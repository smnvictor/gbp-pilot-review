from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.client import Client
from app.models.enums import (
    ClientStatus,
    ResponseStatus,
    UserRole,
)
from app.models.location import Location
from app.models.oauth_credential import OAuthCredential
from app.models.response import Response
from app.models.review import Review
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.admin import (
    AdminClientDetail,
    AdminClientListItem,
    AdminClientMetrics,
    AdminClientNotesUpdate,
)
from app.services.admin_metrics import get_client_metrics
from app.services.audit_service import audit

router = APIRouter(prefix="/admin/clients", tags=["admin"])


def _ensure_admin(user: User) -> None:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.get("", response_model=list[AdminClientListItem])
async def list_clients(
    session: SessionDep,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[ClientStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminClientListItem]:
    _ensure_admin(user)

    owner = aliased(User)
    stmt = (
        select(
            Client,
            owner.email.label("owner_email"),
            OAuthCredential.status.label("oauth_status"),
        )
        .outerjoin(
            owner,
            (owner.client_id == Client.id) & (owner.deleted_at.is_(None)),
        )
        .outerjoin(OAuthCredential, OAuthCredential.client_id == Client.id)
        .where(Client.deleted_at.is_(None))
    )
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Client.business_name).like(like),
                func.lower(Client.slug).like(like),
            )
        )
    if status_filter is not None:
        stmt = stmt.where(Client.status == status_filter)

    stmt = stmt.order_by(Client.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()

    if not rows:
        return []

    client_ids = [r[0].id for r in rows]
    pending_rows = await session.execute(
        select(Location.client_id, func.count(Response.id))
        .join(Review, Review.location_id == Location.id)
        .join(Response, Response.review_id == Review.id)
        .where(
            Location.client_id.in_(client_ids),
            Response.status.in_(
                [
                    ResponseStatus.pending_validation_client,
                    ResponseStatus.pending_validation_team,
                ]
            ),
            Response.deleted_at.is_(None),
        )
        .group_by(Location.client_id)
    )
    pending_by_client: dict[UUID, int] = {row[0]: row[1] for row in pending_rows}

    items: list[AdminClientListItem] = []
    for client, owner_email, oauth_status in rows:
        items.append(
            AdminClientListItem(
                id=client.id,
                business_name=client.business_name,
                slug=client.slug,
                status=client.status,
                created_at=client.created_at,
                owner_email=owner_email,
                has_oauth=oauth_status is not None,
                oauth_status=oauth_status,
                pending_count=pending_by_client.get(client.id, 0),
            )
        )
    return items


async def _load_detail(session: SessionDep, client_id: UUID) -> AdminClientDetail:
    client = await session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(404)

    owner_email = await session.scalar(
        select(User.email).where(User.client_id == client_id, User.deleted_at.is_(None)).limit(1)
    )
    subscription = await session.scalar(
        select(Subscription).where(Subscription.client_id == client_id)
    )
    oauth = await session.scalar(
        select(OAuthCredential).where(OAuthCredential.client_id == client_id)
    )
    locations_count = (
        await session.scalar(select(func.count(Location.id)).where(Location.client_id == client_id))
        or 0
    )

    reviews_total = (
        await session.scalar(
            select(func.count(Review.id))
            .join(Location, Location.id == Review.location_id)
            .where(Location.client_id == client_id, Review.deleted_at.is_(None))
        )
        or 0
    )
    published_total = (
        await session.scalar(
            select(func.count(Response.id))
            .join(Review, Review.id == Response.review_id)
            .join(Location, Location.id == Review.location_id)
            .where(
                Location.client_id == client_id,
                Response.status == ResponseStatus.published,
                Response.deleted_at.is_(None),
            )
        )
        or 0
    )
    pending = (
        await session.scalar(
            select(func.count(Response.id))
            .join(Review, Review.id == Response.review_id)
            .join(Location, Location.id == Review.location_id)
            .where(
                Location.client_id == client_id,
                Response.status.in_(
                    [
                        ResponseStatus.pending_validation_client,
                        ResponseStatus.pending_validation_team,
                    ]
                ),
                Response.deleted_at.is_(None),
            )
        )
        or 0
    )

    return AdminClientDetail(
        id=client.id,
        business_name=client.business_name,
        slug=client.slug,
        status=client.status,
        business_context=client.business_context,
        tone_instructions=client.tone_instructions,
        admin_notes=client.admin_notes,
        onboarding_completed_at=client.onboarding_completed_at,
        created_at=client.created_at,
        updated_at=client.updated_at,
        owner_email=owner_email,
        subscription_tier=subscription.tier if subscription else None,
        subscription_status=subscription.status if subscription else None,
        oauth_status=oauth.status if oauth else None,
        oauth_expires_at=oauth.expires_at if oauth else None,
        locations_count=locations_count,
        reviews_total=reviews_total,
        responses_published_total=published_total,
        pending_validation=pending,
    )


@router.get("/{client_id}", response_model=AdminClientDetail)
async def get_client_detail(
    client_id: UUID, session: SessionDep, user: CurrentUser
) -> AdminClientDetail:
    _ensure_admin(user)
    return await _load_detail(session, client_id)


@router.patch("/{client_id}/notes", response_model=AdminClientDetail)
async def update_notes(
    client_id: UUID,
    payload: AdminClientNotesUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> AdminClientDetail:
    _ensure_admin(user)
    client = await session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(404)
    client.admin_notes = payload.admin_notes
    await audit(
        session,
        actor_user_id=user.id,
        action="client.notes_updated",
        target_type="client",
        target_id=client.id,
        metadata={"has_notes": payload.admin_notes is not None},
    )
    await session.commit()
    return await _load_detail(session, client_id)


@router.get("/{client_id}/metrics", response_model=AdminClientMetrics)
async def get_metrics(
    client_id: UUID, session: SessionDep, user: CurrentUser
) -> AdminClientMetrics:
    _ensure_admin(user)
    client = await session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(404)
    return await get_client_metrics(session, client_id)


@router.post("/{client_id}/suspend", response_model=AdminClientDetail)
async def suspend(client_id: UUID, session: SessionDep, user: CurrentUser) -> AdminClientDetail:
    _ensure_admin(user)
    client = await session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(404)
    client.status = ClientStatus.suspended
    await audit(
        session,
        actor_user_id=user.id,
        action="client.suspend",
        target_type="client",
        target_id=client.id,
    )
    await session.commit()
    return await _load_detail(session, client_id)


@router.post("/{client_id}/reactivate", response_model=AdminClientDetail)
async def reactivate(client_id: UUID, session: SessionDep, user: CurrentUser) -> AdminClientDetail:
    _ensure_admin(user)
    client = await session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(404)
    client.status = ClientStatus.active
    await audit(
        session,
        actor_user_id=user.id,
        action="client.reactivate",
        target_type="client",
        target_id=client.id,
    )
    await session.commit()
    return await _load_detail(session, client_id)
