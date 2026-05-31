from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.enums import ResponseSource, ResponseStatus, UserRole
from app.repositories.location_repository import LocationRepository
from app.repositories.response_repository import ResponseRepository
from app.repositories.review_repository import ReviewRepository
from app.schemas.response import ResponsePublic, ResponseUpdate
from app.services.publication_service import PublicationService

router = APIRouter(prefix="/responses", tags=["responses"])


async def _ensure_owner(session, response, user) -> None:  # type: ignore[no-untyped-def]
    if user.role == UserRole.admin:
        return
    review = await ReviewRepository(session).get(response.review_id)
    if review is None:
        raise HTTPException(404)
    location = await LocationRepository(session).get(review.location_id)
    if location is None:
        raise HTTPException(404)
    if user.client_id != location.client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.get("/{response_id}", response_model=ResponsePublic)
async def get_response(response_id: UUID, session: SessionDep, user: CurrentUser) -> ResponsePublic:
    response = await ResponseRepository(session).get(response_id)
    if response is None:
        raise HTTPException(404)
    await _ensure_owner(session, response, user)
    return ResponsePublic.model_validate(response)


@router.post("/{response_id}/approve", response_model=ResponsePublic)
async def approve(response_id: UUID, session: SessionDep, user: CurrentUser) -> ResponsePublic:
    response = await ResponseRepository(session).get(response_id)
    if response is None:
        raise HTTPException(404)
    await _ensure_owner(session, response, user)
    updated = await PublicationService(session).schedule_publication(response_id, user.id)
    return ResponsePublic.model_validate(updated)


@router.post("/{response_id}/cancel", response_model=ResponsePublic)
async def cancel(response_id: UUID, session: SessionDep, user: CurrentUser) -> ResponsePublic:
    response = await ResponseRepository(session).get(response_id)
    if response is None:
        raise HTTPException(404)
    await _ensure_owner(session, response, user)
    updated = await PublicationService(session).cancel_publication(response_id)
    return ResponsePublic.model_validate(updated)


@router.patch("/{response_id}", response_model=ResponsePublic)
async def edit(
    response_id: UUID,
    payload: ResponseUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> ResponsePublic:
    repo = ResponseRepository(session)
    response = await repo.get(response_id)
    if response is None:
        raise HTTPException(404)
    await _ensure_owner(session, response, user)
    if response.status not in (
        ResponseStatus.draft,
        ResponseStatus.pending_validation_client,
        ResponseStatus.pending_validation_team,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit from status {response.status.value}",
        )
    response.content = payload.content
    response.source = ResponseSource.manual_client
    await session.commit()
    return ResponsePublic.model_validate(response)


@router.post("/{response_id}/regenerate", response_model=ResponsePublic)
async def regenerate(response_id: UUID, session: SessionDep, user: CurrentUser) -> ResponsePublic:
    response = await ResponseRepository(session).get(response_id)
    if response is None:
        raise HTTPException(404)
    await _ensure_owner(session, response, user)

    from app.models.regeneration import Regeneration
    from app.tasks.generation_tasks import generate_response

    session.add(Regeneration(review_id=response.review_id, requested_by_user_id=user.id))
    response.is_active = False
    response.status = ResponseStatus.superseded
    await session.commit()

    generate_response.apply_async(args=[str(response.review_id)])
    return ResponsePublic.model_validate(response)
