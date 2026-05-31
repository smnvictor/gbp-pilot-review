from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.client import Client
from app.models.enums import OAuthCredentialStatus, UserRole
from app.models.oauth_credential import OAuthCredential
from app.repositories.dead_letter_repository import DeadLetterRepository
from app.schemas.admin import AdminOAuthCredentialPublic, AdminSystemMetrics
from app.services.admin_metrics import get_system_metrics
from app.services.dlq_service import replay
from app.utils.circuit import breaker_states

router = APIRouter(prefix="/admin/monitoring", tags=["admin"])


def _ensure_admin(user) -> None:  # type: ignore[no-untyped-def]
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.get("/dlq")
async def list_dlq(session: SessionDep, user: CurrentUser) -> list[dict[str, object]]:
    _ensure_admin(user)
    jobs = await DeadLetterRepository(session).list_unreplayed()
    return [
        {
            "id": j.id,
            "task_name": j.task_name,
            "attempts": j.attempts,
            "last_error": j.last_error,
            "failed_at": j.failed_at.isoformat(),
        }
        for j in jobs
    ]


@router.post("/dlq/{dlq_id}/replay", status_code=status.HTTP_202_ACCEPTED)
async def replay_dlq(dlq_id: int, user: CurrentUser) -> dict[str, str]:
    _ensure_admin(user)
    replay(dlq_id)
    return {"status": "replayed"}


@router.get("/circuits")
async def circuits(user: CurrentUser) -> dict[str, str]:
    _ensure_admin(user)
    return breaker_states()


@router.get("/oauth-alerts", response_model=list[AdminOAuthCredentialPublic])
async def oauth_alerts(session: SessionDep, user: CurrentUser) -> list[AdminOAuthCredentialPublic]:
    _ensure_admin(user)
    stmt = (
        select(OAuthCredential, Client.business_name)
        .join(Client, Client.id == OAuthCredential.client_id)
        .where(
            OAuthCredential.status.in_(
                [
                    OAuthCredentialStatus.expiring,
                    OAuthCredentialStatus.expired,
                    OAuthCredentialStatus.revoked,
                ]
            ),
            Client.deleted_at.is_(None),
        )
        .order_by(OAuthCredential.expires_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        AdminOAuthCredentialPublic(
            client_id=cred.client_id,
            business_name=business_name,
            status=cred.status,
            expires_at=cred.expires_at,
            last_refreshed_at=cred.last_refreshed_at,
            last_check_at=cred.last_check_at,
            last_error=cred.last_error,
        )
        for cred, business_name in rows
    ]


@router.get("/metrics", response_model=AdminSystemMetrics)
async def system_metrics(session: SessionDep, user: CurrentUser) -> AdminSystemMetrics:
    _ensure_admin(user)
    return await get_system_metrics(session)
