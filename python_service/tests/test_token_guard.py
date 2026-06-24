"""Tests for TokenGuard — defensive token budget enforcement."""
import pytest
from python_service.app.services.token_guard import (
    TokenGuard, GuardConfig, ToolLimit, LEVEL_CONFIGS,
    VALID_LEVELS, compact_json, slim_dict, slim_list,
    token_guard,
)


class TestTokenGuardLevels:
    """Test level configuration and switching."""

    def test_all_levels_exist(self):
        for level in VALID_LEVELS:
            assert level in LEVEL_CONFIGS

    def test_default_level_is_high(self):
        tg = TokenGuard()
        assert tg.level == "high"
        assert tg.config.enabled is True

    def test_none_level_disables_enforcement(self):
        tg = TokenGuard(level="none")
        assert tg.config.enabled is False
        assert tg.config.round_budget_chars > 999_000_000

    def test_set_level_changes_config(self):
        tg = TokenGuard(level="high")
        tg.set_level("low")
        assert tg.level == "low"
        assert tg.config.round_budget_chars == 75000

    def test_set_invalid_level_keeps_current(self):
        tg = TokenGuard(level="high")
        tg.set_level("invalid_level")
        assert tg.level == "high"

    def test_set_same_level_is_noop(self):
        tg = TokenGuard(level="medium")
        tg.set_level("medium")
        assert tg.level == "medium"

    def test_budget_increases_from_high_to_low(self):
        high = LEVEL_CONFIGS["high"]
        low = LEVEL_CONFIGS["low"]
        assert low.round_budget_chars > high.round_budget_chars


class TestTokenGuardEnforce:
    """Test enforce() output truncation."""

    def test_short_output_passes_through(self):
        tg = TokenGuard(level="high")
        output = "Short text"
        result = tg.enforce("web_search", output)
        assert result == output

    def test_empty_output_passes_through(self):
        tg = TokenGuard(level="high")
        assert tg.enforce("web_search", "") == ""
        assert tg.enforce("web_search", None) is None

    def test_long_output_truncated(self):
        tg = TokenGuard(level="high")
        # web_search limit at high = 3000 chars
        long_output = "x" * 10000
        result = tg.enforce("web_search", long_output)
        assert len(result) < 10000
        assert "truncated" in result

    def test_none_level_no_truncation(self):
        tg = TokenGuard(level="none")
        long_output = "x" * 100000
        result = tg.enforce("web_search", long_output)
        assert result == long_output

    def test_round_budget_tracking(self):
        tg = TokenGuard(level="high")
        tg.reset_round()
        tg.enforce("web_search", "a" * 1000)
        stats = tg.round_stats
        assert stats["tools_called"] == 1
        assert stats["chars_used"] >= 1000

    def test_multiple_tools_cumulate(self):
        tg = TokenGuard(level="high")
        tg.reset_round()
        tg.enforce("web_search", "a" * 500)
        tg.enforce("news_search", "b" * 500)
        stats = tg.round_stats
        assert stats["tools_called"] == 2
        assert stats["chars_used"] >= 1000

    def test_reset_round_clears_counters(self):
        tg = TokenGuard(level="high")
        tg.enforce("web_search", "a" * 500)
        tg.reset_round()
        stats = tg.round_stats
        assert stats["tools_called"] == 0
        assert stats["chars_used"] == 0

    def test_round_budget_remaining(self):
        tg = TokenGuard(level="high")
        tg.reset_round()
        initial = tg.round_budget_remaining
        tg.enforce("web_search", "a" * 500)
        assert tg.round_budget_remaining < initial


class TestTokenGuardEnforceParams:
    """Test enforce_params() parameter clamping."""

    def test_clamps_limit_param(self):
        tg = TokenGuard(level="high")
        params = {"limit": 100, "query": "test"}
        result = tg.enforce_params("web_search", params)
        # web_search max_rows at high = 5
        assert result["limit"] <= 5
        assert result["query"] == "test"

    def test_clamps_max_results(self):
        tg = TokenGuard(level="high")
        params = {"max_results": 50}
        result = tg.enforce_params("news_search", params)
        assert result["max_results"] <= 8

    def test_none_level_no_clamping(self):
        tg = TokenGuard(level="none")
        params = {"limit": 1000}
        result = tg.enforce_params("web_search", params)
        assert result["limit"] == 1000

    def test_get_limit_returns_tool_specific(self):
        tg = TokenGuard(level="high")
        limit = tg.get_limit("web_search")
        assert limit.max_chars == 3000
        assert limit.max_rows == 5

    def test_get_limit_returns_default_for_unknown(self):
        tg = TokenGuard(level="high")
        limit = tg.get_limit("unknown_tool_xyz")
        assert limit.max_chars == tg.config.default_limit.max_chars


class TestUtilityFunctions:
    """Test compact_json, slim_dict, slim_list."""

    def test_compact_json_no_whitespace(self):
        result = compact_json({"key": "value", "num": 42})
        assert " " not in result
        assert result == '{"key":"value","num":42}'

    def test_compact_json_unicode(self):
        result = compact_json({"名称": "茅台"})
        assert "茅台" in result

    def test_slim_dict_whitelist(self):
        d = {"name": "AAPL", "price": 150, "secret": "xxx", "notes": "long text"}
        result = slim_dict(d, ["name", "price"])
        assert result == {"name": "AAPL", "price": 150}
        assert "secret" not in result

    def test_slim_dict_truncates_long_fields(self):
        d = {"text": "a" * 500}
        result = slim_dict(d, ["text"], max_field_chars=100)
        assert len(result["text"]) <= 101  # 100 + "…"

    def test_slim_list_max_items(self):
        items = [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}, {"a": 5}]
        result = slim_list(items, max_items=3)
        assert len(result) == 3

    def test_slim_list_with_whitelist(self):
        items = [{"name": "A", "secret": "x"}, {"name": "B", "secret": "y"}]
        result = slim_list(items, max_items=10, whitelist=["name"])
        assert all("secret" not in r for r in result)
        assert all("name" in r for r in result)
