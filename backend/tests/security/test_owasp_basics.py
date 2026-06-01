"""OWASP Top 10 smoke checks — light coverage for the easy wins."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers
from tests.factories import create_full_client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_a02_password_hash_never_returned_on_signup(
    client: AsyncClient,
) -> None:
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "no-leak@example.com",
            "password": "Password123!",
            "business_name": "No Leak Co",
        },
    )
    body = res.text
    assert "password_hash" not in body
    assert "Password123!" not in body


async def test_a02_password_hash_absent_from_me(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _client, user, *_ = await create_full_client(db_session)
    await db_session.commit()
    res = await client.get("/api/v1/me", headers=auth_headers(user.id))
    assert res.status_code == 200
    assert "password_hash" not in res.json()


async def test_a05_security_misconfig_no_powered_by(
    client: AsyncClient,
) -> None:
    res = await client.get("/healthz")
    lower = {k.lower() for k in res.headers}
    assert "x-powered-by" not in lower
    assert "server" not in lower


async def test_a07_login_with_wrong_credentials_returns_401(
    client: AsyncClient,
) -> None:
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )
    assert res.status_code in (401, 422)


async def test_a08_lemonsqueezy_webhook_rejects_bad_signature(
    client: AsyncClient,
) -> None:
    payload = {"meta": {"event_id": "x", "event_name": "subscription_created"}, "data": {}}
    res = await client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=json.dumps(payload).encode(),
        headers={"X-Signature": "deadbeef", "content-type": "application/json"},
    )
    assert res.status_code in (400, 401, 403)
