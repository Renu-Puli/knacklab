import string
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, text, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import get_db
from app.models import Link, ClickEvent
from app.schemas.link import (
    LinkCreate,
    LinkResponse,
    LinkUpdate,
    LinkAnalyticsResponse,
    BatchAnalyticsResponse,
    BatchAnalyticsItem,
)
from app.auth import require_api_key, Principal
from app.rate_limiter import rate_limit_link_creation
from app.cache import invalidate_redirect_target

router = APIRouter(prefix="/links", tags=["Links"])

CODE_CHARS = string.ascii_letters + string.digits


def generate_short_code(db: Session, length: int = 7) -> str:
    """Generate a collision-resistant unique short code."""
    for _ in range(10):
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(length))
        if not db.query(Link).filter_by(code=code).first():
            return code
    # Fallback to longer code if high collision rate
    return "".join(secrets.choice(CODE_CHARS) for _ in range(length + 2))


@router.post("", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(
    payload: LinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    tenant_id: Optional[str] = None,
):
    # Support backward-compatibility for direct unit test calls specifying tenant_id
    effective_principal = Principal(principal_id=tenant_id, org_id=tenant_id) if tenant_id else principal

    # Enforce rate limiting: 30 link creations per minute per authenticated API key
    rate_limit_link_creation(effective_principal)

    tags_str = ",".join(payload.tags) if payload.tags else None

    # Retry loop in case of concurrent code generation collision
    max_retries = 3
    for attempt in range(max_retries):
        code = generate_short_code(db)
        link = Link(
            code=code,
            long_url=payload.long_url,
            created_by=effective_principal.org_id,
            expires_at=payload.expires_at,
            tags=tags_str,
            title=payload.title,
            is_active=payload.is_active if payload.is_active is not None else True,
        )
        try:
            db.add(link)
            db.commit()
            db.refresh(link)
            break
        except IntegrityError:
            db.rollback()
            if attempt == max_retries - 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate a unique short code. Please try again."
                )
        except Exception:
            db.rollback()
            raise

    base_url = str(request.base_url).rstrip("/")
    short_url = f"{base_url}/r/{link.code}"

    return LinkResponse(
        id=link.id,
        code=link.code,
        short_url=short_url,
        long_url=link.long_url,
        created_by=link.created_by,
        created_at=link.created_at,
        expires_at=link.expires_at,
        tags=link.tags,
        title=link.title,
        is_active=link.is_active,
    )


@router.get("", response_model=List[LinkResponse])
def list_links(
    request: Request,
    skip: Optional[int] = Query(default=None, ge=0, description="Pagination offset"),
    page: Optional[int] = Query(default=None, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    # Advanced search and filtering parameters
    query: Optional[str] = Query(default=None, max_length=100, description="Keyword search in URL or code"),
    tag: Optional[str] = Query(default=None, max_length=30, description="Filter by tag"),
    status_filter: Optional[str] = Query(default=None, alias="status", regex="^(active|expired)$", description="Filter by active/expired status"),
    # Keyset / cursor pagination parameter (ID of the last item from previous page)
    cursor_id: Optional[int] = Query(default=None, ge=1, description="Keyset cursor: return items with id < cursor_id"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    tenant_id: Optional[str] = None,
):
    effective_org = tenant_id if tenant_id else principal.org_id

    # Base query strictly scoped to tenant
    q = db.query(Link).filter(Link.created_by == effective_org)

    # 1. Keyword search (URL or code)
    if query:
        search_pattern = f"%{query.strip()}%"
        q = q.filter(or_(Link.long_url.ilike(search_pattern), Link.code.ilike(search_pattern)))

    # 2. Tag filter
    if tag:
        tag_clean = tag.strip()
        q = q.filter(Link.tags.ilike(f"%{tag_clean}%"))

    # 3. Status filter (active vs expired)
    now = datetime.now(timezone.utc)
    if status_filter == "active":
        q = q.filter(or_(Link.expires_at == None, Link.expires_at > now))
    elif status_filter == "expired":
        q = q.filter(Link.expires_at != None, Link.expires_at <= now)

    # 4. Keyset cursor vs Offset pagination
    if cursor_id is not None:
        # Keyset pagination utilizes the index directly (O(1) seek)
        q = q.filter(Link.id < cursor_id).order_by(Link.created_at.desc(), Link.id.desc()).limit(limit)
    else:
        # Standard offset pagination
        if page is not None:
            computed_offset = (page - 1) * limit
        elif skip is not None:
            computed_offset = skip
        else:
            computed_offset = 0

        q = q.order_by(Link.created_at.desc(), Link.id.desc()).offset(computed_offset).limit(limit)

    links = q.all()

    base_url = str(request.base_url).rstrip("/")
    return [
        LinkResponse(
            id=l.id,
            code=l.code,
            short_url=f"{base_url}/r/{l.code}",
            long_url=l.long_url,
            created_by=l.created_by,
            created_at=l.created_at,
            expires_at=l.expires_at,
            tags=l.tags,
            title=l.title,
            is_active=l.is_active,
        )
        for l in links
    ]


@router.get("/analytics/batch", response_model=BatchAnalyticsResponse)
def get_batch_analytics(
    request: Request,
    link_ids: str = Query(..., description="Comma-separated list of link IDs"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    tenant_id: Optional[str] = None,
):
    """
    Optimized batch analytics endpoint to eliminate N+1 queries.
    Aggregates click metrics for up to 50 links in a single SQL query.
    """
    effective_org = tenant_id if tenant_id else principal.org_id

    # Parse and validate link IDs
    try:
        parsed_ids = [int(i.strip()) for i in link_ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="link_ids must be a comma-separated list of integers"
        )

    if not parsed_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No link IDs provided")

    if len(parsed_ids) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot query more than 50 links at once")

    # Verify tenant ownership of all requested links (anti-enumeration / tenant isolation)
    owned_links = (
        db.query(Link.id)
        .filter(Link.id.in_(parsed_ids), Link.created_by == effective_org)
        .all()
    )
    valid_ids = [row[0] for row in owned_links]

    if not valid_ids:
        return BatchAnalyticsResponse(items=[], total_links_queried=0)

    # Perform single aggregate query (GROUP BY link_id) to eliminate N+1 roundtrips
    results = (
        db.query(
            ClickEvent.link_id,
            func.count(ClickEvent.id).label("total_clicks"),
            func.max(ClickEvent.clicked_at).label("last_clicked_at"),
        )
        .filter(ClickEvent.link_id.in_(valid_ids))
        .group_by(ClickEvent.link_id)
        .all()
    )

    result_map = {r.link_id: (r.total_clicks, r.last_clicked_at) for r in results}

    items = []
    for lid in valid_ids:
        total_clicks, last_clicked = result_map.get(lid, (0, None))
        items.append(
            BatchAnalyticsItem(
                link_id=lid,
                total_clicks=total_clicks,
                last_clicked_at=last_clicked,
            )
        )

    return BatchAnalyticsResponse(items=items, total_links_queried=len(items))


@router.get("/{link_id}/analytics", response_model=LinkAnalyticsResponse)
def get_link_analytics(
    link_id: int,
    request: Request,
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD or ISO)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD or ISO)"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    tenant_id: Optional[str] = None,
):
    effective_org = tenant_id if tenant_id else principal.org_id

    # 1. Enforce tenant ownership (404 for cross-tenant or non-existent)
    link = (
        db.query(Link)
        .filter(Link.id == link_id, Link.created_by == effective_org)
        .first()
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found"
        )

    # 2. Parse date range
    now = datetime.now(timezone.utc)
    if from_date:
        try:
            start_dt = datetime.fromisoformat(from_date)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid 'from' date format. Use YYYY-MM-DD or ISO 8601."
            )
    else:
        start_dt = now - timedelta(days=settings.retention_days)

    if to_date:
        try:
            if len(to_date) == 10 and to_date.count("-") == 2:
                end_dt = datetime.fromisoformat(to_date + "T23:59:59.999999+00:00")
            else:
                end_dt = datetime.fromisoformat(to_date)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid 'to' date format. Use YYYY-MM-DD or ISO 8601."
            )
    else:
        end_dt = now

    if start_dt > end_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' date must be before or equal to 'to' date."
        )

    # 3. Query ClickEvent metrics using composite index ix_click_events_link_clicked
    result = (
        db.query(
            func.count(ClickEvent.id).label("total_clicks"),
            func.max(ClickEvent.clicked_at).label("last_clicked_at"),
        )
        .filter(
            ClickEvent.link_id == link.id,
            ClickEvent.clicked_at >= start_dt,
            ClickEvent.clicked_at <= end_dt,
        )
        .first()
    )

    total_clicks = result.total_clicks if result and result.total_clicks else 0
    last_clicked_at = result.last_clicked_at if result else None

    return LinkAnalyticsResponse(
        link_id=link.id,
        from_date=start_dt.isoformat(),
        to_date=end_dt.isoformat(),
        total_clicks=total_clicks,
        last_clicked_at=last_clicked_at,
    )


@router.get("/{link_id}", response_model=LinkResponse)
def get_link_by_id(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    tenant_id: Optional[str] = None,
):
    effective_org = tenant_id if tenant_id else principal.org_id

    # Enforce tenant scoping & not_owner_status = 404:
    link = (
        db.query(Link)
        .filter(Link.id == link_id, Link.created_by == effective_org)
        .first()
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found"
        )

    base_url = str(request.base_url).rstrip("/")
    return LinkResponse(
        id=link.id,
        code=link.code,
        short_url=f"{base_url}/r/{link.code}",
        long_url=link.long_url,
        created_by=link.created_by,
        created_at=link.created_at,
        expires_at=link.expires_at,
        tags=link.tags,
        title=link.title,
        is_active=link.is_active,
    )


@router.patch("/{link_id}", response_model=LinkResponse)
async def update_link(
    link_id: int,
    payload: LinkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    tenant_id: Optional[str] = None,
):
    effective_org = tenant_id if tenant_id else principal.org_id

    link = (
        db.query(Link)
        .filter(Link.id == link_id, Link.created_by == effective_org)
        .first()
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found"
        )

    updated = False
    if payload.long_url is not None:
        link.long_url = payload.long_url
        updated = True
    if payload.expires_at is not None:
        link.expires_at = payload.expires_at
        updated = True
    if payload.tags is not None:
        link.tags = ",".join(payload.tags) if payload.tags else None
        updated = True

    if payload.title is not None:
        link.title = payload.title
        updated = True
    if payload.is_active is not None:
        link.is_active = payload.is_active
        updated = True

    if updated:
        try:
            db.commit()
            db.refresh(link)
        except Exception:
            db.rollback()
            raise

        # Invalidate cached redirect target so subsequent redirects fetch updated target
        await invalidate_redirect_target(link.code, org_id=effective_org)

    base_url = str(request.base_url).rstrip("/")
    return LinkResponse(
        id=link.id,
        code=link.code,
        short_url=f"{base_url}/r/{link.code}",
        long_url=link.long_url,
        created_by=link.created_by,
        created_at=link.created_at,
        expires_at=link.expires_at,
        tags=link.tags,
        title=link.title,
        is_active=link.is_active,
    )


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    link_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_api_key),
    tenant_id: Optional[str] = None,
):
    effective_org = tenant_id if tenant_id else principal.org_id

    link = (
        db.query(Link)
        .filter(Link.id == link_id, Link.created_by == effective_org)
        .first()
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found"
        )

    code_to_invalidate = link.code
    db.delete(link)
    db.commit()

    # Invalidate cached redirect target in Redis
    await invalidate_redirect_target(code_to_invalidate, org_id=effective_org)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
