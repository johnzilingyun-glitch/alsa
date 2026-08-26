"""Regression tests: HK-share deep fundamentals must not be mostly N/A.

Root cause (2026-08): a_stock_direct.get_financial_summary's HK fast path mapped
only 7 of the ~25 indicators that EastMoney HK F10 (RPT_HKF10_FN_MAININDICATOR)
returns, so the deep report's "深度基本面指标" table showed N/A for 36/46 rows
on HK shares. Also: A-share financials emit `revenueGrowthYoY` but the report
compiler only looked for `revenueYoY`/`revenueGrowth` (营收同比增长 was N/A too),
and Tencent's HK quote reports market cap in 亿 units while the rest of the
pipeline uses raw yuan.
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.services.report_generator_service import ReportGeneratorService

# A realistic EastMoney HK F10 row (shape of RPT_HKF10_FN_MAININDICATOR)
HK_F10_ROW = {
    "report_date": "2026-03-31",
    "report_type": "2026年一季报",
    "OPERATE_INCOME": 316135036.49,
    "OPERATE_INCOME_YOY": 10.0223006179,
    "HOLDER_PROFIT": 238356654.58,
    "HOLDER_PROFIT_YOY": 479.6682829806,
    "PRETAX_PROFIT": 256055391.68,
    "GROSS_PROFIT": 64763236.7,
    "GROSS_PROFIT_RATIO": 20.485940887494,
    "NET_PROFIT_RATIO": 75.395446255,
    "BASIC_EPS": 0.32,
    "DILUTED_EPS": 0.32,
    "EPS_TTM": 0.660678372399,
    "BPS": 11.418932783827,
    "ROE_AVG": 2.823840404613,
    "ROA": 2.417560608161,
    "DEBT_ASSET_RATIO": 14.7430782535,
    "TOTAL_ASSETS": 10036865856.21,
    "TOTAL_LIABILITIES": 1479742987.38,
    "TOTAL_PARENT_EQUITY": 8556756955.86,
    "NETCASH_OPERATE": 127611163.08,
    "END_CASH": 983084920.32,
    "DPS_HKD": 0.13786,
    "DIVIDEND_RATE": 0.501309090909,
    "PE_TTM": 37.119734600669,
    "PB_TTM": 2.126391796823,
    "TOTAL_MARKET_CAP": 20607076050,
}
HK_F10_ROW2 = {
    "report_date": "2025-12-31",
    "report_type": "2025年年报",
    "OPERATE_INCOME": 1657624000,
    "HOLDER_PROFIT": 297841000,
}


def _hk_financials_patch(monkeypatch, rows):
    from python_service.app.services.data_providers import a_stock_direct as m
    async def _fake_fetch_hk_financials(symbol, periods=4):
        return [dict(r) for r in rows]
    async def _fake_fetch_tencent_quote(symbols):
        return [{
            "code": "06127", "name": "昭衍新药", "price": 26.74,
            "pe": 60.77, "pb": None, "market_cap": 200.3757, "change_pct": -1.6,
        }]
    monkeypatch.setattr(m, "fetch_hk_financials", _fake_fetch_hk_financials)
    monkeypatch.setattr(m, "fetch_tencent_quote", _fake_fetch_tencent_quote)


def test_hk_financial_summary_maps_all_f10_fields(monkeypatch):
    """The HK fast path must surface every report-compiler key, not just 7."""
    from python_service.app.services.data_providers.a_stock_direct import AStockDirectProvider
    _hk_financials_patch(monkeypatch, [HK_F10_ROW, HK_F10_ROW2])

    import asyncio
    provider = AStockDirectProvider()
    res = asyncio.run(provider.get_financial_summary("06127.HK"))

    # Key metrics that were N/A before the fix
    assert res.get("pb") == 2.126391796823, "PB must come from PB_TTM (Tencent HK has no PB)"
    assert res.get("priceToBook") == 2.126391796823
    assert res.get("profitMargin") == 0.75395446255, "net margin must be decimal fraction"
    assert res.get("roa") == 2.417560608161
    assert res.get("debtRatio") == 14.7430782535
    assert res.get("operatingCashflow") == 127611163.08
    assert res.get("totalCash") == 983084920.32
    assert res.get("dividendYield") == 0.501309090909
    assert res.get("marketCap") == 20607076050, "market cap must be raw yuan (not 亿 units)"
    assert res.get("enterpriseValue") == 20607076050 + 1479742987.38 - 983084920.32
    assert res.get("revenueYoY") == 10.0223006179
    assert res.get("netProfitYoY") == 479.6682829806
    # QoQ between 一季报 and 年报 must NOT be computed (different frequencies)
    assert res.get("revenueQoQ") is None
    assert res.get("netProfitQoQ") is None


def test_hk_report_fundamentals_not_mostly_na(monkeypatch):
    """The deep-fundamentals table for a HK share must be mostly populated."""
    from python_service.app.services.data_providers.a_stock_direct import AStockDirectProvider
    _hk_financials_patch(monkeypatch, [HK_F10_ROW, HK_F10_ROW2])

    import asyncio
    provider = AStockDirectProvider()
    res = asyncio.run(provider.get_financial_summary("06127.HK"))

    service = ReportGeneratorService()
    fund = service._compile_fundamentals(
        {"financials": res, "quote": {"currency": "CNY", "changePercent": -1.6}},
        "CNY", {}, market="HK-Share",
    )
    na_fields = [k for k, v in fund.items() if v == "N/A"]
    # Was 36/46 N/A; the remaining N/A fields are genuinely unavailable in HK F10
    assert len(na_fields) <= 26, f"too many N/A fields: {na_fields}"

    # Spot-check previously-broken rows
    assert fund["总市值"] == "206.07亿 CNY", fund["总市值"]
    assert fund["企业价值 (EV)"] == "211.04亿 CNY"
    assert fund["市净率 (PB)"] == "2.13"
    assert fund["总资产收益率 (ROA)"] == "2.42%"
    assert fund["净利率"] == "75.4%"
    assert fund["资产负债率"] == "14.74%"
    assert fund["经营现金流"] == "1.28亿 CNY"
    assert fund["总现金(含短投)"] == "9.83亿 CNY"
    assert fund["股息率"] == "0.5%"
    assert fund["营收同比增长 (YoY)"] == "10.02%"
    assert fund["净利润同比增长 (YoY)"] == "479.67%"


def test_compiler_recognizes_revenue_growth_yoy_alias():
    """A-share financials emit revenueGrowthYoY — the compiler must honor it."""
    service = ReportGeneratorService()
    financials = {
        "revenueGrowthYoY": 10.02,
        "netProfitGrowthYoY": 479.67,
        "netProfitGrowth": 479.67,
    }
    fund = service._compile_fundamentals(
        {"financials": financials, "quote": {"currency": "CNY", "changePercent": 1.0}},
        "CNY", {}, market="A-Share",
    )
    assert fund["营收同比增长 (YoY)"] == "10.02%", fund["营收同比增长 (YoY)"]
    assert fund["净利润同比增长 (YoY)"] == "479.67%"
