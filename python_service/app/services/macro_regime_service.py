"""
Macro Regime Detector — Cross-asset ratio analysis using yfinance.
Detects structural macro regime transitions (1-2 year horizon).

Ratios analyzed:
- Copper/Gold (Dr. Copper: economic expansion vs contraction)
- XLY/XLP (Consumer Discretionary vs Staples: risk-on vs risk-off)
- HYG/TLT (High Yield vs Treasuries: credit risk appetite)
- IWM/SPY (Small Cap vs Large Cap: breadth of rally)
- TIP/TLT (TIPS vs Treasuries: inflation expectations)
"""

import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cross-asset ratio pairs for regime detection
RATIO_PAIRS = [
    {"name": "Copper/Gold", "num": "HG=F", "den": "GC=F", "signal": "经济扩张 vs 收缩"},
    {"name": "XLY/XLP", "num": "XLY", "den": "XLP", "signal": "风险偏好 vs 避险"},
    {"name": "HYG/TLT", "num": "HYG", "den": "TLT", "signal": "信用扩张 vs 收缩"},
    {"name": "IWM/SPY", "num": "IWM", "den": "SPY", "signal": "小盘领涨 vs 大盘集中"},
    {"name": "TIP/TLT", "num": "TIP", "den": "TLT", "signal": "通胀预期升温 vs 降温"},
]


def _compute_regime_sync() -> dict:
    """Blocking function to compute macro regime from yfinance data."""
    try:
        import yfinance as yf
        import math
    except ImportError:
        return {"error": "yfinance not installed"}

    end = datetime.now()
    start_1y = end - timedelta(days=365)
    start_6m = end - timedelta(days=180)

    all_symbols = set()
    for pair in RATIO_PAIRS:
        all_symbols.add(pair["num"])
        all_symbols.add(pair["den"])

    try:
        data = yf.download(list(all_symbols), start=start_1y, end=end, progress=False, auto_adjust=True)
        if data.empty:
            return {"error": "No data returned from yfinance"}
    except Exception as e:
        return {"error": f"yfinance download failed: {e}"}

    close = data["Close"] if "Close" in data.columns.get_level_values(0) else data

    results = []
    bullish_count = 0
    total_valid = 0

    for pair in RATIO_PAIRS:
        try:
            num_data = close[pair["num"]].dropna()
            den_data = close[pair["den"]].dropna()

            if len(num_data) < 20 or len(den_data) < 20:
                continue

            # Align dates
            common_idx = num_data.index.intersection(den_data.index)
            if len(common_idx) < 20:
                continue

            ratio = num_data[common_idx] / den_data[common_idx]

            current = float(ratio.iloc[-1])
            ma50 = float(ratio.iloc[-50:].mean()) if len(ratio) >= 50 else float(ratio.mean())
            ma200 = float(ratio.mean())

            # 6-month change
            six_m_ago_idx = ratio.index[ratio.index >= start_6m]
            if len(six_m_ago_idx) > 0:
                six_m_ago = float(ratio[six_m_ago_idx[0]])
                pct_6m = round((current - six_m_ago) / six_m_ago * 100, 2)
            else:
                pct_6m = 0

            # Trend determination
            above_ma50 = current > ma50
            above_ma200 = current > ma200
            if above_ma50 and above_ma200:
                trend = "上升趋势"
                bullish_count += 1
            elif not above_ma50 and not above_ma200:
                trend = "下降趋势"
            else:
                trend = "转换中"
                bullish_count += 0.5

            total_valid += 1

            results.append({
                "pair": pair["name"],
                "signal_meaning": pair["signal"],
                "current_ratio": round(current, 4),
                "ma50": round(ma50, 4),
                "ma200": round(ma200, 4),
                "6m_change_pct": pct_6m,
                "trend": trend,
            })
        except Exception as e:
            logger.warning(f"Failed to compute ratio {pair['name']}: {e}")

    if total_valid == 0:
        return {"error": "No valid ratio data computed"}

    # Overall regime classification
    bullish_pct = bullish_count / total_valid * 100
    if bullish_pct >= 80:
        regime = "RISK-ON EXPANSION"
        regime_zh = "风险偏好扩张期"
        description = "多数跨资产比率指向经济扩张和风险偏好上升"
    elif bullish_pct >= 60:
        regime = "MODERATE GROWTH"
        regime_zh = "温和增长期"
        description = "多数信号偏多，但部分领域出现分歧"
    elif bullish_pct >= 40:
        regime = "TRANSITION"
        regime_zh = "转换/震荡期"
        description = "多空信号交织，市场处于方向选择阶段"
    elif bullish_pct >= 20:
        regime = "MODERATE CONTRACTION"
        regime_zh = "温和收缩期"
        description = "多数信号偏空，信用和风险偏好收缩"
    else:
        regime = "RISK-OFF CONTRACTION"
        regime_zh = "风险规避收缩期"
        description = "跨资产全面指向经济收缩和避险"

    return {
        "regime": regime,
        "regime_zh": regime_zh,
        "description": description,
        "bullish_pct": round(bullish_pct, 1),
        "ratios": results,
        "timestamp": datetime.now().isoformat(),
    }


async def get_macro_regime() -> dict:
    """Async wrapper for macro regime computation."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _compute_regime_sync)


# Format as text for prompt injection
async def get_macro_regime_text() -> str:
    """Get macro regime as formatted text for prompt injection."""
    data = await get_macro_regime()
    if "error" in data:
        return f"⚠ Macro Regime Detection Failed: {data['error']}"

    lines = [
        f"## 🌐 宏观体制检测 (Macro Regime Detector)",
        f"**当前体制**: {data['regime_zh']} ({data['regime']})",
        f"**判断依据**: {data['description']}",
        f"**多头信号占比**: {data['bullish_pct']}%",
        "",
        "| 比率 | 含义 | 当前值 | MA50 | MA200 | 6M变化 | 趋势 |",
        "|------|------|--------|------|-------|--------|------|",
    ]
    for r in data.get("ratios", []):
        lines.append(
            f"| {r['pair']} | {r['signal_meaning']} | {r['current_ratio']} | {r['ma50']} | {r['ma200']} | {r['6m_change_pct']}% | {r['trend']} |"
        )

    return "\n".join(lines)
