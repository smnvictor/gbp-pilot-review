from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]
from celery.signals import task_postrun, task_prerun  # type: ignore[import-untyped]

from app.config import get_settings
from app.utils.correlation import correlation_id_var, new_correlation_id

settings = get_settings()

celery_app = Celery(
    "gbp_review_manager",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=[
        "app.tasks.polling_tasks",
        "app.tasks.generation_tasks",
        "app.tasks.publication_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.oauth_tasks",
        "app.tasks.maintenance_tasks",
        "app.tasks.digest_tasks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Europe/Paris so the fixed polling slots below fire at local business hours.
    timezone="Europe/Paris",
    enable_utc=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
    task_default_queue="default",
    task_routes={
        "app.tasks.polling_tasks.*": {"queue": "polling"},
        "app.tasks.generation_tasks.*": {"queue": "generation"},
        "app.tasks.publication_tasks.*": {"queue": "publication"},
        "app.tasks.notification_tasks.*": {"queue": "notification"},
        "app.tasks.digest_tasks.*": {"queue": "notification"},
        "app.tasks.oauth_tasks.*": {"queue": "default"},
        "app.tasks.maintenance_tasks.*": {"queue": "default"},
    },
    beat_schedule={
        "dispatch-pollings": {
            "task": "app.tasks.polling_tasks.dispatch_pollings",
            # Fixed 4 runs/day (11h, 14h, 17h, 20h Europe/Paris) — polling frequency
            # is no longer client-configurable.
            "schedule": crontab(hour="11,14,17,20", minute=0),
        },
        "dispatch-publications": {
            "task": "app.tasks.publication_tasks.dispatch_due_publications",
            "schedule": 60,
        },
        "refresh-oauth": {
            "task": "app.tasks.oauth_tasks.refresh_expiring_tokens",
            "schedule": 60 * 30,
        },
        "send-digests": {
            "task": "app.tasks.notification_tasks.send_pending_digests",
            "schedule": 60 * 15,
        },
        "quota-thresholds": {
            "task": "app.tasks.maintenance_tasks.check_quota_thresholds",
            "schedule": crontab(hour=9, minute=0),
        },
        "purge-expired": {
            "task": "app.tasks.maintenance_tasks.purge_expired_data",
            "schedule": crontab(hour=3, minute=15),
        },
    },
)


@task_prerun.connect
def _bind_correlation(task_id, task, args, kwargs, **_):  # type: ignore[no-untyped-def]
    cid = (kwargs or {}).pop("__correlation_id", None) or new_correlation_id()
    correlation_id_var.set(cid)


@task_postrun.connect
def _unbind_correlation(**_):  # type: ignore[no-untyped-def]
    correlation_id_var.set("-")


# Importing the DLQ module registers its task_failure signal handler.
from app.services import dlq_service as _dlq_service  # noqa: E402, F401
