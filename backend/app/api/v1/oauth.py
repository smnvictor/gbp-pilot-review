import jwt
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from loguru import logger
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.config import get_settings
from app.database import SessionDep
from app.models.enums import OAuthCredentialStatus
from app.repositories.location_repository import LocationRepository
from app.repositories.oauth_repository import OAuthRepository
from app.security.auth import create_access_token, decode_token
from app.services.oauth_service import OAuthService, build_authorize_url, generate_state

router = APIRouter(prefix="/oauth/google", tags=["oauth"])


class OAuthLocationPublic(BaseModel):
    id: str
    name: str
    address: str | None = None
    primary_category: str | None = None
    status: str


class OAuthStatusResponse(BaseModel):
    connected: bool
    status: str | None = None
    expires_at: str | None = None
    locations: list[OAuthLocationPublic]


@router.get("/authorize")
async def authorize(user: CurrentUser) -> dict[str, str]:
    if user.client_id is None:
        raise HTTPException(status_code=400, detail="User has no client")
    state = create_access_token(
        user.client_id,
        role="oauth_state",
        extra={"state_nonce": generate_state(), "type": "oauth_state"},
    )
    return {"authorize_url": build_authorize_url(state), "state": state}


@router.get("/status", response_model=OAuthStatusResponse)
async def oauth_status(session: SessionDep, user: CurrentUser) -> OAuthStatusResponse:
    if user.client_id is None:
        raise HTTPException(status_code=400, detail="User has no client")
    credential = await OAuthRepository(session).get_by_client(user.client_id)
    locations = await LocationRepository(session).list_by_client(user.client_id)
    return OAuthStatusResponse(
        connected=credential is not None
        and credential.status == OAuthCredentialStatus.active,
        status=credential.status.value if credential else None,
        expires_at=credential.expires_at.isoformat() if credential else None,
        locations=[
            OAuthLocationPublic(
                id=str(loc.id),
                name=loc.name,
                address=loc.address,
                primary_category=loc.primary_category,
                status=loc.status.value,
            )
            for loc in locations
        ],
    )


@router.get("/callback")
async def callback(
    session: SessionDep,
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    settings = get_settings()
    try:
        payload = decode_token(state)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid state") from exc
    if payload.get("type") != "oauth_state":
        raise HTTPException(status_code=400, detail="Invalid state token type")

    from uuid import UUID
    client_id = UUID(payload["sub"])

    service = OAuthService(session)
    try:
        await service.exchange_and_persist(code=code, client_id=client_id)
    except Exception as exc:
        logger.exception("OAuth callback failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return RedirectResponse(url=f"{settings.frontend_url}/onboarding/connected", status_code=302)
