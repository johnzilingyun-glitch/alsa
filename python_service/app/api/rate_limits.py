from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitTier:
    endpoint_pattern: str
    limit: str  # slowapi format, e.g. "5/hour"
    description: str


# Endpoint-category rate limits
ENDPOINT_RATE_LIMITS: dict[str, RateLimitTier] = {
    "analysis": RateLimitTier("/api/analysis/*", "5/hour", "AI analysis jobs"),
    "market": RateLimitTier("/api/market/*", "60/minute", "Market data queries"),
    "auth": RateLimitTier("/api/auth/*", "5/minute", "Authentication endpoints"),
    "watchlist": RateLimitTier("/api/watchlist/*", "30/minute", "Watchlist management"),
    "alerts": RateLimitTier("/api/alerts/*", "30/minute", "Alert management"),
    "api_keys": RateLimitTier("/api/api-keys/*", "10/minute", "API key management"),
    "default": RateLimitTier("/api/*", "120/minute", "Default API rate limit"),
}

# Role-based rate limit overrides (requests per hour)
ROLE_RATE_LIMITS: dict[str, Optional[int]] = {
    "admin": None,      # unlimited
    "researcher": 100,
    "viewer": 20,
    "user": 60,
}


def get_rate_limit_for_endpoint(path: str) -> str:
    for key, tier in ENDPOINT_RATE_LIMITS.items():
        if key == "default":
            continue
        pattern = tier.endpoint_pattern.replace("*", "")
        if path.startswith(pattern):
            return tier.limit
    return ENDPOINT_RATE_LIMITS["default"].limit


def get_rate_limit_for_role(role: str) -> Optional[str]:
    per_hour = ROLE_RATE_LIMITS.get(role)
    if per_hour is None:
        return None  # unlimited
    return f"{per_hour}/hour"
