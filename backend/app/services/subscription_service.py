from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubscriptionStatus, SubscriptionTier
from app.models.subscription import Subscription
from app.models.webhook_event import WebhookEvent
from app.repositories.subscription_repository import SubscriptionRepository

# Map Lemon Squeezy variant_id → tier (configured per store).
# In production, store this mapping in a config table or .env. Stub default:
TIER_QUOTAS = {
    SubscriptionTier.starter: 10,
    SubscriptionTier.pro: 50,
    SubscriptionTier.business: 1_000_000,
}


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subs = SubscriptionRepository(session)

    async def is_event_processed(self, event_id: str, provider: str = "lemonsqueezy") -> bool:
        stmt = select(WebhookEvent).where(
            WebhookEvent.provider == provider,
            WebhookEvent.event_id == event_id,
            WebhookEvent.processed_at.is_not(None),
        )
        return (await self.session.scalars(stmt)).first() is not None

    async def record_event(
        self, *, event_id: str, event_type: str, payload: dict[str, Any]
    ) -> WebhookEvent:
        event = WebhookEvent(
            provider="lemonsqueezy",
            event_id=event_id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def handle_event(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if await self.is_event_processed(event_id):
            logger.info("Lemon Squeezy event {eid} already processed, skipping", eid=event_id)
            return

        event = await self.record_event(event_id=event_id, event_type=event_type, payload=payload)
        try:
            data = payload.get("data", {})
            attrs = data.get("attributes", {})
            custom = payload.get("meta", {}).get("custom_data", {})
            client_id_str = custom.get("client_id")
            if client_id_str is None:
                event.processing_error = "Missing client_id in custom_data"
                event.processed_at = datetime.now(UTC)
                await self.session.commit()
                return
            client_id = UUID(client_id_str)

            if event_type in ("subscription_created", "subscription_updated", "order_created"):
                await self._upsert_subscription(client_id, attrs)
            elif event_type in ("subscription_cancelled", "subscription_expired"):
                await self._cancel(client_id, attrs)
            elif event_type == "subscription_payment_failed":
                await self._mark_past_due(client_id)
            elif event_type == "subscription_payment_success":
                await self._mark_active(client_id, attrs)
            else:
                logger.info("Unhandled Lemon Squeezy event type {t}", t=event_type)

            event.processed_at = datetime.now(UTC)
        except Exception as exc:
            event.processing_error = str(exc)[:1000]
            raise
        finally:
            await self.session.commit()

    async def _upsert_subscription(self, client_id: UUID, attrs: dict[str, Any]) -> Subscription:
        sub = await self.subs.get_by_client(client_id)
        tier = self._tier_from_attrs(attrs)
        quota = TIER_QUOTAS[tier]
        if sub is None:
            sub = Subscription(
                client_id=client_id,
                tier=tier,
                status=SubscriptionStatus.active,
                lemonsqueezy_subscription_id=str(attrs.get("subscription_id") or ""),
                lemonsqueezy_customer_id=str(attrs.get("customer_id") or ""),
                monthly_response_quota=quota,
            )
            self.session.add(sub)
        else:
            sub.tier = tier
            sub.status = SubscriptionStatus.active
            sub.monthly_response_quota = quota
            if attrs.get("subscription_id"):
                sub.lemonsqueezy_subscription_id = str(attrs["subscription_id"])
            if attrs.get("customer_id"):
                sub.lemonsqueezy_customer_id = str(attrs["customer_id"])
        await self.session.flush()
        return sub

    async def _cancel(self, client_id: UUID, attrs: dict[str, Any]) -> None:
        sub = await self.subs.get_by_client(client_id)
        if sub is None:
            return
        sub.status = SubscriptionStatus.cancelled
        sub.cancelled_at = datetime.now(UTC)
        await self.session.flush()

    async def _mark_past_due(self, client_id: UUID) -> None:
        sub = await self.subs.get_by_client(client_id)
        if sub is None:
            return
        sub.status = SubscriptionStatus.past_due
        await self.session.flush()

    async def _mark_active(self, client_id: UUID, attrs: dict[str, Any]) -> None:
        sub = await self.subs.get_by_client(client_id)
        if sub is None:
            return
        sub.status = SubscriptionStatus.active
        if attrs.get("renews_at"):
            sub.current_period_end = attrs["renews_at"]
        await self.session.flush()

    @staticmethod
    def _tier_from_attrs(attrs: dict[str, Any]) -> SubscriptionTier:
        # Heuristic: Lemon Squeezy passes product_name / variant_name in attributes.
        name = (attrs.get("product_name", "") or attrs.get("variant_name", "")).lower()
        if "business" in name:
            return SubscriptionTier.business
        if "pro" in name:
            return SubscriptionTier.pro
        return SubscriptionTier.starter
