# Debugging & Incident Response — Module 06: Fix

**Track**: `debugging-incident-response`  
**Module**: 06 — Caching With Redis & Cache Invalidation Integrity  
**Step**: STEP 4 — FIX  
**Status**: COMPLETED  

---

## 1. Root Cause Analysis
In `apps/api/app/routers/links.py`, the `update_link` (`PATCH`) and `delete_link` (`DELETE`) endpoints committed changes to PostgreSQL but omitted calling the Redis cache eviction helper `invalidate_redirect_target()`. Because Redis had a 3600-second TTL, stale cache entries persisted until TTL expiry.

---

## 2. Minimal Fix Implemented
1. **Explicit Invalidation on Link Update (`PATCH`)**:
   In `apps/api/app/routers/links.py`:
   ```python
   if updated:
       try:
           db.commit()
           db.refresh(link)
       except Exception:
           db.rollback()
           raise

       # Invalidate cached redirect target so subsequent redirects fetch updated target
       await invalidate_redirect_target(link.code, org_id=effective_org)
   ```
2. **Explicit Invalidation on Link Deletion (`DELETE`)**:
   In `apps/api/app/routers/links.py`:
   ```python
   code_to_invalidate = link.code
   db.delete(link)
   db.commit()

   # Invalidate cached redirect target in Redis
   await invalidate_redirect_target(code_to_invalidate, org_id=effective_org)
   ```
3. **Tenant-Scoped Invalidation**:
   In `apps/api/app/cache.py`, `invalidate_redirect_target` validates tenant scoping before eviction:
   ```python
   async def invalidate_redirect_target(code: str, org_id: Optional[str] = None) -> bool:
       client = await ensure_redis()
       if client is None:
           return False
       key = get_cache_key(code)
       if org_id:
           cached = await client.get(key)
           if cached:
               data = json.loads(cached)
               if data.get("org_id") and data.get("org_id") != org_id:
                   logger.warning(f"Tenant isolation blocked invalidation: {org_id} != {data.get('org_id')}")
                   return False
       await client.delete(key)
       return True
   ```
4. **Graceful Fallback on Redis Down**:
   In `apps/api/app/routers/redirect.py`, if `get_redirect_target` returns `None` (either due to a cache miss or Redis being unreachable), the redirect seamlessly queries PostgreSQL and serves `HTTP 307`.

---

## 3. Backups Created
- `apps/api/app/routers/links.py.m06.bak`
