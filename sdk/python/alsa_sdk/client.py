"""ALSAClient — Python SDK for the ALSA Stock Analysis API."""

import time
import logging
from typing import Optional, Any
import httpx

from .models import (
    AnalysisJob,
    MarketQuote,
    WatchlistItem,
    Alert,
    AnalysisResult,
    ApiKeyInfo,
)

logger = logging.getLogger("alsa_sdk")

DEFAULT_BASE_URLS = {
    "development": "http://localhost:8001",
    "production": "https://api.alsa.example.com",
}


class ALSAClientError(Exception):
    """Base error for ALSA SDK."""
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[{status_code}] {code}: {message}")


class ALSAClient:
    """Client for the ALSA Stock Analysis API.

    Args:
        api_key: API key prefixed with ``alsa_``. Mutually exclusive with ``token``.
        token: JWT access token from ``/api/auth/token``.
        base_url: API base URL. Defaults to ``http://localhost:8001``.
        timeout: HTTP timeout in seconds.
        max_retries: Maximum retry attempts for transient errors (429, 5xx).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        base_url: str = "http://localhost:8001",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        if not api_key and not token:
            raise ValueError("Provide either api_key or token")
        self.api_key = api_key
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._client = httpx.Client(
            timeout=timeout,
            headers=self._build_headers(),
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        elif self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.request(method, url, **kwargs)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited, retrying in {retry_after}s (attempt {attempt+1})")
                    time.sleep(retry_after)
                    continue
                if resp.status_code >= 500:
                    wait = min(2 ** attempt, 30)
                    logger.warning(f"Server error {resp.status_code}, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    last_exc = e
                    continue
                body = e.response.json() if e.response.headers.get("content-type", "").startswith("application/json") else {}
                error = body.get("error", {})
                raise ALSAClientError(
                    status_code=e.response.status_code,
                    code=error.get("code", "HTTP_ERROR"),
                    message=error.get("message", str(e)),
                ) from e
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    wait = min(2 ** attempt, 30)
                    logger.warning(f"Request error, retrying in {wait}s: {e}")
                    time.sleep(wait)
                    last_exc = e
                    continue
                raise ALSAClientError(503, "CONNECTION_ERROR", str(e)) from e
        raise ALSAClientError(503, "MAX_RETRIES", "Exceeded maximum retries") from last_exc

    def _unwrap(self, resp: dict) -> Any:
        if not resp.get("success"):
            err = resp.get("error", {})
            raise ALSAClientError(400, err.get("code", "UNKNOWN"), err.get("message", "Unknown error"))
        return resp.get("data")

    # ── Analysis ──

    def analyze(self, symbol: str, market: str, analysis_level: str = "standard",
                model: Optional[str] = None) -> dict:
        """Submit an analysis job and return the job response."""
        payload = {"symbol": symbol, "market": market, "analysis_level": analysis_level}
        if model:
            payload["requested_model"] = model
        resp = self._request("POST", "/api/analysis/jobs", json=payload)
        return self._unwrap(resp)

    def get_analysis_job(self, job_id: str) -> dict:
        resp = self._request("GET", f"/api/analysis/jobs/{job_id}")
        return self._unwrap(resp)

    def get_analysis_run(self, analysis_id: str) -> dict:
        resp = self._request("GET", f"/api/analysis/runs/{analysis_id}")
        return self._unwrap(resp)

    def get_analysis_history(self, symbol: str) -> list[dict]:
        resp = self._request("GET", f"/api/analysis/history/{symbol}")
        return self._unwrap(resp)

    # ── Market ──

    def get_market_indices(self, market: str = "A-Share") -> dict:
        resp = self._request("GET", f"/api/market/indices", params={"market": market})
        return self._unwrap(resp)

    def get_quote(self, symbol: str) -> dict:
        resp = self._request("GET", f"/api/market/quote/{symbol}")
        return self._unwrap(resp)

    def get_quotes(self, symbols: list[str]) -> list[dict]:
        resp = self._request("GET", "/api/market/quotes", params={"symbols": ",".join(symbols)})
        return self._unwrap(resp)

    def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> list[dict]:
        resp = self._request("GET", f"/api/market/history/{symbol}", params={"period": period, "interval": interval})
        return self._unwrap(resp)

    def get_market_data(self, symbol: str, period: str = "1mo") -> dict:
        """Convenience: quote + history."""
        quote = self.get_quote(symbol)
        history = self.get_history(symbol, period=period)
        return {"quote": quote, "history": history}

    # ── Watchlist ──

    def get_watchlist(self) -> list[dict]:
        resp = self._request("GET", "/api/watchlist/")
        data = self._unwrap(resp)
        return data.get("items", []) if isinstance(data, dict) else data

    def add_to_watchlist(self, symbol: str, name: str, market: str) -> dict:
        resp = self._request("POST", "/api/watchlist/", json={"symbol": symbol, "name": name, "market": market})
        return self._unwrap(resp)

    def remove_from_watchlist(self, symbol: str, market: str) -> bool:
        self._request("DELETE", f"/api/watchlist/{symbol}", params={"market": market})
        return True

    # ── Alerts ──

    def get_alerts(self) -> list[dict]:
        resp = self._request("GET", "/api/alerts/")
        data = self._unwrap(resp)
        return data.get("items", []) if isinstance(data, dict) else data

    def create_alert(self, symbol: str, market: str, entry_price: float,
                     target_price: float, stop_loss: float) -> dict:
        resp = self._request("POST", "/api/alerts/", json={
            "symbol": symbol, "market": market,
            "entry_price": entry_price, "target_price": target_price,
            "stop_loss": stop_loss,
        })
        return self._unwrap(resp)

    # ── API Keys ──

    def create_api_key(self, name: str, scopes: list[str] | None = None,
                       expires_in_days: int | None = None) -> dict:
        payload: dict[str, Any] = {"name": name}
        if scopes:
            payload["scopes"] = scopes
        if expires_in_days:
            payload["expires_in_days"] = expires_in_days
        resp = self._request("POST", "/api/api-keys/", json=payload)
        return self._unwrap(resp)

    def list_api_keys(self) -> list[dict]:
        resp = self._request("GET", "/api/api-keys/")
        return self._unwrap(resp)

    def revoke_api_key(self, key_id: str) -> bool:
        self._request("DELETE", f"/api/api-keys/{key_id}")
        return True

    # ── Health ──

    def health(self) -> dict:
        resp = self._request("GET", "/api/health")
        return resp

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
