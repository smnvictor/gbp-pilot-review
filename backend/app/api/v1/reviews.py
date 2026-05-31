from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.enums import ReviewStatus
from app.models.location import Location
from app.models.review import Review
from app.repositories.location_repository import LocationRepository
from app.repositories.review_repository import ReviewRepository
from app.schemas.review import ReviewPublic

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=list[ReviewPublic])
async def list_reviews(
    session: SessionDep,
    user: CurrentUser,
    status: Annotated[ReviewStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReviewPublic]:
    if user.client_id is None:
        return []
    stmt = (
        select(Review)
        .join(Location, Location.id == Review.location_id)
        .where(Location.client_id == user.client_id, Review.deleted_at.is_(None))
        .order_by(Review.posted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(Review.status == status)
    rows = (await session.scalars(stmt)).all()
    return [ReviewPublic.model_validate(r) for r in rows]


@router.get("/pending", response_model=list[ReviewPublic])
async def list_pending(
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReviewPublic]:
    if user.client_id is None:
        return []
    stmt = (
        select(Review)
        .join(Location, Location.id == Review.location_id)
        .where(
            Location.client_id == user.client_id,
            Review.status.in_(
                (ReviewStatus.requires_human_validation, ReviewStatus.awaiting_response)
            ),
            Review.deleted_at.is_(None),
        )
        .order_by(Review.posted_at.desc())
        .limit(limit)
    )
    rows = (await session.scalars(stmt)).all()
    return [ReviewPublic.model_validate(r) for r in rows]


@router.get("/{review_id}", response_model=ReviewPublic)
async def get_review(review_id: UUID, session: SessionDep, user: CurrentUser) -> ReviewPublic:
    review = await ReviewRepository(session).get(review_id)
    if review is None:
        raise HTTPException(404)
    location = await LocationRepository(session).get(review.location_id)
    if location is None or location.client_id != user.client_id:
        raise HTTPException(404)
    return ReviewPublic.model_validate(review)
