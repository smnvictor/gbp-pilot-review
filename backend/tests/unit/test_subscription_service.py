"""Unit tests for SubscriptionService — Lemon Squeezy webhook event handling."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubscriptionStatus, SubscriptionTier
from app.services.subscription_service import TIER_QUOTAS, SubscriptionService
from tests.factories import build_client, create_full_client

pytestmark = pytest.mark.integration


def _payload(event_type: str, client_id: Any, **attrs: Any) -> dict[str, Any]:
    return {
        "meta": {
            "event_id": f"evt-{event_type}",
            "event_name": event_type,
            "custom_data": {"client_id": str(client_id)},
        },
        "data": {
            "type": "subscriptions",
            "id": "sub-1",
            "attributes": {
                "subscription_id": "sub-1",
                "customer_id": "cust-1",
                **attrs,
            },
        },
    }


async def test_handle_subscription_created_creates_sub(db_session: AsyncSession) -> None:
    client = build_client()
    db_session.add(client)
    await db_session.flush()

    payload = _payload("subscription_created", client.id, product_name="Pro")
    await SubscriptionService(db_session).handle_event(
        event_id="evt-created", event_type="subscription_created", payload=payload
    )
    from app.repositories.subscription_repository import SubscriptionRepository

    sub = await SubscriptionRepository(db_session).get_by_client(client.id)
    assert sub is not None
    assert sub.tier == SubscriptionTier.pro
    assert sub.status == SubscriptionStatus.active
    assert sub.monthly_response_quota == TIER_QUOTAS[SubscriptionTier.pro]


async def test_handle_subscription_cancelled(db_session: AsyncSession) -> None:
    _client, _user, _settings, sub, _location, _cred = await create_full_client(db_session)
    payload = _payload("subscription_cancelled", sub.client_id)
    await SubscriptionService(db_session).handle_event(
        event_id="evt-cancel", event_type="subscription_cancelled", payload=payload
    )
    await db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.cancelled
    assert sub.cancelled_at is not None


async def test_handle_payment_failed_marks_past_due(db_session: AsyncSession) -> None:
    _client, _user, _settings, sub, _location, _cred = await create_full_client(db_session)
    payload = _payload("subscription_payment_failed", sub.client_id)
    await SubscriptionService(db_session).handle_event(
        event_id="evt-fail", event_type="subscription_payment_failed", payload=payload
    )
    await db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.past_due


async def test_handle_event_idempotent(db_session: AsyncSession) -> None:
    """Replaying the same event_id should not double-process."""
    client = build_client()
    db_session.add(client)
    await db_session.flush()

    payload = _payload("subscription_created", client.id, product_name="Pro")
    svc = SubscriptionService(db_session)
    await svc.handle_event(event_id="evt-once", event_type="subscription_created", payload=payload)
    # 2nd call must short-circuit
    await svc.handle_event(event_id="evt-once", event_type="subscription_created", payload=payload)

    from sqlalchemy import select

    from app.models.webhook_event import WebhookEvent

    rows = (
        await db_session.scalars(select(WebhookEvent).where(WebhookEvent.event_id == "evt-once"))
    ).all()
    # Only one persisted event row
    assert len(rows) == 1


async def test_tier_inferred_from_product_name() -> None:
    assert (
        SubscriptionService._tier_from_attrs({"product_name": "Business Annual"})
        == SubscriptionTier.business
    )
    assert (
        SubscriptionService._tier_from_attrs({"product_name": "Pro Monthly"})
        == SubscriptionTier.pro
    )
    assert (
        SubscriptionService._tier_from_attrs({"product_name": "Starter"})
        == SubscriptionTier.starter
    )
    assert SubscriptionService._tier_from_attrs({}) == SubscriptionTier.starter
