import os
import sys
import pytest
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.app.services.report_generator_service import ReportGeneratorService

def test_restructured_html_rendering():
    # Instantiate service
    service = ReportGeneratorService()

    # Formulate mock report data
    data = {
        "info": {
            "name": "藏格矿业",
            "symbol": "000408",
            "market": "A-Share",
            "price": 28.5,
            "changePercent": 2.5,
            "currency": "CNY",
            "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M")
        },
        "fund": {
            "总市值": "320亿 CNY",
            "企业价值 (EV)": "310亿 CNY",
            "净利润": "11.24亿 CNY",
            "扣非净利润": "10.85亿 CNY",
            "市盈率 (PE)": "12.5",
            "市净率 (PB)": "2.8",
            "PEG": "0.95",
            "市销率 (PS)": "4.2",
            "EV/EBITDA": "8.5",
            "净资产收益率 (ROE)": "18.5%",
            "毛利率": "45.2%",
            "净利率": "25.2%",
            "营收同比增长 (YoY)": "12.5%",
            "净利润同比增长 (YoY)": "15.2%"
        },
        "verdict": "钾锂双轮驱动，低估值周期筑底，具备极高安全边际",
        "action_stance": "建议逢低建仓",
        "tagline": "藏格矿业：钾锂双轮驱动，低估值筑底期凸显现金牛价值",
        "investment_thesis": "行业大宗出清筑底，供给刚性下钾锂价格面临回升拐点",
        "factor_profile": {
            "size": "中盘股",
            "style": "周期/价值",
            "volatility": "中等波动",
            "expected_return": "稳健高分红 + 周期商品价格上涨弹性"
        },
        "consensus_vs_non_consensus": {
            "market_consensus": "碳酸锂价格探底拖累业绩，短期估值难以修复",
            "our_alpha": "钾肥高景气提供利润托底，锂盐高毛利保障自由现金流，且西藏盐湖投产预期差被市场忽视"
        },
        "the_call": "在价格触及支撑位27.5-28.0元时启动第一阶段分批买入，回撤超10%强制止损。",
        "catalyst_calendar": [
            {
                "event": "年报披露及高分红预案公告",
                "date": "2026-06-15",
                "impact_logic": "股息率若超5%将吸引红利资金和被动宽基流入"
            },
            {
                "event": "西藏麻米错盐湖项目环评批复",
                "date": "2026-07-20",
                "impact_logic": "核心产能拐点确认，启动估值整体上修"
            }
        ],
        "stock_archetype": "Cyclical",
        "wacc_breakdown": {
            "rf": "2.35%",
            "beta": "1.05",
            "erp": "6.0%",
            "kd": "4.2%",
            "tc": "15%",
            "d_v": "5%",
            "e_v": "95%",
            "wacc": "8.3%",
            "source": "中债10年期国债收益率作为Rf，有色金属/采掘行业Beta，公司财务费用除以有息负债测算有息债务成本Kd"
        },
        "kill_switch": {
            "condition": "国内钾肥现货价跌破 1,800 元/吨或碳酸锂价格跌破 7 万元/吨",
            "status": "SAFE"
        },
        "market_wind_control": {
            "lockup_date": "2026-09-12 (5000万股定向增发限售股解禁)",
            "lockup_impact": "解禁比例约占流通盘3%，带来中等短期流动性压制，需提前减持防范",
            "reduction_plan": "大股东及高管公告承诺未来6个月内无减持计划",
            "crowding_level": "公募持仓占比处于历史 25% 分位数，未出现交易拥挤或踩踏风险"
        },
        "trading_discipline": {
            "left_side_condition": "日成交额萎缩至1.5亿元极度地量，价格回踩200日均线支撑位",
            "right_side_trigger": "突破MA60且单日成交量超5日均量1.5倍",
            "max_drawdown_limit": "-10% (强制止损熔断)",
            "thesis_invalidation_trigger": "若藏格钾肥产能扩建项目被环保监管机构否决，则核心逻辑证伪平仓"
        },
        "data_completeness": {
            "score": 95,
            "missing": ["碳酸锂高频社会库存"],
            "impact": "微调对毛利率的短期波动敏感性分析"
        },
        "peer_comparison": [
            {
                "name": "藏格矿业",
                "symbol": "000408",
                "pe": 12.5,
                "pb": 2.8,
                "roe": 18.5,
                "margin": 25.2,
                "marketCap": "320亿",
                "vs_target": "标的"
            },
            {
                "name": "盐湖股份",
                "symbol": "000792",
                "pe": 15.2,
                "pb": 3.1,
                "roe": 16.2,
                "margin": 22.1,
                "marketCap": "950亿",
                "vs_target": "估值折价合理"
            }
        ],
        "summary": "分析概要主要描述基本面周期拐点...",
        "moat_summary": "稀缺的采矿权资源壁垒...",
        "moat_points": ["国内独占性采矿权", "极低成本提锂工艺"],
        "macro_summary": "宏观大宗供给收缩...",
        "macro_points": ["国家钾肥储备战略", "新能源车需求托底"],
        "trading_plan": "整体操作计划描述...",
        "trading_steps": [
            {
                "level": "第一层",
                "price": "28.0 CNY",
                "weight": "30%",
                "logic": "回踩MA200支撑"
            },
            {
                "level": "第二层",
                "price": "29.5 CNY",
                "weight": "40%",
                "logic": "放量金叉确认"
            }
        ],
        "risks_points": ["锂价长期不振风险", "海外投资受阻风险"],
        "key_opps": ["钾肥涨价", "西藏新产能释放"],
        "key_risks": ["大盘估值回落", "环保红线收紧"],
        "scenarios": [
            {
                "case": "看多",
                "probability": 30,
                "targetPrice": "35.0 CNY",
                "logic": "锂价平稳回升且新产能加速投产"
            },
            {
                "case": "基准",
                "probability": 50,
                "targetPrice": "30.0 CNY",
                "logic": "钾肥价格维持高位，锂价磨底"
            },
            {
                "case": "看空",
                "probability": 20,
                "targetPrice": "24.0 CNY",
                "logic": "锂价暴跌，扩产项目环评审批延误"
            }
        ],
        "score": 82,
        "recommendation": "BUY",
        "discussion": [
            {
                "role": "Chief Strategist",
                "content": "<p>首席策略师多轮观点汇总...</p>"
            },
            {
                "role": "Fundamental Analyst",
                "content": "<p>基本面分析师多轮观点汇总...</p>"
            }
        ]
    }

    # 1. Render and Validate A-Share
    data["info"]["market"] = "A-Share"
    html_a = service._render_html(data)
    assert "第一层：核心决策包" in html_a
    assert "第二层：逻辑链条与数据实证" in html_a
    assert "第三层：交易执行单与风险防线" in html_a
    assert "因子雷达" in html_a
    assert "多空共识差" in html_a
    assert "催化剂事件日历" in html_a
    assert "WACC 贴现模型白箱审计" in html_a
    assert "防伪红线 (Kill Switch)" in html_a
    assert "限售股解禁日历" in html_a
    assert "减持公告与拥挤度" in html_a
    assert "左右侧交易信号条件" in html_a
    assert "单票回撤上限" in html_a
    assert "附录：" in html_a or "专家研讨" in html_a

    # 2. Render and Validate HK-Share
    data["info"]["market"] = "HK-Share"
    html_hk = service._render_html(data)
    assert "基石/主要股东禁售解禁" in html_hk
    assert "港股通持股与大股东质押" in html_hk

    # 3. Render and Validate US-Share
    data["info"]["market"] = "US-Share"
    html_us = service._render_html(data)
    assert "内部人交易 Form 4" in html_us
    assert "空头头寸与机构持仓" in html_us

    # Keep html as html_a for output inspection
    html = html_a

    # Write output file for visual inspection
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../scratch'))
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "test_rendered_report.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"\n[Test Success] Rendered HTML written to: {output_path}")

if __name__ == "__main__":
    test_restructured_html_rendering()
