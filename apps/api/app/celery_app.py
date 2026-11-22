import os
import logging
from celery import Celery
from app.config import settings

logger = logging.getLogger("celery_app")

broker_url = (
    os.getenv("CELERY_BROKER_URL")
    or os.getenv("REDIS_URL")
    or getattr(settings, "celery_broker_url", None)
    or getattr(settings, "redis_url", None)
    or "redis://localhost:6379/0"
)

if broker_url.startswith("redis://") and broker_url.count("/") == 2:
    broker_url = broker_url.rstrip("/") + "/0"

celery_app = Celery(
    "analytics_worker",
    broker=broker_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
)
