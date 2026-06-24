"""API Rate Limiter — prevents abuse and ensures fair resource usage.

Uses in-memory token bucket for single-instance deployments.
For distributed deployments, integrates with Redis.
"""
import time
import logging
from collections import defaultdict
from typing import Dict
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    In-memory token bucket rate limiter.
    
    Suitable for single-instance deployments.
    For distributed deployments, use Redis-backed limiter.
    """

    def __init__(self):
        self._buckets: Dict[str, list] = defaultdict(list)
        self._limits: Dict[str, tuple] = {}  # key -> (max_requests, window_seconds)

    def configure(self, key: str, max_requests: int, window_seconds: int):
        """Configure rate limit for a key pattern."""
        self._limits[key] = (max_requests, window_seconds)

    def is_allowed(self, key: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
        """
        Check if a request is allowed under the rate limit.
        
        Args:
            key: Unique identifier (e.g., user_id, IP address)
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds
            
        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        window_start = now - window_seconds

        # Clean old entries
        self._buckets[key] = [t for t in self._buckets[key] if t > window_start]

        if len(self._buckets[key]) >= max_requests:
            return False

        self._buckets[key].append(now)
        return True

    def get_remaining(self, key: str, max_requests: int = 10, window_seconds: int = 60) -> int:
        """Get remaining requests in current window."""
        now = time.time()
        window_start = now - window_seconds
        current = sum(1 for t in self._buckets[key] if t > window_start)
        return max(0, max_requests - current)

    def get_reset_time(self, key: str, window_seconds: int = 60) -> float:
        """Get seconds until the rate limit resets."""
        if not self._buckets[key]:
            return 0.0
        oldest = min(self._buckets[key])
        reset_at = oldest + window_seconds
        return max(0.0, reset_at - time.time())


# Singleton
rate_limiter = InMemoryRateLimiter()


# Pre-configured rate limits
RATE_LIMITS = {
    "analysis": (10, 60),      # 10 analyses per minute
    "market_data": (30, 60),   # 30 market data requests per minute
    "screening": (5, 60),      # 5 screening requests per minute
    "api_general": (100, 3600), # 100 general API calls per hour
}


def get_client_key(request: Request) -> str:
    """Extract client identifier from request."""
    # Try X-Forwarded-For first (for proxied requests)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Fall back to client host
    if request.client:
        return request.client.host
    return "unknown"


async def check_rate_limit(request: Request, limit_type: str = "api_general"):
    """
    FastAPI dependency for rate limiting.
    
    Usage:
        @router.get("/endpoint")
        async def endpoint(request: Request):
            await check_rate_limit(request, "analysis")
            ...
    """
    max_requests, window = RATE_LIMITS.get(limit_type, (100, 3600))
    client_key = f"{get_client_key(request)}:{limit_type}"

    if not rate_limiter.is_allowed(client_key, max_requests, window):
        remaining = rate_limiter.get_remaining(client_key, max_requests, window)
        reset_time = rate_limiter.get_reset_time(client_key, window)

        logger.warning(f"[RateLimit] Blocked {client_key}: {max_requests}/{window}s limit exceeded")

        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": max_requests,
                "window_seconds": window,
                "remaining": remaining,
                "reset_in_seconds": round(reset_time, 1),
            },
            headers={
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(reset_time)),
                "Retry-After": str(int(reset_time)),
            },
        )
