from fastapi import APIRouter

from app.api.v1 import (
    auth,
    generation_preview,
    me,
    oauth,
    responses,
    reviews,
    subscription,
    webhooks,
)
from app.api.v1 import settings as settings_routes
from app.api.v1.admin import (
    clients as admin_clients,
)
from app.api.v1.admin import (
    deletions as admin_deletions,
)
from app.api.v1.admin import (
    monitoring,
    validation_queue,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(oauth.router)
api_router.include_router(responses.router)
api_router.include_router(reviews.router)
api_router.include_router(settings_routes.router)
api_router.include_router(validation_queue.router)
api_router.include_router(monitoring.router)
api_router.include_router(subscription.router)
api_router.include_router(generation_preview.router)
api_router.include_router(webhooks.router)
api_router.include_router(admin_clients.router)
api_router.include_router(admin_deletions.router)
