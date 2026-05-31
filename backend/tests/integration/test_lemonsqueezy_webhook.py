"""Integration tests for POST /api/v1/webhooks/lemonsqueezy."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubscriptionStatus
from tests.conftest import sign_lemonsqueezy
from tests.factories import build_client, create_full_client

pytestmark = pytest.mark.integration


async def test_webhook_signature_invalid_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    body = json.dumps({"meta": {"event_id": "1", "event_name": "subscription_created"}}).encode()
    r = await client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=body,
        headers={"X-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 401


async def test_webhook_subscription_created_persists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    new_client = build_client()
    db_session.add(new_client)
    await db_session.flush()

    payload = {
        "meta": {
            "event_id": "evt-create-1",
            "event_name": "subscription_created",
            "custom_data": {"client_id": str(new_client.id)},
        },
        "data": {
            "type": "subscriptions",
            "id": "sub-1",
            "attributes": {
                "subscription_id": "sub-1",
                "customer_id": "cust-1",
                "product_name": "Pro",
            },
        },
    }
    body = json.dumps(payload).encode()
    r = await client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=body,
        headers={"X-Signature": sign_lemonsqueezy(body), "Content-Type": "application/json"},
    )
    assert r.status_code == 200

    from app.repositories.subscription_repository import SubscriptionRepository

    sub = await SubscriptionRepository(db_session).get_by_client(new_client.id)
    assert sub is not None
    assert sub.status == SubscriptionStatus.active


async def test_webhook_idempotent_on_replay(client: AsyncClient, db_session: AsyncSession) -> None:
    _client, _user, _settings, sub, _location, _cred = await create_full_client(db_session)
    payload = {
        "meta": {
            "event_id": "evt-replay-1",
            "event_name": "subscription_payment_failed",
            "custom_data": {"client_id": str(sub.client_id)},
        },
        "data": {"type": "subscriptions", "attributes": {}},
    }
    body = json.dumps(payload).encode()
    headers = {
        "X-Signature": sign_lemonsqueezy(body),
        "Content-Type": "application/json",
    }
    r1 = await client.post("/api/v1/webhooks/lemonsqueezy", content=body, headers=headers)
    r2 = await client.post("/api/v1/webhooks/lemonsqueezy", content=body, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200

    from sqlalchemy import select

    from app.models.webhook_event import WebhookEvent

    rows = (
        await db_session.scalars(
            select(WebhookEvent).where(WebhookEvent.event_id == "evt-replay-1")
        )
    ).all()
    assert len(rows) == 1
