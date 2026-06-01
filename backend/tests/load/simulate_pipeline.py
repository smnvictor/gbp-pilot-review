"""Simulate the full pipeline for N concurrent clients and report latencies.

This script does NOT hit live external APIs. It uses the same in-process
services with mocked Google + Claude adapters, but exercises the real DB +
async session machinery to surface contention and serialization issues.

Run:
    docker compose up -d postgres
    DATABASE_URL=postgresql+asyncpg://app:dev@localhost:5432/gbp_review_manager_test \\
        uv run python tests/load/simulate_pipeline.py --clients 20 --reviews 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "load-secret")
os.environ.setdefault("JWT_SECRET", "load-jwt")
os.environ.setdefault("OAUTH_TOKEN_ENCRYPTION_KEY", "kHbA6rys1I7sV46M2WI2WY6Sl6NF1m0XRLnXwvTV-HA=")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://app:dev@localhost:5432/gbp_review_manager_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "load-google-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "load-google-secret")
os.environ.setdefault(
    "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/oauth/google/callback"
)
os.environ.setdefault("CLAUDE_API_KEY", "load-claude-key")
os.environ.setdefault("LEMONSQUEEZY_API_KEY", "load-ls-key")
os.environ.setdefault("LEMONSQUEEZY_WEBHOOK_SECRET", "load-ls-webhook")
os.environ.setdefault("LEMONSQUEEZY_STORE_ID", "load-store")
os.environ.setdefault("RESEND_API_KEY", "load-resend-key")
os.environ.setdefault("RESEND_FROM_EMAIL", "load@example.com")


async def _stage_polling(client_id: UUID, n_reviews: int) -> tuple[float, list[UUID]]:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.database import get_engine
    from app.integrations.google_business.schemas import GoogleReview
    from app.services.polling_service import PollingService

    sm = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    async with sm() as session:
        # Build google reviews
        google_reviews = [
            GoogleReview(
                name=f"accounts/x/locations/y/reviews/load-{client_id}-{i}",
                review_id=f"load-{client_id}-{i}",
                reviewer_display_name="Loadtest",
                rating=5,
                comment="Excellente expérience, je recommande vivement à tous mes amis !",
                create_time=datetime.now(UTC),
            )
            for i in range(n_reviews)
        ]
        adapter = AsyncMock()
        adapter.list_reviews = AsyncMock(return_value=(google_reviews, None))
        svc = PollingService(session, adapter=adapter)
        t0 = time.perf_counter()
        ids = await svc.poll_client(client_id)
        await session.commit()
        return time.perf_counter() - t0, list(ids)


async def _stage_filter_generate_publish(
    client_id: UUID, review_ids: list[UUID], user_id: UUID
) -> dict[str, list[float]]:
    from datetime import timedelta

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.database import get_engine
    from app.integrations.claude.adapter import LLMResponse
    from app.integrations.google_business.schemas import GoogleReviewReplyResult
    from app.services.filtering_service import FilteringService
    from app.services.generation_service import GenerationService
    from app.services.publication_service import PublicationService

    timings: dict[str, list[float]] = {"filter": [], "generate": [], "publish": []}
    sm = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)

    google_adapter = AsyncMock()
    google_adapter.reply_to_review = AsyncMock(
        return_value=GoogleReviewReplyResult(comment="ok", update_time=datetime.now(UTC))
    )
    llm = AsyncMock()
    llm.generate = AsyncMock(
        return_value=LLMResponse(status=1, content="Merci !", details="", model="claude-sonnet-4-6")
    )

    for rid in review_ids:
        async with sm() as session:
            t0 = time.perf_counter()
            await FilteringService(session).decide(rid)
            timings["filter"].append(time.perf_counter() - t0)

        async with sm() as session:
            t0 = time.perf_counter()
            try:
                response = await GenerationService(session, provider=llm).generate_for_review(rid)
            except Exception:
                continue
            timings["generate"].append(time.perf_counter() - t0)
            response_id = response.id

        async with sm() as session:
            from app.models.response import Response

            response_row = await session.get(Response, response_id)
            if response_row is None:
                continue
            pub = PublicationService(session, adapter=google_adapter)
            t0 = time.perf_counter()
            scheduled = await pub.schedule_publication(response_id, validated_by_user_id=user_id)
            scheduled.scheduled_at = datetime.now(UTC) - timedelta(minutes=10)
            scheduled.undo_deadline_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()
            await pub.publish_now(scheduled)
            timings["publish"].append(time.perf_counter() - t0)
    return timings


async def _bootstrap_client() -> tuple[UUID, UUID]:
    """Provision a fresh client + user + settings + subscription + location + oauth."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.database import get_engine

    sm = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    async with sm() as session:
        # Reuse the helper for parity with tests
        from tests.factories import create_full_client

        client, user, *_ = await create_full_client(session)
        await session.commit()
        return client.id, user.id


async def _ensure_prompt() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.database import get_engine
    from app.models.prompt_version import PromptVersion

    sm = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    async with sm() as session:
        existing = (
            await session.scalars(select(PromptVersion).where(PromptVersion.is_active.is_(True)))
        ).first()
        if existing:
            return
        session.add(
            PromptVersion(
                version="load-v1",
                system_prompt="You are a helpful business reply assistant.",
                user_prompt_template="Reply to: $review_comment",
                model="claude-sonnet-4-6",
                temperature=Decimal("0.70"),
                max_tokens=600,
                is_active=True,
            )
        )
        await session.commit()


async def run(n_clients: int, n_reviews: int) -> dict[str, Any]:
    await _ensure_prompt()
    bootstrap_t0 = time.perf_counter()
    pairs = await asyncio.gather(*[_bootstrap_client() for _ in range(n_clients)])
    bootstrap_elapsed = time.perf_counter() - bootstrap_t0

    poll_t0 = time.perf_counter()
    poll_results = await asyncio.gather(*[_stage_polling(cid, n_reviews) for cid, _uid in pairs])
    poll_elapsed = time.perf_counter() - poll_t0

    pipeline_t0 = time.perf_counter()
    all_timings = await asyncio.gather(
        *[
            _stage_filter_generate_publish(cid, ids, uid)
            for (cid, uid), (_, ids) in zip(pairs, poll_results, strict=True)
        ]
    )
    pipeline_elapsed = time.perf_counter() - pipeline_t0

    def stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"n": 0, "p50": 0.0, "p95": 0.0, "max": 0.0, "mean": 0.0}
        sv = sorted(values)
        return {
            "n": len(sv),
            "p50": sv[len(sv) // 2],
            "p95": sv[int(len(sv) * 0.95)],
            "max": sv[-1],
            "mean": statistics.mean(sv),
        }

    aggregated: dict[str, list[float]] = {"filter": [], "generate": [], "publish": []}
    for t in all_timings:
        for stage, values in t.items():
            aggregated[stage].extend(values)

    return {
        "clients": n_clients,
        "reviews_per_client": n_reviews,
        "bootstrap_seconds": round(bootstrap_elapsed, 3),
        "polling_seconds": round(poll_elapsed, 3),
        "pipeline_seconds": round(pipeline_elapsed, 3),
        "polling_latency_s": stats([t for t, _ in poll_results]),
        "stage_latency_s": {k: stats(v) for k, v in aggregated.items()},
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--clients", type=int, default=20)
    p.add_argument("--reviews", type=int, default=5)
    args = p.parse_args()
    report = asyncio.run(run(args.clients, args.reviews))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
