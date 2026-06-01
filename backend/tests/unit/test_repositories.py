"""Cross-cutting tests for the main repositories — CRUD + custom queries."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    OAuthCredentialStatus,
    ResponseStatus,
    ReviewStatus,
)
from app.repositories.oauth_repository import OAuthRepository
from app.repositories.response_repository import ResponseRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.user_repository import UserRepository
from tests.factories import (
    build_oauth_credential,
    build_response,
    build_review,
    create_full_client,
)

pytestmark = pytest.mark.integration


async def test_user_repository_get_by_email(db_session: AsyncSession) -> None:
    _client, user, *_ = await create_full_client(db_session)
    fetched = await UserRepository(db_session).get_by_email(user.email)
    assert fetched is not None
    assert fetched.id == user.id

    assert await UserRepository(db_session).get_by_email("missing@example.com") is None


async def test_review_repository_get_by_google_id(db_session: AsyncSession) -> None:
    _client, _user, _settings, _sub, location, _cred = await create_full_client(db_session)
    review = build_review(location_id=location.id, google_review_id="g-r-42")
    db_session.add(review)
    await db_session.flush()
    fetched = await ReviewRepository(db_session).get_by_google_id("g-r-42")
    assert fetched is not None
    assert fetched.id == review.id


async def test_review_repository_list_by_status(db_session: AsyncSession) -> None:
    _client, _user, _settings, _sub, location, _cred = await create_full_client(db_session)
    a = build_review(location_id=location.id, status=ReviewStatus.detected)
    b = build_review(location_id=location.id, status=ReviewStatus.completed)
    db_session.add_all([a, b])
    await db_session.flush()
    rows = await ReviewRepository(db_session).list_by_status(ReviewStatus.detected)
    assert any(r.id == a.id for r in rows)
    assert not any(r.id == b.id for r in rows)


async def test_response_repository_get_active_for_review(db_session: AsyncSession) -> None:
    _client, _user, _settings, _sub, location, _cred = await create_full_client(db_session)
    review = build_review(location_id=location.id)
    db_session.add(review)
    await db_session.flush()
    r1 = build_response(review_id=review.id, version=1)
    r1.is_active = False
    r2 = build_response(review_id=review.id, version=2)
    db_session.add_all([r1, r2])
    await db_session.flush()

    active = await ResponseRepository(db_session).get_active_for_review(review.id)
    assert active is not None
    assert active.id == r2.id


async def test_response_repository_list_due_publications(db_session: AsyncSession) -> None:
    _client, _user, _settings, _sub, location, _cred = await create_full_client(db_session)
    review = build_review(location_id=location.id)
    db_session.add(review)
    await db_session.flush()

    due = build_response(review_id=review.id, status=ResponseStatus.scheduled, version=1)
    due.scheduled_at = datetime.now(UTC) - timedelta(minutes=5)
    not_due = build_response(review_id=review.id, status=ResponseStatus.scheduled, version=2)
    not_due.scheduled_at = datetime.now(UTC) + timedelta(hours=1)
    db_session.add_all([due, not_due])
    await db_session.flush()

    rows = await ResponseRepository(db_session).list_due_publications()
    ids = {r.id for r in rows}
    assert due.id in ids
    assert not_due.id not in ids


async def test_oauth_repository_list_expiring(db_session: AsyncSession) -> None:
    _client, _user, _settings, _sub, _loc, credential = await create_full_client(db_session)
    credential.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    credential.status = OAuthCredentialStatus.expiring
    await db_session.flush()

    rows = await OAuthRepository(db_session).list_expiring_before(datetime.now(UTC))
    assert any(c.id == credential.id for c in rows)


async def test_oauth_repository_skips_revoked_in_expiring(db_session: AsyncSession) -> None:
    from tests.factories import build_client

    client = build_client()
    db_session.add(client)
    await db_session.flush()
    cred = build_oauth_credential(client_id=client.id, status=OAuthCredentialStatus.revoked)
    cred.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.add(cred)
    await db_session.flush()

    rows = await OAuthRepository(db_session).list_expiring_before(datetime.now(UTC))
    assert not any(c.id == cred.id for c in rows)
