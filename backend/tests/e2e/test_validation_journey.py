"""E2E: generated response → approve → scheduled."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ResponseStatus
from tests.conftest import auth_headers
from tests.factories import build_response, build_review, create_full_client

pytestmark = pytest.mark.e2e


async def test_user_validates_and_schedules_response(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _c, user, _settings, _sub, location, _cred = await create_full_client(db_session)
    review = build_review(location_id=location.id)
    db_session.add(review)
    await db_session.flush()
    response = build_response(review_id=review.id, status=ResponseStatus.pending_validation_client)
    db_session.add(response)
    await db_session.flush()

    # GET
    r = await client.get(f"/api/v1/responses/{response.id}", headers=auth_headers(user.id))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_validation_client"

    # Approve
    r = await client.post(f"/api/v1/responses/{response.id}/approve", headers=auth_headers(user.id))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"

    # Cancel (within undo window)
    r = await client.post(f"/api/v1/responses/{response.id}/cancel", headers=auth_headers(user.id))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
