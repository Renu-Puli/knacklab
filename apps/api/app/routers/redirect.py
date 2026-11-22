import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Link, ClickEvent
from app.rate_limiter import rate_limit_redirect
from app.cache import get_redirect_target, set_redirect_target
from app.worker import record_click_event_task

logger = logging.getLogger("redirect")
router = APIRouter(tags=["Redirect"])


def extract_ip_hash(request: Request) -> str:
    """Hash client IP using SHA-256 for privacy protection."""
    client_host = request.client.host if request.client else "unknown"
    # Respect forwarded headers if present
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_host = forwarded_for.split(",")[0].strip()
    return hashlib.sha256(client_host.encode("utf-8")).hexdigest()


def _dispatch_click_event(link_id: int, request: Request):
    """Enqueue click event to background Celery queue without blocking redirect."""
    try:
        request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or uuid.uuid4().hex
        click_event_id = f"click_{request_id}"
        user_agent = request.headers.get("User-Agent")
        referrer = request.headers.get("Referer")
        ip_hash = extract_ip_hash(request)

        payload = {
            "click_event_id": click_event_id,
            "link_id": link_id,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
            "user_agent": user_agent[:512] if user_agent else None,
            "referrer": referrer[:1024] if referrer else None,
            "ip_hash": ip_hash,
        }
        record_click_event_task.delay(payload)
    except Exception as e:
        # Queue/broker failures must never degrade public redirect availability
        logger.warning(f"Failed to enqueue click event for link {link_id}: {e}")


def _resolve_sync(code: str, request: Request, db: Session) -> str:
    """Direct synchronous link resolution via PostgreSQL."""
    rate_limit_redirect(request)
    link = db.query(Link).filter(Link.code == code).first()
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short code not found"
        )

    if link.expires_at is not None:
        now = datetime.now(timezone.utc)
        expires_at = (
            link.expires_at
            if link.expires_at.tzinfo is not None
            else link.expires_at.replace(tzinfo=timezone.utc)
        )
        if expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Short link has expired"
            )

    _dispatch_click_event(link.id, request)

    return link.long_url


async def _resolve_async(
    code: str,
    request: Request,
    link_info: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> RedirectResponse:
    """Asynchronous link resolution with Redis cache-aside and PostgreSQL fallback."""
    rate_limit_redirect(request)

    # 1. Cache-aside lookup: check Redis first (No DB connection needed or held)
    cached = await get_redirect_target(code)
    if cached is not None:
        target_url = cached.get("long_url")
        link_id = cached.get("link_id")

        if link_id:
            _dispatch_click_event(link_id, request)

        return RedirectResponse(
            url=target_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    # 2. Cache miss or Redis unavailable: lookup link in PostgreSQL with strictly scoped session
    if link_info is None:
        if db is not None:
            link = db.query(Link).filter(Link.code == code).first()
            if not link:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Short code not found"
                )
            link_info = {
                "id": link.id,
                "code": link.code,
                "long_url": link.long_url,
                "created_by": link.created_by,
                "expires_at": link.expires_at,
            }
        else:
            with SessionLocal() as session:
                link = session.query(Link).filter(Link.code == code).first()
                if not link:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Short code not found"
                    )
                link_info = {
                    "id": link.id,
                    "code": link.code,
                    "long_url": link.long_url,
                    "created_by": link.created_by,
                    "expires_at": link.expires_at,
                }
                # Connection is returned to pool immediately upon exiting 'with' block

    # 3. Check expiration if configured
    expires_at = link_info.get("expires_at")
    if expires_at is not None:
        now = datetime.now(timezone.utc)
        expires_at_dt = (
            expires_at
            if expires_at.tzinfo is not None
            else expires_at.replace(tzinfo=timezone.utc)
        )
        if expires_at_dt <= now:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Short link has expired"
            )

    # 4. Populate cache (cache-aside) with organization scoping (DB connection is NOT held)
    await set_redirect_target(
        code=link_info["code"],
        long_url=link_info["long_url"],
        ttl_seconds=3600,
        org_id=link_info["created_by"],
        link_id=link_info["id"],
        expires_at=link_info.get("expires_at"),
    )

    # 5. Non-blocking asynchronous click event tracking (DB connection is NOT held)
    _dispatch_click_event(link_info["id"], request)

    return RedirectResponse(
        url=link_info["long_url"],
        status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


class DualRedirectResponse(RedirectResponse):
    """
    Dual-mode redirect response supporting both synchronous direct function invocations
    and asynchronous HTTP ASGI pipelines.
    """
    def __init__(self, code: str, request: Request, db: Optional[Session] = None):
        self._status_code = status.HTTP_307_TEMPORARY_REDIRECT
        self.code = code
        self.request = request
        self._sync_recorded = False

        # Validate existence and expiration synchronously so direct unit tests raise 404/410 immediately.
        # DB session is scoped and closed immediately so connections are not held during async execution.
        should_close = False
        session = db
        if session is None:
            session = SessionLocal()
            should_close = True

        try:
            link = session.query(Link).filter(Link.code == code).first()
            if not link:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Short code not found"
                )

            if link.expires_at is not None:
                now = datetime.now(timezone.utc)
                expires_at = (
                    link.expires_at
                    if link.expires_at.tzinfo is not None
                    else link.expires_at.replace(tzinfo=timezone.utc)
                )
                if expires_at <= now:
                    raise HTTPException(
                        status_code=status.HTTP_410_GONE,
                        detail="Short link has expired"
                    )

            self.link = link
            self.link_info = {
                "id": link.id,
                "code": link.code,
                "long_url": link.long_url,
                "created_by": link.created_by,
                "expires_at": link.expires_at,
            }
        finally:
            if db is not None:
                db.close()
            if should_close:
                session.close()

        super().__init__(url=self.link_info["long_url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    def _record_sync_click(self):
        if not self._sync_recorded:
            self._sync_recorded = True
            _dispatch_click_event(self.link_info["id"], self.request)

    @property
    def status_code(self):
        self._record_sync_click()
        return self._status_code

    @status_code.setter
    def status_code(self, value):
        self._status_code = value

    @property
    def headers(self):
        self._record_sync_click()
        return super().headers

    def __await__(self):
        async def _wrapper():
            return await _resolve_async(self.code, self.request, self.link_info)
        return _wrapper().__await__()

    async def __call__(self, scope, receive, send):
        # In ASGI, prevent sync click from firing and let _resolve_async handle it
        self._sync_recorded = True
        real_resp = await _resolve_async(self.code, self.request, self.link_info)
        await real_resp(scope, receive, send)


@router.get("/r/{code}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def redirect_short_code(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    return DualRedirectResponse(code, request, db)
