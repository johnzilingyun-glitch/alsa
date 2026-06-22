from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI


def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="ALSA — Institutional Stock Analysis API",
        version="2.0.0",
        description=(
            "## Overview\n\n"
            "ALSA (Automated Liquid Stock Analysis) is an institutional-grade quantitative "
            "analysis platform providing AI-powered stock research, real-time market data, "
            "portfolio management, and signal monitoring.\n\n"
            "## Authentication\n\n"
            "All endpoints require one of:\n\n"
            "| Method | Header | Description |\n"
            "|--------|--------|-------------|\n"
            "| API Key | `X-API-Key: alsa_...` | Recommended for external integrations |\n"
            "| JWT Bearer | `Authorization: Bearer <jwt>` | User session from `/api/auth/token` |\n"
            "| Legacy Token | `Authorization: Bearer <API_TOKEN>` | Original shared token |\n\n"
            "## Rate Limits\n\n"
            "| Endpoint Category | Default Limit |\n"
            "|-------------------|---------------|\n"
            "| Analysis (`/api/analysis/*`) | 5 requests/hour |\n"
            "| Market Data (`/api/market/*`) | 60 requests/minute |\n"
            "| Authentication (`/api/auth/*`) | 5 requests/minute |\n"
            "| Watchlist/Alerts | 30 requests/minute |\n"
            "| Default | 120 requests/minute |\n\n"
            "Rate limits are per-user for JWT/API-key auth, per-IP for unauthenticated. "
            "Role overrides: `admin` = unlimited, `researcher` = 100/hr, `viewer` = 20/hr.\n\n"
            "## Quick Start\n\n"
            "```bash\n"
            "# 1. Register & login\n"
            "curl -X POST http://localhost:8001/api/auth/register \\\n"
            "  -d 'username=alice&password=secret123'\n"
            "TOKEN=$(curl -X POST http://localhost:8001/api/auth/token \\\n"
            "  -d 'username=alice&password=secret123' | jq -r .access_token)\n\n"
            "# 2. Create an API key\n"
            "KEY=$(curl -X POST http://localhost:8001/api/api-keys/ \\\n"
            "  -H 'Authorization: Bearer '$TOKEN \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"name\": \"my-integration\", \"scopes\": [\"analysis:read\",\"market:read\"]}' \\\n"
            "  | jq -r .data.key)\n\n"
            "# 3. Use the API key\n"
            "curl -H 'X-API-Key: '$KEY http://localhost:8001/api/market/indices?market=A-Share\n"
            "```\n\n"
            "## SDKs\n\n"
            "Official SDKs are available for Python and JavaScript:\n\n"
            "```bash\n"
            "# Python\n"
            "pip install alsa-sdk\n\n"
            "# JavaScript\n"
            "npm install @alsa/sdk\n"
            "```\n\n"
            "## Error Codes\n\n"
            "| HTTP | Code | Meaning |\n"
            "|------|------|---------|\n"
            "| 401 | UNAUTHORIZED | Missing or invalid credentials |\n"
            "| 403 | FORBIDDEN | Insufficient scope for this endpoint |\n"
            "| 429 | RATE_LIMITED | Rate limit exceeded, retry after `Retry-After` header |\n"
            "| 500 | INTERNAL_ERROR | Server error, retry with backoff |\n"
        ),
        routes=app.routes,
    )

    # Security schemes
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key prefixed with `alsa_`. Create via POST `/api/api-keys/`.",
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token from POST `/api/auth/token`.",
        },
        "LegacyTokenAuth": {
            "type": "http",
            "scheme": "bearer",
            "description": "Legacy shared API_TOKEN.",
        },
    }

    # Add error response schemas
    openapi_schema["components"]["schemas"] = openapi_schema["components"].get("schemas", {})
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "example": False},
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "example": "UNAUTHORIZED"},
                    "message": {"type": "string", "example": "Invalid authentication credentials"},
                },
            },
        },
    }

    # Tags with descriptions
    openapi_schema["tags"] = [
        {"name": "auth", "description": "User registration, login, and JWT token management"},
        {"name": "api-keys", "description": "Create, list, update, and revoke API keys"},
        {"name": "analysis", "description": "AI-powered stock analysis jobs and results"},
        {"name": "market", "description": "Real-time market data, indices, quotes, and sector flows"},
        {"name": "watchlist", "description": "Portfolio watchlist management"},
        {"name": "alerts", "description": "Price alerts and signal monitoring"},
        {"name": "journal", "description": "Trading journal entries"},
        {"name": "brain", "description": "AI reasoning and research"},
        {"name": "technicals", "description": "Technical indicator calculations"},
        {"name": "screening", "description": "Stock screening and filtering"},
        {"name": "sector", "description": "Sector analysis and rankings"},
        {"name": "institutional", "description": "Institutional-grade risk management and compliance"},
        {"name": "mock_trading", "description": "Paper trading and backtesting"},
        {"name": "predictions", "description": "Price predictions and evaluations"},
        {"name": "reflections", "description": "Post-trade reflection and lessons learned"},
        {"name": "trade_intents", "description": "Trade intent submission and approval"},
        {"name": "health", "description": "Service health checks (no auth required)"},
    ]

    # Apply security globally
    openapi_schema["security"] = [
        {"ApiKeyAuth": []},
        {"BearerAuth": []},
        {"LegacyTokenAuth": []},
    ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema
