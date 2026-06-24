"""Tests for InMemoryRateLimiter — API rate limiting."""
import time
import pytest
from unittest.mock import MagicMock
from python_service.app.api.rate_limiter import (
    InMemoryRateLimiter, rate_limiter, RATE_LIMITS, get_client_key,
)


class TestInMemoryRateLimiter:
    """Test token bucket rate limiter."""

    def test_allows_requests_within_limit(self):
        limiter = InMemoryRateLimiter()
        for i in range(5):
            assert limiter.is_allowed("user1", max_requests=5, window_seconds=60) is True

    def test_blocks_after_limit_exceeded(self):
        limiter = InMemoryRateLimiter()
        for i in range(3):
            limiter.is_allowed("user2", max_requests=3, window_seconds=60)
        assert limiter.is_allowed("user2", max_requests=3, window_seconds=60) is False

    def test_different_keys_independent(self):
        limiter = InMemoryRateLimiter()
        for i in range(3):
            limiter.is_allowed("userA", max_requests=3, window_seconds=60)
        # userA is exhausted, but userB should be fine
        assert limiter.is_allowed("userA", max_requests=3, window_seconds=60) is False
        assert limiter.is_allowed("userB", max_requests=3, window_seconds=60) is True

    def test_window_expiry_resets(self):
        limiter = InMemoryRateLimiter()
        # Use a very short window
        for i in range(3):
            limiter.is_allowed("user3", max_requests=3, window_seconds=0.1)
        assert limiter.is_allowed("user3", max_requests=3, window_seconds=0.1) is False

        # Wait for window to expire
        time.sleep(0.15)
        assert limiter.is_allowed("user3", max_requests=3, window_seconds=0.1) is True

    def test_get_remaining(self):
        limiter = InMemoryRateLimiter()
        assert limiter.get_remaining("user4", max_requests=10, window_seconds=60) == 10

        limiter.is_allowed("user4", max_requests=10, window_seconds=60)
        limiter.is_allowed("user4", max_requests=10, window_seconds=60)
        assert limiter.get_remaining("user4", max_requests=10, window_seconds=60) == 8

    def test_get_reset_time(self):
        limiter = InMemoryRateLimiter()
        # No requests yet
        assert limiter.get_reset_time("user5", window_seconds=60) == 0.0

        limiter.is_allowed("user5", max_requests=10, window_seconds=60)
        reset_time = limiter.get_reset_time("user5", window_seconds=60)
        assert 0 < reset_time <= 60


class TestGetClientKey:
    """Test client key extraction from request."""

    def test_forwarded_header(self):
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        assert get_client_key(request) == "192.168.1.1"

    def test_client_host_fallback(self):
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.5"
        assert get_client_key(request) == "10.0.0.5"

    def test_no_client_returns_unknown(self):
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert get_client_key(request) == "unknown"


class TestRateLimitsConfig:
    """Test pre-configured rate limits."""

    def test_analysis_limit_defined(self):
        assert "analysis" in RATE_LIMITS
        max_req, window = RATE_LIMITS["analysis"]
        assert max_req > 0
        assert window > 0

    def test_market_data_limit_defined(self):
        assert "market_data" in RATE_LIMITS

    def test_screening_limit_defined(self):
        assert "screening" in RATE_LIMITS

    def test_general_limit_defined(self):
        assert "api_general" in RATE_LIMITS
