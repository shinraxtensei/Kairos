"""Celery app and beat schedule.

Worker:  celery -A kairos.celery_app worker --loglevel=info
Beat:    celery -A kairos.celery_app beat --loglevel=info

Redis is the only broker (CONTEXT.md §3.1). Cross-context communication goes
through here or through application-service calls — never through shared tables.
"""

from celery import Celery
from celery.schedules import crontab

from kairos.config import get_settings
from kairos.observability import configure_logging

configure_logging()
settings = get_settings()

celery_app = Celery(
    "kairos",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # The composition root: every context's task module is registered here.
    # Imported lazily at worker start, so contexts still import celery_app.
    include=[
        "kairos.trend_discovery.infrastructure.tasks",
        "kairos.niche_ranking.infrastructure.tasks",
    ],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    timezone="UTC",
    enable_utc=True,
    # ENG-22. Daily on purpose — nothing about niche discovery is real-time, and
    # every extra run spends quota against sources that rate-limit.
    beat_schedule={
        "collect-trend-signals-daily": {
            "task": "kairos.trend_discovery.collect",
            "schedule": crontab(hour=6, minute=0),
        },
    },
)


@celery_app.task(name="kairos.ping")
def ping() -> str:
    """Proves the broker round-trip works. Keep it until a real task replaces it."""
    return "pong"
