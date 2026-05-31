import httpx

from app.config import get_settings


class LemonSqueezyError(Exception):
    pass


class LemonSqueezyClient:
    BASE_URL = "https://api.lemonsqueezy.com/v1"

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http or httpx.AsyncClient(timeout=15.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        settings = get_settings()
        return {
            "Authorization": f"Bearer {settings.lemonsqueezy_api_key.get_secret_value()}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }

    async def create_checkout(
        self, *, variant_id: str, customer_email: str, custom: dict[str, str]
    ) -> str:
        settings = get_settings()
        payload = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "checkout_data": {
                        "email": customer_email,
                        "custom": custom,
                    }
                },
                "relationships": {
                    "store": {"data": {"type": "stores", "id": settings.lemonsqueezy_store_id}},
                    "variant": {"data": {"type": "variants", "id": variant_id}},
                },
            }
        }
        try:
            response = await self._http.post(
                f"{self.BASE_URL}/checkouts", headers=self._headers(), json=payload
            )
        except httpx.HTTPError as exc:
            raise LemonSqueezyError(str(exc)) from exc
        if response.status_code >= 400:
            raise LemonSqueezyError(f"Lemon Squeezy {response.status_code}: {response.text[:200]}")
        return str(response.json()["data"]["attributes"]["url"])
