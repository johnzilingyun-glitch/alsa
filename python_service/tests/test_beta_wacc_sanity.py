# -*- coding: utf-8 -*-
"""Sanity tests for DCF β/WACC guardrails (regression for job_6c9d3280,
伊利股份 600887: raw β=0.10 → WACC 2.62% → Gordon terminal explosion).

Covers:
  - provider side (_apply_beta_guardrails / _compute_beta): Blume shrinkage,
    sanity bounds, regression-quality gates, raw-value preservation.
  - renderer side (ReportGeneratorService._compute_valuation): β input clamp,
    Rf sourcing, WACC floor, g constraint, DCF rejection on insufficient
    WACC−g spread, deviation warning vs the blended target price.
  - ERP single definition point (provider & renderer share one constant).
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.services.data_providers.a_stock_direct import (
    EQUITY_RISK_PREMIUM,
    _apply_beta_guardrails,
    _compute_beta,
)
from python_service.app.services.computation_tools import dcf_calculate
import python_service.app.services.report_generator_service as rgs
from python_service.app.services.report_generator_service import ReportGeneratorService


# ────────────────────────── helpers ──────────────────────────
def _df_from_returns(rets, start="2021-01-08"):
    """Build a kline-style DataFrame (date/close) from a return series."""
    dates = pd.date_range(start, periods=len(rets) + 1, freq="7D")
    close = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + np.asarray(rets, dtype=float)]))
    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "close": close,
    })


def _pair(n=150, beta=1.2, orthogonal=False):
    """Deterministic stock/bench return series.

    orthogonal=True → stock return is the period-4 pattern [+,+,-,-] while the
    bench is [+,-,+,-]: exactly uncorrelated (corr=0, β_reg=0) — the
    "correlation collapse" regime (e.g. 600887 raw corr=0.10, β=0.1049).
    """
    bench = np.tile([0.01, -0.01], n // 2)
    if orthogonal:
        stock = np.tile([0.02, 0.02, -0.02, -0.02], n // 4)[: len(bench)]
    else:
        stock = beta * bench
    return _df_from_returns(stock), _df_from_returns(bench)


def _svc():
    return ReportGeneratorService()


# ─────────────── provider: _apply_beta_guardrails (pure) ───────────────
class TestApplyBetaGuardrails:
    def test_regression_none_falls_back_to_market_prior(self):
        r = _apply_beta_guardrails(None)
        assert r == {"beta": 1.0, "beta_raw": None, "low_confidence": True,
                     "rejected": False, "prior": "market"}

    def test_yili_like_low_beta_falls_back_to_prior(self):
        # β_reg=0.1049 < 0.2：回归值无统计意义 → 回退先验（而非 Blume 拉回）。
        # 此前 Blume 会把 0.1049 拉到 0.40 混入正常带，现在明确标记低置信。
        r = _apply_beta_guardrails(0.1049)
        assert r["beta"] == 1.0
        assert r["beta_raw"] == 0.1
        assert r["low_confidence"] is True
        assert r["rejected"] is False
        assert r["prior"] == "market"

    def test_low_beta_uses_industry_prior(self):
        r = _apply_beta_guardrails(0.1049, industry="食品饮料")
        assert r["beta"] == 0.75  # 行业 β 中位数先验（Damodaran 中国口径近似）
        assert r["prior"] == "industry:食品饮料"
        assert r["low_confidence"] is True

    def test_normal_beta_uses_blume(self):
        r = _apply_beta_guardrails(1.2)
        assert r["beta"] == pytest.approx(1.13, abs=0.005)  # 0.67×1.2+0.33
        assert r["beta_raw"] == 1.2
        assert r["low_confidence"] is False
        assert r["rejected"] is False
        assert r["prior"] is None

    def test_negative_regression_is_rejected(self):
        # 负 β（权益资产与市场长期负相关，CAPM 下无意义）一律拒绝入库。
        r = _apply_beta_guardrails(-0.6)
        assert r["beta"] is None
        assert r["beta_raw"] == -0.6
        assert r["low_confidence"] is True
        assert r["rejected"] is True

    def test_mild_negative_regression_is_rejected(self):
        r = _apply_beta_guardrails(-0.3)
        assert r["beta"] is None
        assert r["beta_raw"] == -0.3
        assert r["low_confidence"] is True
        assert r["rejected"] is True

    def test_floating_point_negative_noise_treated_as_zero(self):
        # 正交序列回归出的 -1e-17 是浮点噪声（相关性塌陷），不是有意义的
        # 负 β：归一为 0 → β<0.2 → 先验回退而非拒绝入库。
        r = _apply_beta_guardrails(-1e-17)
        assert r["beta"] == 1.0
        assert r["beta_raw"] == 0.0
        assert r["low_confidence"] is True
        assert r["rejected"] is False
        assert r["prior"] == "market"

    def test_extreme_beta_falls_back_to_market_prior(self):
        # β_reg=4.0 > 3：回退先验而非钳制到 3.0（采信异常值无统计意义）。
        r = _apply_beta_guardrails(4.0)
        assert r["beta"] == 1.0
        assert r["beta_raw"] == 4.0
        assert r["low_confidence"] is True
        assert r["rejected"] is False
        assert r["prior"] == "market"

    def test_extreme_beta_uses_industry_prior(self):
        r = _apply_beta_guardrails(4.0, industry="证券")
        assert r["beta"] == 1.30
        assert r["prior"] == "industry:证券"


# ─────────────── provider: _compute_beta (synthetic series) ───────────────
class TestComputeBeta:
    def test_high_correlation_normal_beta(self):
        stock, bench = _pair(n=150, beta=1.2)
        r = _compute_beta(stock, bench)
        assert r["beta_raw"] == pytest.approx(1.2, abs=1e-6)
        assert r["beta"] == pytest.approx(1.13, abs=0.005)
        assert r["low_confidence"] is False
        assert r["rejected"] is False

    def test_low_correlation_falls_back_to_market_prior(self):
        # Correlation collapse (job_6c9d3280 regime): β_reg≈0, corr≈0。
        # β_reg < 0.2 无统计意义 → 市场先验 1.0 + 低置信（不再让 0.33 混入 DB），
        # 且行业先验可用时优先行业口径。
        stock, bench = _pair(n=150, orthogonal=True)
        r = _compute_beta(stock, bench)
        assert r["beta_raw"] == pytest.approx(0.0, abs=0.05)
        assert r["beta"] == 1.0
        assert r["low_confidence"] is True
        assert r["prior"] == "market"

    def test_low_correlation_uses_industry_prior(self):
        stock, bench = _pair(n=150, orthogonal=True)
        r = _compute_beta(stock, bench, industry="银行")
        assert r["beta"] == 0.60
        assert r["prior"] == "industry:银行"

    def test_negative_correlation_is_rejected(self):
        stock, bench = _pair(n=150, beta=-0.6)
        r = _compute_beta(stock, bench)
        assert r["beta_raw"] == pytest.approx(-0.6, abs=1e-6)
        assert r["beta"] is None
        assert r["low_confidence"] is True
        assert r["rejected"] is True

    def test_mild_negative_is_rejected(self):
        stock, bench = _pair(n=150, beta=-0.3)
        r = _compute_beta(stock, bench)
        assert r["beta_raw"] == pytest.approx(-0.3, abs=1e-6)
        assert r["beta"] is None
        assert r["rejected"] is True

    def test_insufficient_aligned_observations_falls_back(self):
        stock, bench = _pair(n=50, beta=1.2)  # 49 aligned returns < 60
        r = _compute_beta(stock, bench)
        assert r["beta"] == 1.0
        assert r["beta_raw"] is None
        assert r["low_confidence"] is True
        assert r["prior"] == "market"

    def test_missing_frames_fall_back(self):
        for stock, bench in ((None, None), (_df_from_returns([0.01] * 100), None),
                             (None, _df_from_returns([0.01] * 100))):
            r = _compute_beta(stock, bench)
            assert r == {"beta": 1.0, "beta_raw": None, "low_confidence": True,
                         "rejected": False, "prior": "market"}


# ─────────────── renderer: _compute_valuation guardrails ───────────────
class TestComputeValuationGuards:
    def _snap(self, **over):
        fin = {
            "beta": 1.0, "rf": 0.0173,
            "marketCap": 1.0e11, "totalDebt": 2.5e10,
            "freeCashflow": 1.0e10, "sharesOutstanding": 5.0e9,
        }
        fin.update(over)
        return {"financials": fin, "quote": {"price": 30.0}}

    def _info(self, **over):
        d = {"market": "A-Share", "currency": "CNY", "price": 30.0}
        d.update(over)
        return d

    def test_pathological_beta_clamped_and_wacc_floored(self):
        # Old behavior: β=0.1 → Ke=2.18% → WACC=2.62% → g clamp → DCF=103.42.
        # New: β→0.2, WACC→5% floor, g=1.73% → bounded DCF ≈ 48.6.
        res = _svc()._compute_valuation(
            self._snap(beta=0.1, beta_raw=0.1, beta_low_confidence=True), self._info())
        assert res["beta"] == "0.20"
        assert res["wacc"] == "5.00%"
        # Ke = Rf + 0.2 × ERP = 1.73% + 0.2×5.5% = 2.83%
        assert "Ke=Rf+β×ERP=2.8%" in res["source"]
        warns = res["sanity_warnings"]
        assert any("低于合理下限" in w and "β" in w for w in warns)
        assert any("WACC" in w and "已钳制" in w for w in warns)
        assert "dcf_target" in res
        dcf = float(res["dcf_target"].split()[0])
        # WACC 5% floor, g=1.73% -> intrinsic 3.111e11 / 5e9 shares = 62.22
        assert dcf == pytest.approx(62.22, abs=0.05)
        assert dcf < 70  # no more exploding ~103

    def test_normal_params_follow_new_formula(self):
        # ERP unified to 5.5%: ke = 1.73% + 1.0×5.5% = 7.23%; Kd 默认 4%（与
        # provider 同源 valuation_config）；E/V=0.8, D/V=0.2 →
        # WACC = 0.8×7.23% + 0.2×4%×0.75 = 6.38% (> 5% floor, no clamp);
        # g = min(5%, 1.73%, 4.38%) = 1.73%; DCF = 43.72 CNY.
        res = _svc()._compute_valuation(self._snap(), self._info())
        assert res["erp"] == "5.5%"
        assert res["kd"] == "4.0%"  # 与 provider WACC 同源（不再 4%/5% 各执一词）
        assert res["wacc"] == "6.38%"
        assert res["sanity_warnings"] == []
        assert "g=1.73%" in res["source"]
        dcf = float(res["dcf_target"].split()[0])
        assert dcf == pytest.approx(43.72, abs=0.05)

    def test_rf_prefers_provider_realtime_value(self):
        res = _svc()._compute_valuation(self._snap(rf=0.025), self._info())
        assert res["rf"] == "2.50%"
        assert "provider 实时" in res["source"]

    def test_rf_falls_back_to_live_cn_rate(self):
        # A-Share 且 provider 未写 rf：渲染层直取 provider 的实时中债 10Y
        # （同一函数 + TTL 缓存）；patch 掉实时函数避免测试打网络。
        snap = self._snap()
        snap["financials"].pop("rf")
        monkey = pytest.MonkeyPatch()
        try:
            monkey.setattr(rgs, "_get_cn_risk_free_rate", lambda: 0.021)
            res = _svc()._compute_valuation(snap, self._info())
        finally:
            monkey.undo()
        assert res["rf"] == "2.10%"
        assert "渲染层直取" in res["source"]

    def test_rf_live_fetch_failure_uses_config_default(self):
        snap = self._snap()
        snap["financials"].pop("rf")

        def _boom():
            raise RuntimeError("network down")

        monkey = pytest.MonkeyPatch()
        try:
            monkey.setattr(rgs, "_get_cn_risk_free_rate", _boom)
            res = _svc()._compute_valuation(snap, self._info())
        finally:
            monkey.undo()
        assert res["rf"] == "2.00%"  # valuation_config.CN_RISK_FREE_FALLBACK
        assert "市场基准默认" in res["source"]

    def test_beta_provenance_disclosed_in_source(self):
        res = _svc()._compute_valuation(
            self._snap(beta=0.4, beta_raw=0.1, beta_low_confidence=True), self._info())
        assert "原始回归 0.10" in res["source"]
        assert "Blume" in res["source"]
        assert "低置信" in res["source"]

    def test_dcf_rejected_when_spread_insufficient(self):
        # Force WACC below the 2% spread floor by disabling the sanity floor
        # constants (defense-in-depth test of the rejection branch):
        # β=0.2, rf=0.5% → ke=1.6%, ~no debt → WACC≈1.6% → g_ceiling<0 → skip.
        monkey = pytest.MonkeyPatch()
        try:
            monkey.setattr(rgs, "_VALUATION_WACC_FLOOR_ABS", 0.0)
            monkey.setattr(rgs, "_VALUATION_WACC_FLOOR_MARGIN", 0.0)
            res = _svc()._compute_valuation(
                self._snap(beta=0.2, rf=0.005, marketCap=1.0e10, totalDebt=1.0),
                self._info())
        finally:
            monkey.undo()
        assert "dcf_target" not in res
        assert "跳过 DCF" in res["dcf_skip_reason"]

    def test_deviation_warning_when_dcf_exceeds_blended_target_2x(self):
        res = _svc()._compute_valuation(
            self._snap(), self._info(ref_target_price=20.0))  # DCF 43.72 vs 20
        assert res["deviation_warning"] is not None
        assert "偏离超 2 倍" in res["deviation_warning"]
        assert "2.2x" in res["deviation_warning"]

    def test_deviation_warning_when_dcf_below_blended_target_half(self):
        res = _svc()._compute_valuation(
            self._snap(), self._info(ref_target_price=100.0))  # DCF 43.72 vs 100
        assert res["deviation_warning"] is not None
        assert "偏离超 2 倍" in res["deviation_warning"]

    def test_no_deviation_warning_within_2x_band(self):
        res = _svc()._compute_valuation(
            self._snap(), self._info(ref_target_price=30.0))
        assert "deviation_warning" not in res

    def test_beta_ceiling_clamp(self):
        res = _svc()._compute_valuation(self._snap(beta=5.0), self._info())
        assert res["beta"] == "3.00"
        assert any("高于合理上限" in w for w in res["sanity_warnings"])

    def test_wacc_basis_disclosed_alongside_provider_estimate(self):
        # 两套 WACC 不合并，但必须明确标注口径差异：渲染层独立复算 +
        # provider 快照估算并列披露。
        res = _svc()._compute_valuation(
            self._snap(wacc=7.77, waccEstimated=True), self._info())
        assert "口径：本表为报告层独立复算 WACC" in res["source"]
        assert "数据源快照 WACC 估算=7.77%" in res["source"]

    def test_kd_default_matches_provider_constant(self):
        # Kd 默认值与 provider 侧同源（valuation_config.DEFAULT_COST_OF_DEBT）。
        from python_service.app.services.valuation_config import DEFAULT_COST_OF_DEBT
        snap = self._snap()
        snap["financials"].pop("rf")
        monkey = pytest.MonkeyPatch()
        try:
            monkey.setattr(rgs, "_get_cn_risk_free_rate", lambda: 0.0173)
            res = _svc()._compute_valuation(snap, self._info())
        finally:
            monkey.undo()
        assert res["kd"] == f"{DEFAULT_COST_OF_DEBT*100:.1f}%"
        assert DEFAULT_COST_OF_DEBT == 0.04


# ─────────────── scenario blended target helper ───────────────
class TestScenarioExpectedPrice:
    def test_probability_weighted_price(self):
        scenarios = [
            {"case": "Bull", "probability": 30, "targetPrice": "32.0元"},
            {"case": "Base", "probability": 50, "targetPrice": "27.0"},
            {"case": "Bear", "probability": 20, "targetPrice": "21.0"},
        ]
        # 30%*32 + 50%*27 + 20%*21 = 27.3 (the prompt few-shot example that
        # says 27.5 is itself arithmetically wrong).
        assert ReportGeneratorService._scenario_expected_price(scenarios) == pytest.approx(27.3)

    def test_range_target_price_uses_midpoint(self):
        scenarios = [{"case": "Base", "probability": 100, "targetPrice": "25-35元"}]
        assert ReportGeneratorService._scenario_expected_price(scenarios) == pytest.approx(30.0)

    def test_garbage_returns_none(self):
        assert ReportGeneratorService._scenario_expected_price(None) is None
        assert ReportGeneratorService._scenario_expected_price([]) is None
        assert ReportGeneratorService._scenario_expected_price(
            [{"case": "X", "probability": "abc", "targetPrice": "N/A"}]) is None


# ─────────────── ERP single definition point ───────────────
class TestERPSingleDefinition:
    def test_renderer_and_provider_share_one_constant(self):
        # Same object: report_generator_service imports it from the provider
        # module (single source of truth), so the two WACC estimations can
        # never drift apart again.
        assert rgs.EQUITY_RISK_PREMIUM is EQUITY_RISK_PREMIUM
        assert EQUITY_RISK_PREMIUM == 0.055

    def test_renderer_uses_shared_erp_in_output(self):
        res = _svc()._compute_valuation(
            {"financials": {"beta": 1.0, "rf": 0.0173}}, {"market": "A-Share"})
        assert "ERP=5.5%" in res["source"]


# ─────────────── computation_tools: tightened DCF validation bounds ───────────────
class TestComputationToolsBounds:
    """dcf_calculate 校验边界收紧：β∈[0.2, 3]、WACC∈[max(Rf+2%, 5%), 20%]、
    g≤Rf、WACC−g≥2%（利差不足拒绝而非 clamp 硬算）。

    yfinance.Ticker 打桩为异常 → Rf 回退 4.2%，全部离线运行。
    """

    _BASE = {
        "fcf_base": 100.0,
        "growth_rates": [0.10, 0.08, 0.07, 0.06, 0.05],
        "terminal_growth": 0.03,
        "wacc": 0.09,
        "shares_outstanding": 10.0,
        "net_debt": 50.0,
    }

    @patch("yfinance.Ticker", side_effect=Exception("offline"))
    def test_valid_params_pass(self, _mock_yf):
        assert "DCF ERROR" not in dcf_calculate(dict(self._BASE))

    @patch("yfinance.Ticker", side_effect=Exception("offline"))
    def test_beta_below_tightened_floor_rejected(self, _mock_yf):
        # β 下限从 0 收紧到 0.2：β=0.1 拒绝（此前会放行进入 CAPM）。
        res = dcf_calculate(dict(self._BASE, beta=0.1))
        assert "DCF ERROR: Unreasonable beta" in res
        assert "0.2" in res and "3.0" in res

    @patch("yfinance.Ticker", side_effect=Exception("offline"))
    def test_wacc_below_floor_rejected(self, _mock_yf):
        # β=0.2 → Ke = 4.2% + 0.2×5.5% = 5.3% < floor max(4.2%+2%, 5%) = 6.2%。
        res = dcf_calculate(dict(self._BASE, beta=0.2))
        assert "DCF ERROR: Unreasonable WACC" in res
        assert "max(Rf+2%, 5%)" in res

    @patch("yfinance.Ticker", side_effect=Exception("offline"))
    def test_terminal_growth_above_rf_rejected(self, _mock_yf):
        # g≤Rf：Rf=4.2%，g=5% 拒绝（旧口径 8% 上限会放行）。
        res = dcf_calculate(dict(self._BASE, terminal_growth=0.05))
        assert "DCF ERROR: Unreasonable terminal growth rate" in res
        assert "risk-free rate" in res
