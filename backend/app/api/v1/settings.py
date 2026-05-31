from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser
from app.database import SessionDep
from app.models.client import Client
from app.models.client_settings import ClientSettings
from app.repositories.client_settings_repository import ClientSettingsRepository
from app.schemas.settings import (
    CLIENT_PROFILE_FIELDS,
    ClientSettingsPublic,
    ClientSettingsUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _public(settings: ClientSettings, client: Client) -> ClientSettingsPublic:
    return ClientSettingsPublic(
        publish_delay_range=settings.publish_delay_range,
        publish_window_start=settings.publish_window_start,
        publish_window_end=settings.publish_window_end,
        publish_window_timezone=settings.publish_window_timezone,
        language_override=settings.language_override,
        no_text_review_policy=settings.no_text_review_policy,
        validation_mode=settings.validation_mode,
        digest_mode=settings.digest_mode,
        digest_hour=settings.digest_hour,
        regex_blocklist=settings.regex_blocklist,
        tone=client.tone,
        business_context=client.business_context,
        always_mention=client.always_mention,
        never_mention=client.never_mention,
    )


@router.get("", response_model=ClientSettingsPublic)
async def get_settings_(session: SessionDep, user: CurrentUser) -> ClientSettingsPublic:
    if user.client_id is None:
        raise HTTPException(404, "User has no client")
    settings = await ClientSettingsRepository(session).get_by_client(user.client_id)
    client = await session.get(Client, user.client_id)
    if settings is None or client is None:
        raise HTTPException(404, "Settings not found")
    return _public(settings, client)


@router.patch("", response_model=ClientSettingsPublic)
async def patch_settings(
    payload: ClientSettingsUpdate, session: SessionDep, user: CurrentUser
) -> ClientSettingsPublic:
    if user.client_id is None:
        raise HTTPException(404, "User has no client")
    settings = await ClientSettingsRepository(session).get_by_client(user.client_id)
    client = await session.get(Client, user.client_id)
    if settings is None or client is None:
        raise HTTPException(404, "Settings not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        target = client if key in CLIENT_PROFILE_FIELDS else settings
        setattr(target, key, value)
    await session.commit()
    return _public(settings, client)
