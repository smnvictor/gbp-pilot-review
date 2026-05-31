import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations.google_business.adapter import GoogleBusinessAdapter
from app.integrations.google_business.client import GoogleBusinessClient
from app.integrations.google_business.exceptions import GoogleAuthError
from app.models.enums import LocationStatus, OAuthCredentialStatus
from app.models.location import Location
from app.models.oauth_credential import OAuthCredential
from app.repositories.location_repository import LocationRepository
from app.repositories.oauth_repository import OAuthRepository

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE_BUSINESS_MANAGE = "https://www.googleapis.com/auth/business.manage"


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_oauth_client_id.get_secret_value(),
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": SCOPE_BUSINESS_MANAGE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


def generate_state() -> str:
    return secrets.token_urlsafe(32)


class OAuthService:
    def __init__(
        self,
        session: AsyncSession,
        adapter: GoogleBusinessAdapter | None = None,
    ) -> None:
        self.session = session
        self.repo = OAuthRepository(session)
        self.locations = LocationRepository(session)
        self.adapter: GoogleBusinessAdapter = adapter or GoogleBusinessClient()

    async def exchange_and_persist(self, *, code: str, client_id: UUID) -> OAuthCredential:
        settings = get_settings()
        token = await self.adapter.exchange_code(code, settings.google_oauth_redirect_uri)

        if not token.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google did not return a refresh_token (re-consent required)",
            )

        existing = await self.repo.get_by_client(client_id)
        expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)
        if existing is None:
            credential = OAuthCredential(
                client_id=client_id,
                access_token_encrypted=token.access_token,
                refresh_token_encrypted=token.refresh_token,
                scopes=token.scope.split(),
                expires_at=expires_at,
                status=OAuthCredentialStatus.active,
                last_refreshed_at=datetime.now(UTC),
            )
            await self.repo.add(credential)
        else:
            credential = existing
            credential.access_token_encrypted = token.access_token
            credential.refresh_token_encrypted = token.refresh_token
            credential.scopes = token.scope.split()
            credential.expires_at = expires_at
            credential.status = OAuthCredentialStatus.active
            credential.last_refreshed_at = datetime.now(UTC)
            credential.last_error = None
            await self.session.flush()

        await self._sync_locations(credential)
        await self.session.commit()
        return credential

    async def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        try:
            token = await self.adapter.refresh_token(credential.refresh_token_encrypted)
        except GoogleAuthError as exc:
            credential.status = OAuthCredentialStatus.revoked
            credential.last_error = str(exc)
            credential.last_check_at = datetime.now(UTC)
            await self.session.commit()
            raise
        credential.access_token_encrypted = token.access_token
        if token.refresh_token:
            credential.refresh_token_encrypted = token.refresh_token
        credential.expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)
        credential.status = OAuthCredentialStatus.active
        credential.last_refreshed_at = datetime.now(UTC)
        credential.last_check_at = datetime.now(UTC)
        credential.last_error = None
        await self.session.commit()
        return credential

    async def revoke(self, credential: OAuthCredential) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            await self.adapter.revoke_token(credential.refresh_token_encrypted)
        credential.status = OAuthCredentialStatus.revoked
        await self.session.commit()

    async def _sync_locations(self, credential: OAuthCredential) -> None:
        google_locations = await self.adapter.list_locations(credential.access_token_encrypted)
        existing = {
            loc.google_location_id: loc
            for loc in await self.locations.list_by_client(credential.client_id)
        }
        for gl in google_locations:
            # name is "accounts/123/locations/456" — split for storage
            parts = gl.name.split("/")
            account_id = parts[1] if len(parts) >= 2 else ""
            location_id = parts[-1]
            if location_id in existing:
                existing[location_id].name = gl.title
                existing[location_id].primary_category = gl.primary_category
                existing[location_id].address = "\n".join(gl.address_lines) or None
            else:
                self.session.add(
                    Location(
                        client_id=credential.client_id,
                        google_account_id=account_id,
                        google_location_id=location_id,
                        name=gl.title,
                        address="\n".join(gl.address_lines) or None,
                        primary_category=gl.primary_category,
                        status=LocationStatus.active,
                    )
                )
        await self.session.flush()
