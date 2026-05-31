from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.client import Client

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingCompleteRequest(BaseModel):
    business_name: str | None = Field(default=None, max_length=200)


@router.post("/complete")
async def complete_onboarding(
    payload: OnboardingCompleteRequest, session: SessionDep, user: CurrentUser
) -> dict[str, bool]:
    if user.client_id is None:
        raise HTTPException(404, "User has no client")
    client = await session.get(Client, user.client_id)
    if client is None:
        raise HTTPException(404, "Client not found")
    if payload.business_name:
        client.business_name = payload.business_name
    client.onboarding_completed_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True}
