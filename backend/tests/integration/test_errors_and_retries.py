"""Integration tests for retry/circuit breaker behaviour around external calls."""

from unittest.mock import AsyncMock

import pybreaker
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.google_business.exceptions import GoogleAuthError
from app.utils.circuit import ALL_BREAKERS, google_breaker
from app.utils.retry import with_retry
from tests.factories import build_review, create_full_client

pytestmark = pytest.mark.integration


def _reset_breakers() -> None:
    for br in ALL_BREAKERS.values():
        br.close()


async def test_retry_eventually_succeeds() -> None:
    attempts = {"n": 0}

    @with_retry(max_attempts=3, base_delay=0.0, jitter=False)
    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert attempts["n"] == 3


async def test_retry_exhausts_and_reraises() -> None:
    @with_retry(max_attempts=2, base_delay=0.0, jitter=False)
    async def always_fails() -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await always_fails()


async def test_circuit_breaker_opens_on_repeated_failures() -> None:
    _reset_breakers()
    fails_needed = google_breaker.fail_max

    def boom() -> None:
        raise RuntimeError("google down")

    # The call that reaches the threshold opens the circuit and raises
    # CircuitBreakerError directly (instead of re-raising the underlying error),
    # so accept either exception while the breaker is still closing.
    for _ in range(fails_needed):
        with pytest.raises((RuntimeError, pybreaker.CircuitBreakerError)):
            google_breaker.call(boom)
    assert google_breaker.current_state == "open"
    with pytest.raises(pybreaker.CircuitBreakerError):
        google_breaker.call(boom)
    _reset_breakers()


async def test_polling_marks_credential_revoked_on_persistent_auth_error(
    db_session: AsyncSession, mock_google_adapter: AsyncMock
) -> None:
    from app.models.enums import OAuthCredentialStatus
    from app.services.polling_service import PollingService

    client, _user, _settings, _sub, location, credential = await create_full_client(db_session)
    db_session.add(build_review(location_id=location.id))
    await db_session.flush()

    mock_google_adapter.list_reviews = AsyncMock(side_effect=GoogleAuthError("invalid_grant"))
    svc = PollingService(db_session, adapter=mock_google_adapter)
    with pytest.raises(GoogleAuthError):
        await svc.poll_client(client.id)
    await db_session.refresh(credential)
    assert credential.status == OAuthCredentialStatus.revoked
