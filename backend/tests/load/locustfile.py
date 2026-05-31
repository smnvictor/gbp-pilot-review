"""Light-load HTTP scenario for the FastAPI app.

Run:
    uv run locust -f tests/load/locustfile.py --headless -u 20 -r 2 -t 2m \
        --host http://localhost:8000

Locust is *not* a project dependency — install ad hoc with `uv tool install locust`
or `pip install locust` in a separate venv. The file imports lazily so importing
this module without locust installed does not crash the test suite.
"""

from __future__ import annotations

import uuid
from pathlib import Path

try:
    from locust import HttpUser, between, task
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "locust not installed — run `uv tool install locust` or `pip install locust`."
    ) from exc


class ClientUser(HttpUser):
    """A simulated SaaS client.

    Each user signs up once, then alternates between reading their review queue
    and (occasionally) PATCH-ing settings.
    """

    wait_time = between(1, 3)
    access_token: str = ""

    def on_start(self) -> None:
        email = f"loadtest-{uuid.uuid4().hex[:8]}@example.test"
        password = "Password123!"
        signup = self.client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": password, "business_name": "Load Biz"},
            name="POST /auth/signup",
        )
        if signup.status_code != 201:
            return
        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            name="POST /auth/login",
        )
        if login.status_code == 200:
            self.access_token = login.json()["access_token"]

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}

    @task(5)
    def get_me(self) -> None:
        self.client.get("/api/v1/me", headers=self.auth_headers, name="GET /me")

    @task(3)
    def get_settings(self) -> None:
        self.client.get("/api/v1/settings", headers=self.auth_headers, name="GET /settings")

    @task(1)
    def patch_settings(self) -> None:
        self.client.patch(
            "/api/v1/settings",
            json={"polling_frequency_minutes": 60},
            headers=self.auth_headers,
            name="PATCH /settings",
        )

    @task(2)
    def healthz(self) -> None:
        # No auth needed — sanity ping
        self.client.get("/healthz", name="GET /healthz")


if __name__ == "__main__":
    print("Run with: locust -f", Path(__file__).resolve())
