import os
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault(
    # Generated via: Fernet.generate_key().decode()
    "OAUTH_TOKEN_ENCRYPTION_KEY",
    "kHbA6rys1I7sV46M2WI2WY6Sl6NF1m0XRLnXwvTV-HA=",
)
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://app:dev@localhost:5432/gbp_review_manager_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-google-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-google-secret")
os.environ.setdefault(
    "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/oauth/google/callback"
)
os.environ.setdefault("CLAUDE_API_KEY", "test-claude-key")
os.environ.setdefault("LEMONSQUEEZY_API_KEY", "test-ls-key")
os.environ.setdefault("LEMONSQUEEZY_WEBHOOK_SECRET", "test-ls-webhook")
os.environ.setdefault("LEMONSQUEEZY_STORE_ID", "test-store")
os.environ.setdefault("RESEND_API_KEY", "test-resend-key")
os.environ.setdefault("RESEND_FROM_EMAIL", "noreply@example.test")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")


# ---------------------------------------------------------------------------
# Database fixtures (session-scoped engine, function-scoped rolled-back session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """Session-scoped engine. Creates schema once, drops at the end."""
    from app.config import get_settings
    from app.models import Base

    engine = create_async_engine(str(get_settings().database_url), echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Function-scoped session wrapped in a SAVEPOINT — rolled back per test."""
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        async with sessionmaker(bind=conn) as session:
            try:
                yield session
            finally:
                await session.close()
                await trans.rollback()


# ---------------------------------------------------------------------------
# FastAPI test client with DB dependency override
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app.database import get_session
    from app.main import create_app

    app = create_app()

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def unauthenticated_client() -> AsyncIterator[AsyncClient]:
    """Client without DB override (uses real settings) — for tests that don't need DB."""
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth fixtures — issue tokens for an arbitrary user
# ---------------------------------------------------------------------------


def auth_headers(user_id: Any, role: str = "client") -> dict[str, str]:
    """Build an Authorization header for the given user — usable across tests."""
    from app.security.auth import create_access_token

    token = create_access_token(user_id, role=role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Mocks for external providers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_claude_response() -> dict[str, Any]:
    """Default Claude LLM response payload (status=1, valid content)."""
    return {
        "status": 1,
        "content": "Merci pour votre avis ! Au plaisir de vous accueillir à nouveau.",
        "details": "",
        "tokens_input": 120,
        "tokens_output": 32,
        "model": "claude-sonnet-4-6",
    }


@pytest.fixture
def mock_llm_provider(mock_claude_response: dict[str, Any]) -> AsyncMock:
    """Drop-in replacement for the ClaudeClient LLMProvider."""
    from app.integrations.claude.adapter import LLMResponse

    provider = AsyncMock()
    provider.generate = AsyncMock(return_value=LLMResponse(**mock_claude_response))
    return provider


@pytest.fixture
def mock_google_adapter() -> AsyncMock:
    """Drop-in replacement for the GoogleBusinessAdapter Protocol."""
    from datetime import UTC, datetime

    from app.integrations.google_business.schemas import (
        GoogleLocation,
        GoogleReviewReplyResult,
        GoogleTokenResponse,
    )

    adapter = AsyncMock()
    adapter.exchange_code = AsyncMock(
        return_value=GoogleTokenResponse(
            access_token="fake-access-token",
            refresh_token="fake-refresh-token",
            expires_in=3600,
            scope="https://www.googleapis.com/auth/business.manage",
        )
    )
    adapter.refresh_token = AsyncMock(
        return_value=GoogleTokenResponse(
            access_token="fake-refreshed-token",
            refresh_token="fake-refresh-token",
            expires_in=3600,
            scope="https://www.googleapis.com/auth/business.manage",
        )
    )
    adapter.revoke_token = AsyncMock(return_value=None)
    adapter.list_locations = AsyncMock(
        return_value=[
            GoogleLocation(
                name="accounts/12345/locations/67890",
                title="Test Location",
                primary_category="restaurant",
                address_lines=["1 rue de Test", "75001 Paris"],
            )
        ]
    )
    adapter.list_reviews = AsyncMock(return_value=([], None))
    adapter.reply_to_review = AsyncMock(
        return_value=GoogleReviewReplyResult(comment="ok", update_time=datetime.now(UTC))
    )
    adapter.delete_reply = AsyncMock(return_value=None)
    return adapter


@pytest.fixture
def lemonsqueezy_payload() -> dict[str, Any]:
    """A minimal Lemon Squeezy webhook payload (subscription_created)."""
    return {
        "meta": {
            "event_id": "evt_test_001",
            "event_name": "subscription_created",
            "custom_data": {},  # client_id injected per test
        },
        "data": {
            "type": "subscriptions",
            "id": "sub_test_001",
            "attributes": {
                "subscription_id": "sub_test_001",
                "customer_id": "cust_test_001",
                "product_name": "Pro",
                "variant_name": "Pro Monthly",
            },
        },
    }


def sign_lemonsqueezy(body: bytes) -> str:
    """Generate a valid X-Signature header for the test webhook secret."""
    import hashlib
    import hmac

    secret = os.environ["LEMONSQUEEZY_WEBHOOK_SECRET"].encode()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()
