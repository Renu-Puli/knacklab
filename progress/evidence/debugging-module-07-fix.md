# Debugging & Incident Response — Module 07: Fix

**Track**: `debugging-incident-response`  
**Module**: 07 — Background Jobs & Analytics Decoupling  
**Step**: STEP 4 — FIX  
**Status**: COMPLETED  

---

## 1. Root Cause Analysis
In `apps/api/app/worker.py`, the `record_click_event_task` function executed a standard SQLAlchemy `db.add(ClickEvent(...))` without checking whether `click_event_id` already existed. In distributed Celery setups, workers can experience transient network blips after DB commit but before task acknowledgment, triggering automatic message re-queuing and duplicate execution.

---

## 2. Minimal Fix Implemented
1. **Atomic Idempotent Insertion (`ON CONFLICT DO NOTHING`)**:
   In `apps/api/app/worker.py`:
   ```python
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
   ```
2. **Queue Failure Resilience**:
   In `apps/api/app/routers/redirect.py`:
   ```python
   try:
       record_click_event_task.delay(click_payload)
   except Exception as exc:
       logger.warning(f"Failed to enqueue click event for link {link.id}: {exc}")
       # Do NOT fail redirect; return HTTP 307 normally
   ```
3. **Data Retention Cleanup**:
   In `apps/api/app/worker.py`, implemented `purge_expired_clicks_task`:
   ```python
   @celery_app.task(name="app.worker.purge_expired_clicks_task")
   def purge_expired_clicks_task(retention_days: Optional[int] = None):
       days = retention_days if retention_days is not None else settings.retention_days
       cutoff = datetime.now(timezone.utc) - timedelta(days=days)
       db: Session = SessionLocal()
       try:
           deleted = db.query(ClickEvent).filter(ClickEvent.clicked_at < cutoff).delete()
           db.commit()
           logger.info(f"Purged {deleted} click events older than {cutoff.isoformat()}")
           return {"status": "purged", "count": deleted}
       finally:
           db.close()
   ```

---

## 3. Backups Created
- `apps/api/app/worker.py.bak`
