import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Tuple
from fastapi import HTTPException, Request, status
from app.auth import Principal


class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.

    ARCHITECTURE & LIMITATION NOTE:
    This rate limiter maintains window timestamps in local process memory.
    In a distributed, load-balanced, or multi-worker production deployment,
    in-memory limiters do not share state across process boundaries. For horizontal
    scaling, a distributed cache such as Redis (scheduled for Module 06) must be used.
    """

    def __init__(self):
        self._lock = Lock()
        # key -> list of float epoch timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def check_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60
    ) -> Tuple[bool, int]:
        """
        Evaluate if a request is permitted within the sliding window.
        Returns (is_allowed: bool, retry_after_seconds: int).
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Prune timestamps older than the sliding window
            timestamps = [ts for ts in self._requests[key] if ts > window_start]

            if len(timestamps) >= max_requests:
                oldest_in_window = timestamps[0]
                retry_after = max(1, int(oldest_in_window + window_seconds - now))
                self._requests[key] = timestamps
                return False, retry_after

            timestamps.append(now)
            self._requests[key] = timestamps
            return True, 0

    def reset(self) -> None:
        """Clear all rate limiting entries (for test suite isolation)."""
        with self._lock:
            self._requests.clear()


rate_limiter = InMemoryRateLimiter()


def rate_limit_link_creation(principal: Principal) -> None:
    """
    Rate limit dependency for link creation:
    Enforces maximum 30 requests per minute per authenticated principal/API key.
    """
    key = f"create_link:{principal.principal_id}"
    allowed, retry_after = rate_limiter.check_limit(key, max_requests=30, window_seconds=60)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: Link creation limit is 30 requests per minute.",
            headers={"Retry-After": str(retry_after)}
        )


def rate_limit_redirect(request: Request) -> None:
    """
    Rate limit dependency for public redirects:
    Enforces maximum 120 requests per minute per client IP to prevent short code enumeration.
    """
    client_ip = "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        client_ip = request.client.host

    key = f"redirect:{client_ip}"
    allowed, retry_after = rate_limiter.check_limit(key, max_requests=120, window_seconds=60)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: Redirect limit is 120 requests per minute.",
            headers={"Retry-After": str(retry_after)}
        )
