"""Unit tests for OAuthService — exchange_and_persist and refresh."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.google_business.exceptions import GoogleAuthError
from app.integrations.google_business.schemas import GoogleTokenResponse
from app.models.enums import OAuthCredentialStatus
from app.services.oauth_service import OAuthService
from tests.factories import build_client, create_full_client

pytestmark = pytest.mark.integration


async def test_exchange_and_persist_creates_credential_and_location(
    db_session: AsyncSession, mock_google_adapter: AsyncMock
) -> None:
    client = build_client()
    db_session.add(client)
    await db_session.flush()

    service = OAuthService(db_session, adapter=mock_google_adapter)
    cred = await service.exchange_and_persist(code="auth-code", client_id=client.id)

    assert cred.status == OAuthCredentialStatus.active
    assert cred.client_id == client.id
    assert cred.refresh_token_encrypted == "fake-refresh-token"

    from app.repositories.location_repository import LocationRepository

    locations = await LocationRepository(db_session).list_by_client(client.id)
    assert len(locations) == 1


async def test_exchange_without_refresh_token_raises_400(
    db_session: AsyncSession, mock_google_adapter: AsyncMock
) -> None:
    client = build_client()
    db_session.add(client)
    await db_session.flush()

    mock_google_adapter.exchange_code = AsyncMock(
        return_value=GoogleTokenResponse(
            access_token="ax",
            refresh_token=None,
            expires_in=3600,
            scope="https://www.googleapis.com/auth/business.manage",
        )
    )
    service = OAuthService(db_session, adapter=mock_google_adapter)
    with pytest.raises(HTTPException) as exc:
        await service.exchange_and_persist(code="auth-code", client_id=client.id)
    assert exc.value.status_code == 400


async def test_refresh_marks_credential_active(
    db_session: AsyncSession, mock_google_adapter: AsyncMock
) -> None:
    _client, _user, _settings, _sub, _location, credential = await create_full_client(db_session)
    credential.status = OAuthCredentialStatus.expiring
    await db_session.flush()

    service = OAuthService(db_session, adapter=mock_google_adapter)
    refreshed = await service.refresh(credential)
    assert refreshed.status == OAuthCredentialStatus.active
    assert refreshed.last_refreshed_at is not None


async def test_refresh_marks_revoked_on_auth_error(
    db_session: AsyncSession, mock_google_adapter: AsyncMock
) -> None:
    _client, _user, _settings, _sub, _location, credential = await create_full_client(db_session)
    mock_google_adapter.refresh_token = AsyncMock(side_effect=GoogleAuthError("invalid_grant"))

    service = OAuthService(db_session, adapter=mock_google_adapter)
    with pytest.raises(GoogleAuthError):
        await service.refresh(credential)
    await db_session.refresh(credential)
    assert credential.status == OAuthCredentialStatus.revoked
