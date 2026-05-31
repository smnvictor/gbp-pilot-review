"""Integration tests for POST /api/v1/responses/{id}/approve|cancel|edit (admin bypass)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.enums import ResponseStatus, UserRole
from app.models.response import Response
from app.models.user import User
from tests.conftest import auth_headers
from tests.factories import (
    build_response,
    build_review,
    build_user,
    create_full_client,
)

pytestmark = pytest.mark.integration


async def _seed_response(db_session: AsyncSession) -> tuple[Client, User, Response]:
    client, user, _settings, _sub, location, _cred = await create_full_client(db_session)
    review = build_review(location_id=location.id)
    db_session.add(review)
    await db_session.flush()
    response = build_response(review_id=review.id, status=ResponseStatus.pending_validation_client)
    db_session.add(response)
    await db_session.flush()
    return client, user, response


async def test_owner_can_approve(client: AsyncClient, db_session: AsyncSession) -> None:
    _c, user, response = await _seed_response(db_session)
    r = await client.post(
        f"/api/v1/responses/{response.id}/approve",
        headers=auth_headers(user.id, role="client"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduled"


async def test_non_owner_gets_403(client: AsyncClient, db_session: AsyncSession) -> None:
    _c1, _user, response = await _seed_response(db_session)
    intruder = build_user()
    db_session.add(intruder)
    await db_session.flush()

    r = await client.post(
        f"/api/v1/responses/{response.id}/approve",
        headers=auth_headers(intruder.id, role="client"),
    )
    assert r.status_code == 403


async def test_admin_bypasses_owner_check(client: AsyncClient, db_session: AsyncSession) -> None:
    _c, _user, response = await _seed_response(db_session)
    admin = build_user(role=UserRole.admin)
    db_session.add(admin)
    await db_session.flush()

    r = await client.post(
        f"/api/v1/responses/{response.id}/approve",
        headers=auth_headers(admin.id, role="admin"),
    )
    assert r.status_code == 200, r.text
