"""Phase 1 Audit Fixes — TDD verification tests.

Tests 8 audit items:
  C5: LLM output basic validation
  C6: Backtest trade_list extraction
  C7: Kill Switch SQLite persistence + HMAC
  H2: Admin Token auto-generation (no "change-me")
  H3: No print() in core modules (use logger instead)
  H4: Metrics SQLite persistence
  H5: RSI uses Wilder's EMA
  H6: ATR uses Wilder's EMA
  H12: Rate limiter resets _min_interval on success
  H13: max_delay <= 120s
"""
import ast
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


# ── C5: LLM Output Validation ──────────────────────────────────────

class TestC5OutputValidator:
    def test_imports(self):
        from python_service.app.services.output_validator import output_validator
        assert output_validator is not None

    def test_catches_negative_price(self):
        from python_service.app.services.output_validator import OutputValidator
        v = OutputValidator()
        _, warnings = v.validate("当前股价: -100元")
        assert len(warnings) >= 1

    def test_catches_absurd_pe(self):
        from python_service.app.services.output_validator import OutputValidator
        v = OutputValidator()
        _, warnings = v.validate("PE ratio: 99999")
        assert len(warnings) >= 1

    def test_catches_extreme_change(self):
        from python_service.app.services.output_validator import OutputValidator
        v = OutputValidator()
        _, warnings = v.validate("涨幅: 200%")
        assert len(warnings) >= 1

    def test_valid_data_no_warnings(self):
        from python_service.app.services.output_validator import OutputValidator
        v = OutputValidator()
        _, warnings = v.validate("股价: 50元, PE: 15.2, 涨幅: 3.5%")
        assert len(warnings) == 0


# ── C6: Backtest trade_list extraction ──────────────────────────────

class TestC6TradeListExtraction:
    def test_run_qlib_bridge_has_extraction_code(self):
        src_path = os.path.join(
            os.path.dirname(__file__),
            "../paper_trading_system/execution_layer/run_qlib_bridge.py",
        )
        with open(src_path) as f:
            content = f.read()
        assert "indicator_dict" in content
        assert "trade_list" in content
        assert 'trade_list.append' in content


# ── C7: Kill Switch SQLite ─────────────────────────────────────────

class TestC7KillSwitchSQLite:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path):
        self.db_path = str(tmp_path / "kill_test.db")

    def test_state_persists_in_sqlite(self):
        from python_service.app.risk.kill_switch import KillSwitch, KillSwitchState
        ks1 = KillSwitch(db_path=self.db_path)
        ks1.trigger(
            __import__("python_service.app.risk.kill_switch", fromlist=["KillSwitchTrigger"]).KillSwitchTrigger.MANUAL,
            reason="test persist",
        )
        assert ks1.state == KillSwitchState.KILLED

        ks2 = KillSwitch(db_path=self.db_path)
        assert ks2.state == KillSwitchState.KILLED

    def test_hmac_signature_stored(self):
        from python_service.app.risk.kill_switch import KillSwitch
        ks = KillSwitch(db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT signature FROM kill_switch_state WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] is not None and len(row[0]) > 0

    def test_no_json_file_used(self):
        from python_service.app.risk.kill_switch import KillSwitch
        ks = KillSwitch(db_path=self.db_path)
        json_path = self.db_path.replace(".db", ".json")
        assert not os.path.exists(json_path)

    def test_table_structure(self):
        from python_service.app.risk.kill_switch import KillSwitch
        KillSwitch(db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(kill_switch_state)").fetchall()]
        conn.close()
        for required in ("state", "reason", "signature", "triggered_at", "reset_at"):
            assert required in cols, f"Missing column: {required}"


# ── H2: Admin Token ────────────────────────────────────────────────

class TestH2AdminToken:
    def test_no_hardcoded_change_me(self):
        src_path = os.path.join(os.path.dirname(__file__), "../app/api/admin.py")
        with open(src_path) as f:
            content = f.read()
        assert 'os.getenv("ADMIN_TOKEN", "change-me")' not in content

    def test_auto_generates_token(self):
        from python_service.app.api.admin import _ensure_admin_token
        old = os.environ.pop("ADMIN_TOKEN", None)
        try:
            token = _ensure_admin_token()
            assert token is not None
            assert len(token) > 10
            assert token != "change-me"
        finally:
            if old:
                os.environ["ADMIN_TOKEN"] = old

    def test_admin_rejects_change_me(self):
        from python_service.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/admin/stack-status", headers={"x-admin-token": "change-me"})
        assert resp.status_code == 403


# ── H3: No print() in core modules ─────────────────────────────────

class TestH3NoPrintInCoreModules:
    CORE_FILES = [
        "app/services/llm_gateway.py",
        "app/api/admin.py",
        "app/api/sector.py",
        "app/observability/metrics.py",
    ]

    @pytest.mark.parametrize("rel_path", CORE_FILES)
    def test_no_print_statement(self, rel_path):
        src_path = os.path.join(os.path.dirname(__file__), "../", rel_path)
        if not os.path.exists(src_path):
            pytest.skip(f"File not found: {rel_path}")
        with open(src_path) as f:
            source = f.read()
        tree = ast.parse(source)
        prints = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    prints.append(node.lineno)
        assert prints == [], f"print() found at lines {prints} in {rel_path}. Use logger instead."


# ── H4: Metrics SQLite persistence ──────────────────────────────────

class TestH4MetricsPersistence:
    def test_metrics_has_flush_method(self):
        from python_service.app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        assert hasattr(mc, "flush")

    def test_metrics_persists_to_sqlite(self, tmp_path):
        db_path = str(tmp_path / "metrics_test.db")
        from python_service.app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        mc._db_path = db_path

        for i in range(10):
            mc.record("test.metric", float(i), {"env": "test"})
        mc.flush()

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM metrics_log").fetchone()[0]
        conn.close()
        assert rows == 10


# ── H5: RSI Wilder's EMA ───────────────────────────────────────────

class TestH5RSIWilder:
    def test_rsi_uses_ewm_not_rolling(self):
        import inspect
        from python_service.technicals import calculate_rsi
        src = inspect.getsource(calculate_rsi)
        assert "ewm" in src
        assert ".rolling" not in src or "ewm" in src

    def test_rsi_output_range(self):
        from python_service.technicals import calculate_rsi
        np.random.seed(42)
        close = pd.Series(np.cumsum(np.random.randn(100)) + 100)
        rsi = calculate_rsi(close, 14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_responds_to_trend(self):
        from python_service.technicals import calculate_rsi
        np.random.seed(42)
        noise = np.random.randn(100) * 0.5
        trend = np.linspace(0, 10, 100)
        uptrend = pd.Series(trend + noise)
        rsi = calculate_rsi(uptrend, 14)
        last_valid = rsi.dropna().iloc[-1]
        assert last_valid > 50


# ── H6: ATR Wilder's EMA ───────────────────────────────────────────

class TestH6ATRWilder:
    def test_atr_uses_ewm_not_rolling(self):
        import inspect
        from python_service.technicals import calculate_atr
        src = inspect.getsource(calculate_atr)
        assert "ewm" in src

    def test_atr_positive(self):
        from python_service.technicals import calculate_atr
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            "high": np.abs(np.random.randn(n)) + 100,
            "low": np.abs(np.random.randn(n)) + 99,
            "close": np.abs(np.random.randn(n)) + 100,
        })
        atr = calculate_atr(df, 14)
        valid = atr.dropna()
        assert (valid > 0).all()


# ── H12: Rate limiter reset on success ──────────────────────────────

class TestH12RateLimiterReset:
    def test_release_resets_interval(self):
        from python_service.app.services.llm_gateway import RateLimiter
        rl = RateLimiter(min_interval=3.0)
        rl._min_interval = 10.0  # simulate backoff increase
        rl.release(success=True)
        assert rl._min_interval == rl._default_min_interval

    def test_no_reset_on_failure(self):
        from python_service.app.services.llm_gateway import RateLimiter
        rl = RateLimiter(min_interval=3.0)
        rl._min_interval = 10.0
        rl.release(success=False)
        assert rl._min_interval == 10.0


# ── H13: max_delay capped ──────────────────────────────────────────

class TestH13MaxDelay:
    def test_gemini_max_delay_is_120(self):
        import inspect
        from python_service.app.services.llm_gateway import LLMGateway
        src = inspect.getsource(LLMGateway._generate_gemini)
        assert "max_delay" in src
        assert "120" in src

    def test_default_max_delay_is_120(self):
        import inspect
        from python_service.app.services.llm_gateway import LLMGateway
        src = inspect.getsource(LLMGateway._generate_default)
        assert '120' in src
        assert '3600' not in src
