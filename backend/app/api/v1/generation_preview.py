from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.client import Client
from app.models.review import Review
from app.repositories.client_settings_repository import ClientSettingsRepository
from app.repositories.location_repository import LocationRepository
from app.repositories.review_repository import ReviewRepository
from app.services.generation_service import GenerationService

router = APIRouter(prefix="/test", tags=["test"])


class TestGenerateRequest(BaseModel):
    review_content: str | None = Field(default=None, max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    review_id: UUID | None = None


class TestGenerateResponse(BaseModel):
    content: str
    ai_status: int
    ai_details: str | None = None
    tone: list[str]
    business_context: str


@router.post("/generate-response", response_model=TestGenerateResponse)
async def generate_response_preview(
    payload: TestGenerateRequest, session: SessionDep, user: CurrentUser
) -> TestGenerateResponse:
    if user.client_id is None:
        raise HTTPException(404, "User has no client")

    service = GenerationService(session)
    settings = await ClientSettingsRepository(session).get_by_client(user.client_id)
    client = await session.get(Client, user.client_id)
    if settings is None or client is None:
        raise HTTPException(404, "Settings not found")

    if payload.review_id is not None:
        review = await ReviewRepository(session).get(payload.review_id)
        if review is None:
            raise HTTPException(404, "Review not found")
        location = await LocationRepository(session).get(review.location_id)
        if location is None or location.client_id != user.client_id:
            raise HTTPException(403, "Review does not belong to this client")
    elif payload.review_content is not None and payload.rating is not None:
        # Transient (unsaved) review — never added to the session.
        review = Review(rating=payload.rating, comment=payload.review_content)
    else:
        raise HTTPException(422, "Provide either review_id or (review_content + rating)")

    version = await service.prompts.active_version()
    result = await service.generate_preview(
        client=client, settings=settings, review=review, version=version
    )
    return TestGenerateResponse(
        content=result.content,
        ai_status=result.ai_status,
        ai_details=result.ai_details,
        tone=result.tone,
        business_context=result.business_context,
    )
