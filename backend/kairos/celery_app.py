"""Celery app and beat schedule.

Worker:  celery -A kairos.celery_app worker --loglevel=info
Beat:    celery -A kairos.celery_app beat --loglevel=info

Redis is the only broker (CONTEXT.md §3.1). Cross-context communication goes
through here or through application-service calls — never through shared tables.
"""

from celery import Celery

from kairos.config import get_settings

settings = get_settings()

celery_app = Celery("kairos", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="kairos.ping")
def ping() -> str:
    """Proves the broker round-trip works. Keep it until a real task replaces it."""
    return "pong"
