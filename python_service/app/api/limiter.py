from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


def _get_limiter_key(request: Request) -> str:
    """Rate limit key: prefer API key hash, then user ID, then IP."""
    api_key = request.headers.get("x-api-key")
    if api_key and api_key.startswith("alsa_"):
        import hashlib
        return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer alsa_"):
        import hashlib
        return f"apikey:{hashlib.sha256(auth[7:].encode()).hexdigest()[:16]}"
    # Check for JWT user
    from ..security import authenticate
    try:
        user_id, method, _ = authenticate(request)
        if method == "jwt":
            return f"user:{user_id}"
    except Exception:
        pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_limiter_key)


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Add X-RateLimit-* headers to responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # SlowAPI stores rate limit info in request.state if available
        limiter_state = getattr(request.state, "rate_limit", None)
        if limiter_state:
            try:
                response.headers["X-RateLimit-Limit"] = str(limiter_state.get("limit", ""))
                response.headers["X-RateLimit-Remaining"] = str(limiter_state.get("remaining", ""))
                response.headers["X-RateLimit-Reset"] = str(limiter_state.get("reset", ""))
            except Exception:
                pass
        return response
