"""Test _json_to_markdown with actual Chief Strategist output"""
import sys, json
sys.path.insert(0, '.')

from python_service.app.services.report_generator_service import ReportGeneratorService

svc = ReportGeneratorService()

test_json = '''{
  "tagline": "LI：$14.47净现金铁底对抗FCF烈焰",
  "investmentThesis": "理想汽车处于罕见极端状态",
  "sentiment": "HOLD（观望等待）",
  "expectedPrice": {
    "calculation": "25%×$22.00 + 45%×$18.00 + 30%×$13.50",
    "result": 17.65,
    "vsCurrentPrice": -0.35,
    "expectedReturn": "-1.94%"
  },
  "masterVariable": {
    "variable": "产品周期能否逆转营收下滑",
    "currentStatus": "未知",
    "bullThreshold": "锁单≥5,000台",
    "bearThreshold": "锁单<2,000台"
  },
  "tradingPlan": {
    "entryZone": "$17.00-18.50",
    "targetPrice": "$22.00",
    "stopLoss": "$16.50",
    "riskRewardRatio": 1.73,
    "strategy": "等待催化剂信号"
  },
  "kellyPosition": {
    "b": 1.50,
    "p": 0.40,
    "q": 0.60,
    "f": "0.00 (0%)",
    "halfKelly": "0.00 (0%)"
  },
  "timeHorizon": {
    "short": {"period": "1-2周", "action": "观望", "logic": "等待事件"},
    "medium": {"period": "1-3个月", "action": "条件建仓", "logic": "数据验证"},
    "long": {"period": "3-6个月", "action": "加仓或清仓", "logic": "Q2财报"}
  },
  "buildPlan": [
    {"level": "Phase 1", "price": "$17.20", "weight": "30%", "cumulativePosition": "30%", "logic": "首次触及支撑"},
    {"level": "Phase 2", "price": "$18.95", "weight": "40%", "cumulativePosition": "70%", "logic": "放量突破"},
    {"level": "Phase 3", "price": "$19.64", "weight": "30%", "cumulativePosition": "100%", "logic": "三重确认"}
  ],
  "keyRevisionsToPriorAnalyses": {
    "netCashPerShare": "从$13.60修正为$14.47",
    "bullProbability": "从35%下调至25%"
  },
  "falsificationRedlines": [
    {"condition": "L9 Livis首月锁单<2,000台", "window": "2026年6月15日前", "action": "清仓"},
    {"condition": "Q2毛利率<18%", "window": "2026年8月财报", "action": "清仓"},
    {"condition": "连续2日收盘<$16.50", "window": "任何时间", "action": "立即清仓"}
  ]
}'''

result = svc._json_to_markdown(test_json)
if result:
    print("=== SUCCESS ===")
    print(result[:2000])
    print(f"\n... total {len(result)} chars")
else:
    print("=== FAILED: returned empty ===")

# Also test with mixed markdown + trailing JSON
mixed = "这是一段分析报告\n\n## 核心观点\n\n理想汽车值得关注\n\n" + test_json
import asyncio
async def test_normalize():
    html = await svc._normalize_log_style(mixed)
    has_codehilite = 'codehilite' in html
    has_tagline = 'tagline' in html.lower() or '核心论点' in html
    print(f"\n=== MIXED CONTENT TEST ===")
    print(f"Has code block (bad): {has_codehilite}")
    print(f"Has rendered tagline (good): {has_tagline}")
    # Check for raw JSON
    has_raw_json = '"tagline"' in html and 'codehilite' in html
    print(f"Has raw JSON in code block (bad): {has_raw_json}")
    print(f"HTML length: {len(html)}")

asyncio.run(test_normalize())
