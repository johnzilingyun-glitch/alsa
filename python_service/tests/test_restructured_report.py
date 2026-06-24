import os
import sys
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
        "summary": "藏格矿业作为国内钾肥双巨头之一，依托察尔汗盐湖低成本提钾资源禀赋构建稳固护城河；西藏麻米错盐湖锂项目打开第二增长曲线，碳酸锂价格探底后有望迎来量价齐升。当前估值处于历史低位区间，叠加高分红政策提供安全边际，建议在技术支撑位分批建仓。",
        "moat_summary": "藏格矿业的核心护城河体现在三个方面：第一，察尔汗盐湖采矿权的独占性——国内钾肥资源集中在青海察尔汗地区，公司拥有该区域最优质的卤水资源，新进入者几乎不可能获得同等开采权；第二，极低的提锂成本——公司采用自主研发的吸附法提锂工艺，碳酸锂单吨完全成本约4.5万元，远低于锂辉石提锂路线的8-10万元，在全球锂价下行周期中具备极强的成本护城河；第三，钾锂联产的协同效应——同一卤水资源先提钾后提锂，大幅摊薄固定成本，使得公司毛利率长期维持在45%以上，远超行业平均水平。",
        "moat_points": ["国内独占性察尔汗盐湖采矿权", "极低成本吸附法提锂工艺（单吨成本<5万元）", "钾锂联产协同效应，毛利率长期45%+"],
        "macro_summary": "宏观层面，全球钾肥供给格局持续收紧——白俄罗斯和俄罗斯两大钾肥出口国受地缘政治影响产能受限，加拿大Nutrien暂缓扩产计划，导致全球钾肥价格维持在3,500-4,000元/吨的偏强区间。国内方面，粮食安全上升为国家战略，农业农村部要求2026年化肥保供稳价，钾肥进口依赖度（约50%）居高不下，国内钾肥企业享有政策红利。资金面来看，北向资金近三个月累计增持藏格矿业12亿元，公募持仓比例从4.2%升至6.8%，显示机构对周期底部反转的提前布局。技术面上，股价在27.5元附近形成三重底支撑，MACD周线级别底背离已经形成。",
        "macro_points": ["全球钾肥供给刚性收缩，价格维持偏强区间", "国家粮食安全战略推动化肥保供稳价政策", "北向资金持续增持+公募仓位翻倍", "周线MACD底背离，三重底支撑确认"],
        "trading_plan": "整体操作策略：采取'左侧试探+右侧确认'的分批建仓方式，在27.5-29.5元区间分两层介入，累计目标仓位不超过总组合的15%。第一层在28.0元附近（回踩200日均线支撑位）介入30%目标仓位作为底仓观察；第二层等待放量突破MA60后追加40%目标仓位进行右侧确认。止损纪律：单票绝对回撤-10%强制平仓止损，不设条件、不找借口。核心逻辑证伪条件为：若碳酸锂现货价格跌破7万元/吨且持续超过1个月，或西藏麻米错盐湖项目环评被正式否决，则清仓离场。",
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
                "content": "<h2>1️⃣ 首席策略师综合判决</h2><p><strong>最终评级：BUY（买入）</strong></p><p>藏格矿业当前处于周期底部+低估值+高分红的三重安全边际叠加窗口。钾肥业务提供稳定现金流（吨毛利>800元），锂盐业务提供弹性（碳酸锂价格每上涨1万元，年化净利润增厚约3.5亿元）。西藏麻米错盐湖项目预计2026Q4投产，届时碳酸锂权益产能将从当前的1万吨增至3万吨，这是市场尚未充分定价的预期差。</p><p>建议以28.0元为第一建仓点（对应2026年PE 11.5倍），分两层完成建仓，单票回撤-10%强制熔断。核心逻辑证伪条件为碳酸锂<7万元/吨持续1个月或西藏项目环评被否。</p><h2>2️⃣ 情景概率与期望价格</h2><table><tr><th>情景</th><th>概率</th><th>目标价</th><th>核心驱动</th></tr><tr><td>看多</td><td>30%</td><td>35.0 CNY</td><td>锂价回升+西藏产能释放</td></tr><tr><td>基准</td><td>50%</td><td>30.0 CNY</td><td>钾肥维稳+锂价磨底</td></tr><tr><td>看空</td><td>20%</td><td>24.0 CNY</td><td>锂价破位+环评延误</td></tr></table><p><strong>概率加权期望价格：30.3 CNY（较现价28.5元上涨空间6.3%）</strong></p>"
            },
            {
                "role": "Fundamental Analyst",
                "content": "<h2>1️⃣ 财务健康度评估</h2><p><strong>总评分：78/100（健康区间）</strong></p><p>资产负债率仅28%，有息负债率15%，账上货币资金+交易性金融资产合计45亿元，覆盖一年内到期有息负债的3.2倍。2025年经营活动现金流净额22.6亿元，自由现金流18.1亿元，资本开支9.2亿元主要用于西藏项目前期投入。</p><h2>2️⃣ 盈利质量分析</h2><p>2025年实现营收44.6亿元（+12.5% YoY），归母净利润11.24亿元（+15.2% YoY），扣非净利润10.85亿元。毛利率45.2%（同比+1.8pct），净利率25.2%（同比+1.2pct）。ROE 18.5%，在化工/采掘行业中处于前25%分位。钾肥板块贡献营收占比58%、毛利占比65%；锂盐板块营收占比28%、毛利占比25%。</p><h2>3️⃣ 估值横向对比</h2><p>TTM PE 12.5倍，处于近5年历史分位的22%低位区间。PB 2.8倍，低于盐湖股份（3.1倍）和钾肥国际（3.5倍）。PEG 0.95（<1表明成长性尚未被估值充分反映）。EV/EBITDA 8.5倍也低于行业可比公司中位数9.8倍。</p>"
            },
            {
                "role": "Risk Manager",
                "content": "<h2>1️⃣ 风险评估矩阵</h2><table><tr><th>风险类型</th><th>严重度</th><th>概率</th><th>应对措施</th></tr><tr><td>碳酸锂价格持续下跌</td><td>高</td><td>25%</td><td>跌破7万/吨触发减仓</td></tr><tr><td>西藏项目环评延期</td><td>中</td><td>20%</td><td>密切跟踪审批进度</td></tr><tr><td>钾肥进口冲击</td><td>中</td><td>15%</td><td>关注俄白钾肥出口政策</td></tr><tr><td>汇率波动风险</td><td>低</td><td>10%</td><td>公司外销占比<10%</td></tr></table><h2>2️⃣ 最大回撤测算</h2><p>基于历史波动率（年化32%）和当前估值分位，95%置信度下的1个月VaR约为-8.5%。建议将单票硬止损设在-10%，组合层面设置-15%的行业集中度上限。</p><h2>3️⃣ 防伪红线（Kill Switch）</h2><p><strong>基本面证伪条件：</strong>国内钾肥现货价跌破1,800元/吨或碳酸锂价格跌破7万元/吨且持续超过1个月。</p><p><strong>技术面熔断条件：</strong>单票绝对回撤超-10%强制平仓，不设条件不找借口。</p>"
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
