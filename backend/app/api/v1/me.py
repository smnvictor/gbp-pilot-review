from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.client import Client
from app.schemas.auth import UserPublic
from app.schemas.export import UserDataExport
from app.services.gdpr_service import GDPRService

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserPublic)
async def get_me(user: CurrentUser, session: SessionDep) -> UserPublic:
    me = UserPublic.model_validate(user)
    if user.client_id is not None:
        client = await session.get(Client, user.client_id)
        me.onboarding_completed = bool(client and client.onboarding_completed_at)
    return me


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: CurrentUser, session: SessionDep) -> None:
    from datetime import UTC, datetime

    user.deleted_at = datetime.now(UTC)
    await session.commit()


@router.get("/export", response_model=UserDataExport)
async def export_me(user: CurrentUser, session: SessionDep) -> UserDataExport:
    return await GDPRService(session).export_user_data(user)
