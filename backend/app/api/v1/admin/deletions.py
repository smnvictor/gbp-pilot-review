from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.integrations.google_business.adapter import GoogleBusinessAdapter
from app.integrations.google_business.client import GoogleBusinessClient
from app.integrations.google_business.exceptions import GoogleAuthError, GoogleNetworkError
from app.models.audit_log import AuditLog
from app.models.client import Client
from app.models.enums import OAuthCredentialStatus, ResponseStatus, UserRole
from app.models.location import Location
from app.models.oauth_credential import OAuthCredential
from app.models.response import Response
from app.models.review import Review
from app.models.user import User
from app.schemas.admin import AdminDeletePublishedRequest, AdminPublishedDeletionPublic
from app.services.audit_service import audit

router = APIRouter(prefix="/admin/deletions", tags=["admin"])

PUBLISHED_DELETION_ACTION = "published_response.deleted"


def _ensure_admin(user) -> None:  # type: ignore[no-untyped-def]
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


def _get_adapter() -> GoogleBusinessAdapter:
    return GoogleBusinessClient()


@router.post("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_user(user_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    _ensure_admin(user)
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(404)
    target.deleted_at = datetime.now(UTC)
    await audit(
        session,
        actor_user_id=user.id,
        action="user.soft_delete",
        target_type="user",
        target_id=target.id,
    )
    await session.commit()


@router.post("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_client(client_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    _ensure_admin(user)
    target = await session.get(Client, client_id)
    if target is None:
        raise HTTPException(404)
    target.deleted_at = datetime.now(UTC)
    await audit(
        session,
        actor_user_id=user.id,
        action="client.soft_delete",
        target_type="client",
        target_id=target.id,
    )
    await session.commit()


@router.post("/responses/{response_id}")
async def delete_published_response(
    response_id: UUID,
    payload: AdminDeletePublishedRequest,
    session: SessionDep,
    user: CurrentUser,
) -> dict[str, str]:
    _ensure_admin(user)
    response = await session.get(Response, response_id)
    if response is None or response.deleted_at is not None:
        raise HTTPException(404, "Response not found")
    if response.status != ResponseStatus.published:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete a response with status {response.status.value}",
        )

    review = await session.get(Review, response.review_id)
    if review is None:
        raise HTTPException(500, "Review missing")
    location = await session.get(Location, review.location_id)
    if location is None:
        raise HTTPException(500, "Location missing")

    credential = (
        await session.scalars(
            select(OAuthCredential).where(OAuthCredential.client_id == location.client_id)
        )
    ).first()
    if credential is None or credential.status != OAuthCredentialStatus.active:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="OAuth credential unavailable for this client",
        )

    review_name = (
        f"accounts/{location.google_account_id}"
        f"/locations/{location.google_location_id}/reviews/{review.google_review_id}"
    )

    adapter = _get_adapter()
    try:
        await adapter.delete_reply(credential.access_token_encrypted, review_name)
    except GoogleAuthError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except GoogleNetworkError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc

    now = datetime.now(UTC)
    response.deleted_at = now
    response.is_active = False
    await audit(
        session,
        actor_user_id=user.id,
        action=PUBLISHED_DELETION_ACTION,
        target_type="response",
        target_id=response.id,
        metadata={
            "reason": payload.reason,
            "review_id": str(response.review_id),
            "client_id": str(location.client_id),
        },
    )
    await session.commit()
    return {"status": "deleted"}


@router.get("/responses", response_model=list[AdminPublishedDeletionPublic])
async def list_published_deletions(
    session: SessionDep,
    user: CurrentUser,
    client_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminPublishedDeletionPublic]:
    _ensure_admin(user)
    stmt = (
        select(AuditLog)
        .where(AuditLog.action == PUBLISHED_DELETION_ACTION)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if client_id is not None:
        stmt = stmt.where(AuditLog.metadata_["client_id"].astext == str(client_id))
    rows = (await session.scalars(stmt)).all()
    return [
        AdminPublishedDeletionPublic(
            id=row.id,
            actor_user_id=row.actor_user_id,
            response_id=row.target_id,
            review_id=(
                UUID(row.metadata_["review_id"]) if row.metadata_.get("review_id") else None
            ),
            client_id=(
                UUID(row.metadata_["client_id"]) if row.metadata_.get("client_id") else None
            ),
            reason=row.metadata_.get("reason"),
            created_at=row.created_at,
        )
        for row in rows
    ]
