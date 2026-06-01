"""E2E: signup → login → GET /me → OAuth authorize URL."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_full_signup_login_me_journey(client: AsyncClient) -> None:
    email = "journey+signup@example.com"
    password = "Password123!"
    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "business_name": "Journey Biz"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == email
    assert body["client_id"]

    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    access = r.json()["access_token"]

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    oauth = await client.get(
        "/api/v1/oauth/google/authorize", headers={"Authorization": f"Bearer {access}"}
    )
    assert oauth.status_code == 200
    assert oauth.json()["authorize_url"].startswith("https://accounts.google.com/")


async def test_login_with_bad_password_returns_401(client: AsyncClient) -> None:
    email = "journey+badpass@example.com"
    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "business_name": "Badpass Biz"},
    )
    assert r.status_code == 201
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    assert r.status_code == 401
