import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger("apps.api.cache")

# Global async Redis client instance and associated event loop
redis_client: Optional[aioredis.Redis] = None
_redis_loop: Optional[asyncio.AbstractEventLoop] = None

# Metrics for verification and observability
cache_metrics: Dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "errors": 0,
    "invalidations": 0,
}


def get_cache_key(code: str) -> str:
    """Format consistent cache key for short code redirect targets."""
    return f"link:{code}"


async def init_redis() -> Optional[aioredis.Redis]:
    """Initialize the asynchronous Redis connection pool with strict timeouts."""
    global redis_client, _redis_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if redis_client is not None and _redis_loop is current_loop and current_loop is not None:
        return redis_client

    redis_url = settings.redis_url or "redis://127.0.0.1:6379"
    if "localhost" in redis_url:
        redis_url = redis_url.replace("localhost", "127.0.0.1")
    try:
        redis_client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=1.0,
            health_check_interval=30,
        )
        # Verify connectivity
        await redis_client.ping()
        _redis_loop = current_loop
        logger.info("Connected to Redis cache successfully")
        return redis_client
    except Exception as e:
        logger.warning(f"Redis initialization failed ({e}). Cache will run in fallback mode.")
        redis_client = None
        _redis_loop = None
        return None


async def ensure_redis() -> Optional[aioredis.Redis]:
    """Ensure the Redis client is initialized and bound to the current event loop."""
    global redis_client, _redis_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if redis_client is None or (_redis_loop is not None and _redis_loop is not current_loop):
        await init_redis()
    return redis_client


async def close_redis() -> None:
    """Safely terminate Redis connection pool on application shutdown."""
    global redis_client, _redis_loop
    if redis_client is not None:
        try:
            await redis_client.close()
            logger.info("Closed Redis connection pool.")
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
        finally:
            redis_client = None
            _redis_loop = None


def reset_cache_metrics() -> None:
    """Reset cache metrics for test suite isolation."""
    cache_metrics.clear()
    cache_metrics.update({
        "hits": 0,
        "misses": 0,
        "errors": 0,
        "invalidations": 0,
    })


# =============================================================================
# Cache Service Functions (Cache-Aside + Tenant-Scoping)
# =============================================================================

async def get_redirect_target(code: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached redirect resolution for a short code.
    Returns parsed dictionary containing long_url and tenant org_id on hit.
    Returns None on cache miss, expired entry, or Redis connection failure.
    """
    global redis_client, cache_metrics
    client = await ensure_redis()
    if client is None:
        cache_metrics["misses"] += 1
        return None

    key = get_cache_key(code)
    try:
        raw = await client.get(key)
        if raw is None:
            cache_metrics["misses"] += 1
            return None

        data = json.loads(raw)
        
        # Check if the cached link has an explicit expiration timestamp
        expires_at_str = data.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at <= datetime.now(timezone.utc):
                # Expired link: invalidate immediately and return None
                await client.delete(key)
                cache_metrics["misses"] += 1
                return None

        cache_metrics["hits"] += 1
        return data
    except RedisError as e:
        cache_metrics["errors"] += 1
        logger.warning(f"Redis error reading key {key}: {e}. Falling back to PostgreSQL.")
        return None
    except Exception as e:
        cache_metrics["errors"] += 1
        logger.warning(f"Unexpected cache error reading key {key}: {e}. Falling back to PostgreSQL.")
        return None


async def set_redirect_target(
    code: str,
    long_url: str,
    ttl_seconds: int = 3600,
    org_id: Optional[str] = None,
    link_id: Optional[int] = None,
    expires_at: Optional[datetime] = None,
) -> bool:
    """
    Populate Redis with resolved short link data following a database query.
    Captures tenant org_id to satisfy B2B organization scoping.
    """
    global redis_client
    client = await ensure_redis()
    if client is None:
        return False

    key = get_cache_key(code)
    payload = {
        "long_url": long_url,
        "org_id": org_id or "public",
        "link_id": link_id,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # If link has an earlier expiration, ensure TTL does not outlive link expiry
        actual_ttl = ttl_seconds
        if expires_at:
            now = datetime.now(timezone.utc)
            seconds_until_expiry = int((expires_at - now).total_seconds())
            if seconds_until_expiry <= 0:
                return False
            actual_ttl = min(actual_ttl, seconds_until_expiry)

        await client.set(key, json.dumps(payload), ex=max(1, actual_ttl))
        return True
    except RedisError as e:
        logger.warning(f"Redis error setting key {key}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected cache error setting key {key}: {e}")
        return False


async def invalidate_redirect_target(code: str, org_id: Optional[str] = None) -> bool:
    """
    Evict cached redirect target upon update or deletion.
    Enforces tenant scoping by validating ownership if tenant context is available.
    """
    global redis_client, cache_metrics
    client = await ensure_redis()
    if client is None:
        return False

    key = get_cache_key(code)
    try:
        if org_id:
            # If tenant context is provided, check existing cache entry ownership before evicting
            raw = await client.get(key)
            if raw:
                try:
                    data = json.loads(raw)
                    cached_org = data.get("org_id")
                    if cached_org and cached_org != "public" and cached_org != org_id:
                        logger.warning(f"Tenant isolation blocked invalidation: {org_id} != {cached_org}")
                        return False
                except Exception:
                    pass

        deleted = await client.delete(key)
        cache_metrics["invalidations"] += int(deleted > 0)
        return bool(deleted > 0)
    except RedisError as e:
        logger.warning(f"Redis error invalidating key {key}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected cache error invalidating key {key}: {e}")
        return False
