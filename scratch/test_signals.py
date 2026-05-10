"""Test signal dot rendering with LI's actual metric values"""
import sys
sys.path.insert(0, '.')
from python_service.app.services.report_generator_service import ReportGeneratorService

svc = ReportGeneratorService()

test_cases = [
    ("市盈率 (PE)", "112.5"),
    ("市净率 (PB)", "1.72"),
    ("PEG", "0.99"),
    ("市销率 (PS)", "0.16"),
    ("EV/EBITDA", "-11.0"),
    ("净资产收益率 (ROE)", "1.58%"),
    ("总资产收益率 (ROA)", "-0.17%"),
    ("毛利率", "18.68%"),
    ("营业利润率", "-1.37%"),
    ("净利率", "1.0%"),
    ("营收同比增长 (YoY)", "-22.25%"),
    ("营收环比增长 (QoQ)", "5.16%"),
    ("净利润同比增长 (YoY)", "-99.81%"),
    ("净利润环比增长 (QoQ)", "1.01%"),
    ("营收3年复合增长 (CAGR)", "35.36%"),
    ("净利润3年复合增长 (CAGR)", "-17.63%"),
    ("资产负债率", "24.48%"),
    ("流动比率", "1.93"),
    ("速动比率", "1.88"),
    ("分红率", "0.0%"),
    ("股息率", "N/A"),
    ("股价百分位 (52周)", "14.04%"),
    ("PE百分位", "N/A"),
    ("总市值", "183.79亿 USD"),
    ("企业价值 (EV)", "N/A"),
    ("大股东持股", "0.01% (ADS口径)"),
    ("机构持仓", "4.02% (ADS口径)"),
]

print(f"{'Metric':<30} {'Value':<20} {'Signal':<8} {'Parsed':<10}")
print("-" * 70)
for name, val in test_cases:
    signal = svc._get_metric_signal(name, val)
    parsed = svc._parse_metric_value(val)
    emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}.get(signal, "?")
    print(f"{name:<30} {val:<20} {emoji:<8} {parsed}")
