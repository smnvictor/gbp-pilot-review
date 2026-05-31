from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.config import get_settings
from app.database import SessionDep
from app.integrations.lemonsqueezy.client import LemonSqueezyClient, LemonSqueezyError
from app.models.enums import SubscriptionTier
from app.repositories.quota_repository import QuotaRepository, current_year_month
from app.repositories.subscription_repository import SubscriptionRepository

router = APIRouter(prefix="/subscription", tags=["subscription"])


class SubscriptionPublic(BaseModel):
    tier: str
    status: str
    monthly_response_quota: int
    quota_used: int
    current_period_end: str | None = None
    cancelled_at: str | None = None


class CheckoutRequest(BaseModel):
    tier: SubscriptionTier


class CheckoutResponse(BaseModel):
    url: str


@router.get("", response_model=SubscriptionPublic)
async def get_subscription(session: SessionDep, user: CurrentUser) -> SubscriptionPublic:
    if user.client_id is None:
        raise HTTPException(404)
    sub = await SubscriptionRepository(session).get_by_client(user.client_id)
    if sub is None:
        raise HTTPException(404)
    usage = await QuotaRepository(session).get_or_create(user.client_id, current_year_month())
    return SubscriptionPublic(
        tier=sub.tier.value,
        status=sub.status.value,
        monthly_response_quota=sub.monthly_response_quota,
        quota_used=usage.count,
        current_period_end=(sub.current_period_end.isoformat() if sub.current_period_end else None),
        cancelled_at=sub.cancelled_at.isoformat() if sub.cancelled_at else None,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(payload: CheckoutRequest, user: CurrentUser) -> CheckoutResponse:
    if user.client_id is None:
        raise HTTPException(404)
    variant_id = get_settings().lemonsqueezy_variant_for_tier(payload.tier.value)
    if not variant_id:
        # Misconfiguration (missing LEMONSQUEEZY_VARIANT_* env) — surface a clear
        # error instead of an opaque 502 from Lemon Squeezy rejecting a bad variant.
        raise HTTPException(
            status_code=503,
            detail=f"Billing not configured for the '{payload.tier.value}' plan",
        )
    try:
        url = await LemonSqueezyClient().create_checkout(
            variant_id=variant_id,
            customer_email=user.email,
            custom={"client_id": str(user.client_id)},
        )
    except LemonSqueezyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CheckoutResponse(url=url)
