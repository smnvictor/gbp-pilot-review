"""E2E: GET + PATCH /api/v1/settings updates client settings."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers
from tests.factories import create_full_client

pytestmark = pytest.mark.e2e


async def test_user_updates_settings(client: AsyncClient, db_session: AsyncSession) -> None:
    _c, user, _settings, _sub, _loc, _cred = await create_full_client(db_session)

    r = await client.get("/api/v1/settings", headers=auth_headers(user.id))
    assert r.status_code == 200, r.text

    r = await client.patch(
        "/api/v1/settings",
        headers=auth_headers(user.id),
        json={
            "validation_mode": "team",
            "publish_delay_range": "2h_5h",
            "regex_blocklist": ["^spam$", "viagra"],
            "digest_mode": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["validation_mode"] == "team"
    assert body["publish_delay_range"] == "2h_5h"
    assert body["regex_blocklist"] == ["^spam$", "viagra"]
    assert body["digest_mode"] is True


async def test_settings_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/settings")
    assert r.status_code == 401
