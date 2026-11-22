import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, DatabaseError
from sqlalchemy.dialects.postgresql import insert

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import ClickEvent
from app.config import settings

logger = logging.getLogger("worker")

# Aliases for Celery CLI discovery (-A app.worker)
app = celery_app
celery = celery_app


@celery_app.task(
    bind=True,
    name="app.worker.record_click_event_task",
    max_retries=3,
    default_retry_delay=5,
)
def record_click_event_task(self, click_data: dict):
    """
    Background worker task to record a click event into PostgreSQL.
    Guarantees idempotency via unique click_event_id and handles retries gracefully.
    """
    click_event_id = click_data.get("click_event_id")
    link_id = click_data.get("link_id")
    clicked_at_raw = click_data.get("clicked_at")
    user_agent = click_data.get("user_agent")
    referrer = click_data.get("referrer")
    ip_hash = click_data.get("ip_hash")

    if not link_id:
        logger.warning(f"Discarding malformed click event without link_id: {click_data}")
        return {"status": "dropped", "reason": "missing_link_id"}

    if clicked_at_raw:
        try:
            clicked_at_dt = datetime.fromisoformat(clicked_at_raw)
            if clicked_at_dt.tzinfo is None:
                clicked_at_dt = clicked_at_dt.replace(tzinfo=timezone.utc)
        except Exception:
            clicked_at_dt = datetime.now(timezone.utc)
    else:
        clicked_at_dt = datetime.now(timezone.utc)

    db: Session = SessionLocal()
    try:
        # Atomic idempotency: insert with ON CONFLICT (click_event_id) DO NOTHING
        stmt = insert(ClickEvent).values(
            click_event_id=click_event_id,
            link_id=link_id,
            clicked_at=clicked_at_dt,
            user_agent=user_agent[:512] if user_agent else None,
            referrer=referrer[:1024] if referrer else None,
            ip_hash=ip_hash,
        )
        if click_event_id:
            stmt = stmt.on_conflict_do_nothing(index_elements=["click_event_id"])
        stmt = stmt.returning(ClickEvent.id)

        result = db.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        db.commit()

        if inserted_id is None and click_event_id:
            logger.info(f"Duplicate click event ignored for click_event_id={click_event_id}")
            return {"status": "deduplicated", "click_event_id": click_event_id}

        return {"status": "recorded", "click_event_id": click_event_id, "link_id": link_id, "id": inserted_id}

    except (OperationalError, DatabaseError) as exc:
        db.rollback()
        logger.error(f"Database operational error recording click event: {exc}")
        raise self.retry(exc=exc)
    except Exception as exc:
        db.rollback()
        logger.error(f"Unexpected error recording click event: {exc}")
        raise
    finally:
        db.close()


@celery_app.task(
    name="app.worker.purge_expired_clicks_task"
)
def purge_expired_clicks_task(retention_days: Optional[int] = None):
    """
    Retention cleanup task: permanently deletes click events older than retention_days.
    """
    days = retention_days if retention_days is not None else settings.retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    db: Session = SessionLocal()
    try:
        deleted = (
            db.query(ClickEvent)
            .filter(ClickEvent.clicked_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(f"Purged {deleted} click events older than {cutoff.isoformat()} (retention={days}d)")
        return {"status": "purged", "deleted_count": deleted, "cutoff": cutoff.isoformat()}
    except Exception as exc:
        db.rollback()
        logger.error(f"Error purging expired clicks: {exc}")
        raise
    finally:
        db.close()
