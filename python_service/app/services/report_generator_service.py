import os
import json
import re
import asyncio
import markdown2
from datetime import datetime
from typing import List, Any, Dict
from .llm_gateway import llm_gateway

class ReportGeneratorService:
    def generate_report(self, run, outputs: List) -> str:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.generate_html_report_async({
            "symbol": run.symbol,
            "market": run.market,
            "discussion": [{"role": art.artifact_type.replace("_output", "").replace("_", " ").title(), "content": art.content} for art in outputs],
            "snapshot": run.market_snapshot
        }, f"{run.symbol}_report.html"))

    def generate_html_report(self, result: dict, output_path: str) -> str:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.generate_html_report_async(result, output_path))

    async def generate_html_report_async(self, result: dict, output_path: str) -> str:
        symbol = result.get("symbol", "UNKNOWN")
        market = result.get("market", "US-Share")
        discussion_msgs = result.get("discussion", [])
        snapshot = result.get("snapshot") or {}
        
        full_discussion = "\n".join([f"[{m['role']}]: {m['content']}" for m in discussion_msgs])
        
        # UI Data Expert Pass - REFINED CONTENT (RESTORING RAW LOGS)
        ui_data = await self._run_ui_data_expert(symbol, market, snapshot, full_discussion)
        
        quote = snapshot.get("quote", {})
        currency = quote.get("currency", "USD" if "US" in market else "CNY")
        fundamentals = self._compile_fundamentals(snapshot, currency, ui_data)
        
        data = {
            "info": {
                "name": quote.get("name", symbol),
                "symbol": symbol,
                "market": market,
                "price": quote.get("price", "N/A"),
                "changePercent": quote.get("changePercent", 0),
                "currency": currency,
                "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M")
            },
            "fund": fundamentals,
            "summary": ui_data.get("summary", "总结提炼中..."),
            "moat_summary": ui_data.get("moat_summary", ""),
            "moat_points": ui_data.get("moat_points", []),
            "macro_summary": ui_data.get("macro_summary", ""),
            "macro_points": ui_data.get("macro_points", []),
            "trading_plan": ui_data.get("trading_plan", "交易计划生成中..."),
            "trading_steps": ui_data.get("trading_steps", []),
            "risks_points": ui_data.get("risks_points", []),
            "key_opps": ui_data.get("upside", []),
            "key_risks": ui_data.get("downside", []),
            "scenarios": ui_data.get("scenarios", self._default_scenarios()),
            "score": ui_data.get("score", 75),
            "recommendation": ui_data.get("recommendation", "WATCH"),
            "discussion": [
                {"role": m["role"], "content": await self._normalize_log_style(m["content"])}
                for m in discussion_msgs
            ]
        }
        
        html = self._render_html(data)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return os.path.abspath(output_path)

    async def _run_ui_data_expert(self, symbol: str, market: str, snapshot: dict, discussion: str) -> dict:
        prompt = f"""You are the ALSA UI Data Expert. Your task is to extract and organize the core insights from the expert discussion for {symbol}.

STRICT JSON STRUCTURE (MUST BE VALID JSON):
{{
  "summary": "...",
  "moat_summary": "...",
  "moat_points": ["Concise factor 1", "Concise factor 2", "..."],
  "macro_summary": "...",
  "macro_points": ["Concise indicator 1", "Concise indicator 2", "..."],
  "trading_plan": "...",
  "trading_steps": [
    {{"level": "第一层", "price": "$410", "weight": "30%", "logic": "..."}},
    {{"level": "第二层", "price": "$395", "weight": "40%", "logic": "..."}}
  ],
  "risks_points": ["Risk point 1", "Risk point 2", "..."],
  "upside": ["Bull driver 1", "2", "3"],
  "downside": ["Bear risk 1", "2", "3"],
  "scenarios": [
    {{"case": "Bull", "probability": 25, "targetPrice": "$500", "logic": "..."}},
    {{"case": "Base", "probability": 50, "targetPrice": "$410", "logic": "..."}},
    {{"case": "Bear", "probability": 25, "targetPrice": "$350", "logic": "..."}}
  ],
  "pe_percentile": "Current PE percentile (e.g. 45%)",
  "asset_turnover": "Asset turnover ratio",
  "inventory_turnover": "Inventory turnover ratio",
  "capex": "CAPEX value",
  "score": 80,
  "recommendation": "BUY"
}}

OUTPUT ONLY THE JSON OBJECT.
"""
        try:
            res = await llm_gateway.generate_content(prompt + f"\n\nEXPERT DISCUSSION:\n{discussion}", model="gemini-1.5-flash")
            match = re.search(r'\{.*\}', res, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {}
        except Exception as e:
            print(f"UI Data Expert Pass Failed: {e}")
            return {}

    async def _normalize_log_style(self, content: str) -> str:
        # Reformat headers to use the 1️⃣ 2️⃣ style without losing text
        prompt = """Reformat the following analyst report to use '1️⃣ Title', '2️⃣ Title' etc. for the main section headers (e.g. change '### 1. Title' or '### Title' to '### 1️⃣ Title'). 
CRITICAL: DO NOT REMOVE, SUMMARIZE, OR CHANGE ANY OTHER TEXT. KEEP ALL TABLES, BULLETS, AND DETAILS EXACTLY AS THEY ARE.
ONLY CHANGE THE HEADER PREFIXES.
"""
        try:
            # Use a more powerful model if possible for high fidelity, but flash is okay if instructed well
            res = await llm_gateway.generate_content(f"{prompt}\n\nCONTENT:\n{content}", model="gemini-1.5-flash")
            return markdown2.markdown(res, extras=["tables", "fenced-code-blocks", "break-on-newline"])
        except:
            return markdown2.markdown(content, extras=["tables", "fenced-code-blocks", "break-on-newline"])

    def _render_html(self, d: dict) -> str:
        info = d["info"]
        fund = d["fund"]
        chg = info["changePercent"]
        chg_color = "#ef4444" if chg < 0 else "#10b981"
        chg_sign = "+" if chg > 0 else ""

        def md(t): return markdown2.markdown(t) if t else ""

        # Categorized Metrics
        categories = [
            {
                "title": "估值定价 (Valuation)",
                "metrics": [
                    ("总市值", "Market Cap"),
                    ("企业价值 (EV)", "含债务的真实估值"),
                    ("市盈率 (PE)", "TTM市盈率"),
                    ("市净率 (PB)", "资产价格倍数"),
                    ("PEG", "判断估值是否被成长性消化"),
                    ("市销率 (PS)", "对亏损或周期行业很关键"),
                    ("EV/EBITDA", "比PE更抗财务操纵")
                ]
            },
            {
                "title": "获利能力 (Profitability)",
                "metrics": [
                    ("净资产收益率 (ROE)", "股东核心报酬率"),
                    ("总资产收益率 (ROA)", "资产利用效率"),
                    ("毛利率", "产品竞争力"),
                    ("营业利润率", "主营获利能力"),
                    ("净利率", "最终盈利水平"),
                    ("每股收益 (EPS)", "单股盈利额")
                ]
            },
            {
                "title": "成长动力 (Growth)",
                "metrics": [
                    ("营收同比增长 (YoY)", "收入扩张速度"),
                    ("净利润同比增长 (YoY)", "盈利增长速度"),
                    ("营收3年复合增长 (CAGR)", "长期成长稳定性"),
                    ("净利润3年复合增长 (CAGR)", "长期获利稳定性")
                ]
            },
            {
                "title": "财务稳健 (Financial Health)",
                "metrics": [
                    ("资产负债率", "财务杠杆水平"),
                    ("流动比率", "短期偿债能力"),
                    ("速动比率", "极致变现偿债能力")
                ]
            },
            {
                "title": "现金流与分红 (Cash Flow)",
                "metrics": [
                    ("经营现金流", "主营吸金能力"),
                    ("自由现金流 (FCF)", "可分配现金"),
                    ("资本开支 (CAPEX)", "再投资力度"),
                    ("分红率", "股东回报慷慨度"),
                    ("股息率", "现金收益率")
                ]
            },
            {
                "title": "股东结构 (Ownership)",
                "metrics": [
                    ("大股东持股", "管理层利益绑定"),
                    ("机构持仓", "聪明钱认可度")
                ]
            },
            {
                "title": "运营效率 (Efficiency)",
                "metrics": [
                    ("总资产周转率", "资产变现速度"),
                    ("存货周转率", "库存周转效率")
                ]
            },
            {
                "title": "市场环境 (Market Context)",
                "metrics": [
                    ("股价百分位 (52周)", "当前价格在年度区间的位次"),
                    ("PE百分位", "当前估值在历史区间的位次")
                ]
            }
        ]

        detailed_fund_html = ""
        for cat in categories:
            items_html = "".join([
                f'<div class="fund-item"><div class="fund-item-label">{k}<span>{desc}</span></div><div class="fund-item-value">{fund.get(k, "N/A")}</div></div>'
                for k, desc in cat["metrics"]
            ])
            detailed_fund_html += f"""
            <div class="fund-category">
                <div class="fund-category-title">{cat['title']}</div>
                <div class="fund-category-grid">{items_html}</div>
            </div>"""

        scenarios = d.get("scenarios", [])
        if not isinstance(scenarios, list) or (len(scenarios) > 0 and not isinstance(scenarios[0], dict)):
            scenarios = self._default_scenarios()

        sc_rows = "".join([
            f'<tr><td><strong>{s.get("case", "N/A")}</strong></td><td>{s.get("probability", 0)}%</td><td><strong>{s.get("targetPrice", "N/A")}</strong></td><td>{s.get("logic", "")}</td></tr>'
            for s in scenarios
        ])

        # Trading Plan Grid
        trading_steps = d.get("trading_steps", [])
        if not isinstance(trading_steps, list) or (len(trading_steps) > 0 and not isinstance(trading_steps[0], dict)):
            trading_steps = []

        trading_steps_html = ""
        for s in trading_steps:
            if not isinstance(s, dict): continue
            trading_steps_html += f"""
            <div class="trade-card">
                <div class="trade-level">{s.get('level', '仓位')}</div>
                <div class="trade-price">{s.get('price', 'N/A')}</div>
                <div class="trade-weight">占比: {s.get('weight', 'N/A')}</div>
                <div class="trade-logic">{s.get('logic', '')}</div>
            </div>"""

        moat_list = "".join([f'<li>{p}</li>' for p in d.get("moat_points", [])])
        macro_list = "".join([f'<li>{p}</li>' for p in d.get("macro_points", [])])
        risk_points_html = "".join([f'<li>{p}</li>' for p in d.get("risks_points", [])])

        log_html = "".join([
            f'<div class="log-msg"><div class="log-role"><span>{m["role"]}</span></div><div class="log-body">{m["content"]}</div></div>'
            for m in d["discussion"]
        ])

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{info["name"]} ({info["symbol"]}) - 深度研究报告</title>
    <style>
        :root {{
            --primary: #1e293b; --accent: #3b82f6; --text: #334155; --light: #f8fafc; --border: #e2e8f0; --bull: #10b981; --bear: #ef4444;
        }}
        body {{ font-family: 'Inter', -apple-system, system-ui, sans-serif; color: var(--text); line-height: 1.6; margin: 0; background: #f1f5f9; }}
        .report-page {{ max-width: 1000px; margin: 40px auto; background: #fff; padding: 60px 80px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border-radius: 4px; border: 1px solid var(--border); }}
        
        /* Header Styling */
        .report-header {{ border-bottom: 2px solid var(--primary); padding-bottom: 25px; margin-bottom: 40px; display: flex; justify-content: space-between; align-items: center; }}
        .brand-logo {{ font-size: 12px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 10px; }}
        .ticker-info h1 {{ margin: 0; font-size: 32px; font-weight: 800; color: var(--primary); }}
        .ticker-sub {{ color: #64748b; font-size: 14px; font-weight: 500; margin-top: 5px; }}
        .price-box {{ text-align: right; }}
        .current-price {{ font-size: 36px; font-weight: 800; color: var(--primary); line-height: 1; }}
        .price-pct {{ font-size: 18px; font-weight: 700; color: {chg_color}; margin-top: 5px; }}

        /* Sections */
        .section {{ margin-bottom: 50px; text-align: left; }}
        .section-title {{ font-size: 20px; font-weight: 800; color: var(--primary); border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 25px; display: flex; align-items: center; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; }}
        .section-title::before {{ content: ''; display: inline-block; width: 4px; height: 20px; background: var(--accent); margin-right: 12px; vertical-align: middle; border-radius: 2px; }}

        /* Detailed Fund Section */
        .fund-category {{ margin-bottom: 30px; }}
        .fund-category-title {{ font-size: 14px; font-weight: 700; color: var(--accent); margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1px; }}
        .fund-category-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
        .fund-item {{ background: #fdfdfd; border: 1px solid #f1f5f9; padding: 12px 15px; display: flex; justify-content: space-between; align-items: center; border-radius: 4px; }}
        .fund-item-label {{ font-size: 13px; color: #475569; font-weight: 500; }}
        .fund-item-label span {{ display: block; font-size: 10px; color: #94a3b8; font-weight: 400; }}
        .fund-item-value {{ font-size: 14px; font-weight: 700; color: var(--primary); }}

        /* Executive Summary Box */
        .summary-box {{ background: #f0f7ff; border-radius: 8px; padding: 30px; margin-bottom: 50px; border: 1px solid #dbeafe; text-align: left; }}
        .summary-box h2 {{ margin: 0 0 15px 0; font-size: 20px; color: var(--accent); font-weight: 800; }}
        .summary-content {{ font-size: 16px; color: #1e293b; line-height: 1.8; }}
        
        /* Analysis & Others... */
        .thesis-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 25px; text-align: left; }}
        .thesis-card {{ padding: 25px; border-radius: 8px; border: 1px solid var(--border); background: #fff; }}
        .thesis-card.bull {{ border-top: 5px solid var(--bull); background: #f0fdf4; }}
        .thesis-card.bear {{ border-top: 5px solid var(--bear); background: #fef2f2; }}
        .thesis-tag {{ font-size: 12px; font-weight: 700; text-transform: uppercase; margin-bottom: 15px; }}
        .bull .thesis-tag {{ color: var(--bull); }}
        .bear .thesis-tag {{ color: var(--bear); }}
        .thesis-list {{ padding-left: 18px; margin: 0; font-size: 14px; color: #475569; }}
        .thesis-list li {{ margin-bottom: 10px; }}

        .analysis-block {{ background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 30px; }}
        .analysis-text {{ font-size: 16px; color: #1e293b; line-height: 1.8; padding: 30px 30px 10px 30px; border-bottom: none; }}
        .analysis-highlights {{ padding: 0 30px 30px 30px; }}
        .analysis-highlights-title {{ font-size: 12px; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; display: flex; align-items: center; }}
        .analysis-highlights-title::before {{ content: '⚡'; margin-right: 8px; }}
        .analysis-list {{ padding: 0; margin: 0; list-style: none; display: grid; grid-template-columns: 1fr; gap: 8px; }}
        .analysis-list li {{ position: relative; padding-left: 20px; font-size: 14px; color: #475569; line-height: 1.6; }}
        .analysis-list li::before {{ content: '•'; position: absolute; left: 0; color: var(--accent); font-weight: bold; font-size: 18px; line-height: 1; }}

        .trading-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 20px; text-align: left; }}
        .trade-card {{ background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 20px; text-align: center; }}
        .trade-level {{ font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }}
        .trade-price {{ font-size: 24px; font-weight: 800; color: var(--accent); margin-bottom: 8px; }}
        .trade-weight {{ font-size: 13px; font-weight: 600; color: #1e293b; background: #e0f2fe; display: inline-block; padding: 2px 10px; border-radius: 4px; margin-bottom: 12px; }}
        .trade-logic {{ font-size: 13px; color: #64748b; line-height: 1.5; }}

        .risk-section {{ margin-top: 40px; background: #fff1f2; border: 1px solid #fecaca; border-radius: 8px; padding: 30px; text-align: left; }}
        .risk-header {{ font-weight: 800; color: #991b1b; display: flex; align-items: center; margin-bottom: 15px; font-size: 18px; }}
        .risk-header::before {{ content: '⚠️'; margin-right: 12px; }}
        .risk-content {{ font-size: 14px; color: #991b1b; }}
        .risk-content ul {{ padding-left: 20px; margin: 0; }}
        .risk-content li {{ margin-bottom: 8px; }}

        .data-table {{ width: 100%; border-collapse: collapse; font-size: 14px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; text-align: left; }}
        .data-table th {{ background: var(--light); padding: 15px; text-align: left; font-weight: 700; color: var(--primary); }}
        .data-table td {{ padding: 15px; border-top: 1px solid var(--border); }}

        .score-badge {{ background: #64748b; color: #fff; padding: 6px 15px; border-radius: 4px; font-size: 14px; font-weight: 700; margin-left: 20px; text-transform: none; }}
        
        .discussion-log {{ margin-top: 60px; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; text-align: left; }}
        .log-header {{ background: #475569; color: #fff; padding: 15px 25px; font-weight: 700; }}
        .log-msg {{ padding: 40px 30px; border-bottom: 1px solid var(--border); background: #fff; }}
        .log-role {{ margin-bottom: 20px; display: flex; align-items: center; }}
        .log-role span {{ background: var(--light); color: var(--accent); border: 1px solid var(--border); padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }}
        .log-body {{ font-size: 15px; color: #334155; line-height: 1.8; border-left: 4px solid var(--light); padding-left: 20px; }}
        .log-body h1, .log-body h2, .log-body h3 {{ color: var(--primary); margin-top: 25px; margin-bottom: 15px; }}
        .log-body table {{ width: 100%; border-collapse: collapse; margin: 20px 0; border: 1px solid var(--border); }}
        .log-body th {{ background: var(--light); padding: 12px; border: 1px solid var(--border); font-weight: 700; }}
        .log-body td {{ padding: 10px 12px; border: 1px solid var(--border); }}

        .report-footer {{ margin-top: 60px; padding-top: 20px; border-top: 1px solid var(--border); color: #94a3b8; font-size: 12px; text-align: center; }}

        @media print {{
            body {{ background: #fff; }}
            .report-page {{ box-shadow: none; margin: 0; padding: 40px; border: none; max-width: 100%; }}
        }}
    </style>
</head>
<body>
    <div class="report-page">
        <header class="report-header">
            <div class="ticker-info">
                <div class="brand-logo">ALSA Multi-Agent Intelligence</div>
                <h1>{info["name"]}</h1>
                <div class="ticker-sub">{info["symbol"]} | {info["market"]} | 研究报告号: {datetime.now().strftime("%Y%m%d%H%M")}</div>
            </div>
            <div class="price-box">
                <div class="current-price">{info["price"]} <span style="font-size:16px; font-weight:400; color:#94a3b8;">{info["currency"]}</span></div>
                <div class="price-pct">{chg_sign}{info["changePercent"]}%</div>
                <div style="font-size:11px; color:#94a3b8; margin-top:5px;">数据更新: {info["lastUpdated"]}</div>
            </div>
        </header>

        <div class="summary-box">
            <h2>核心投研摘要 (Executive Summary)</h2>
            <div class="summary-content">{md(d["summary"])}</div>
        </div>

        <section class="section">
            <h2 class="section-title">深度基本面指标 (Deep Fundamental Data)</h2>
            {detailed_fund_html}
        </section>

        <section class="section">
            <h2 class="section-title">核心博弈变量 (Core Variables)</h2>
            <div class="thesis-grid">
                <div class="thesis-card bull">
                    <div class="thesis-tag">看涨逻辑驱动 (Bull Thesis)</div>
                    <ul class="thesis-list">{"".join([f"<li>{p}</li>" for p in d["key_opps"]])}</ul>
                </div>
                <div class="thesis-card bear">
                    <div class="thesis-tag">风险与压制因素 (Bear Thesis)</div>
                    <ul class="thesis-list">{"".join([f"<li>{p}</li>" for p in d["key_risks"]])}</ul>
                </div>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">基本面护城河深度解析 (Fundamental & Moat)</h2>
            <div class="analysis-block">
                <div class="analysis-text">{md(d["moat_summary"])}</div>
                <div class="analysis-highlights">
                    <div class="analysis-highlights-title">关键护城河要素 (Key Moat Factors)</div>
                    <ul class="analysis-list">
                        {moat_list}
                    </ul>
                </div>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">宏观与资金技术面剖析 (Technical & Macro)</h2>
            <div class="analysis-block">
                <div class="analysis-text">{md(d["macro_summary"])}</div>
                <div class="analysis-highlights">
                    <div class="analysis-highlights-title">核心宏观与技术指标 (Key Indicators)</div>
                    <ul class="analysis-list">
                        {macro_list}
                    </ul>
                </div>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">
                交易操作计划 (Trading Plan)
                <span class="score-badge">共识得分: {d["score"]} | {d["recommendation"]}</span>
            </h2>
            <div style="font-size:15px; margin-bottom:25px; color:#475569; text-align:left;">{md(d["trading_plan"])}</div>
            <div class="trading-grid">
                {trading_steps_html}
            </div>
        </section>

        <section class="section" id="risk-warning">
            <div class="risk-section">
                <div class="risk-header">策略核心失效风险预警 (Invalidation Risks)</div>
                <div class="risk-content">
                    <ul>
                        {risk_points_html}
                    </ul>
                </div>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">情景分析与目标价预测</h2>
            <table class="data-table">
                <thead><tr><th>演练情景</th><th>概率</th><th>目标价</th><th>核心驱动逻辑</th></tr></thead>
                <tbody>{sc_rows}</tbody>
            </table>
        </section>

        <div class="discussion-log">
            <div class="log-header">专家研讨深度记录 (Expert Deliberation Log)</div>
            {log_html}
        </div>

        <footer class="report-footer">
            <p><strong>免责声明：</strong>本报告由 ALSA 多代理矩阵自主生成，仅供参考，不构成投资建议。</p>
            <p>© 2026 ALSA 智能分析系统</p>
        </footer>
    </div>
</body>
</html>"""




    def _compile_fundamentals(self, snapshot: dict, currency: str, ui_data: dict = {}) -> dict:
        m = {}
        if not isinstance(snapshot, dict): return m
        v, f, q = snapshot.get("valuation", {}), snapshot.get("financials", {}), snapshot.get("quote", {})
        
        def ratio(val): return f"{round(val, 2)}" if val is not None and isinstance(val, (int, float)) else "N/A"
        def pct(val): 
            if val is None or not isinstance(val, (int, float)): return "N/A"
            if abs(val) <= 2.0: return f"{round(val * 100, 2)}%"
            return f"{round(val, 2)}%"
        def money(val):
            if val is None or not isinstance(val, (int, float)): return "N/A"
            if abs(val) >= 1e12: return f"{round(val/1e12, 2)}万亿 {currency}"
            if abs(val) >= 1e8: return f"{round(val/1e8, 2)}亿 {currency}"
            if abs(val) >= 1e6: return f"{round(val/1e6, 2)}百万 {currency}"
            return f"{round(val, 2)} {currency}"

        # Combine sources (f, q, v)
        def get_val(key, sources=[f, q, v]):
            for s in sources:
                if key in s and s[key] is not None: return s[key]
            return None

        # 1. Valuation
        m["总市值"] = money(get_val("marketCap"))
        m["企业价值 (EV)"] = money(get_val("enterpriseValue"))
        m["市盈率 (PE)"] = ratio(get_val("trailingPE") or get_val("pe") or get_val("forwardPE"))
        m["市净率 (PB)"] = ratio(get_val("priceToBook") or get_val("pb"))
        m["PEG"] = ratio(get_val("pegRatio"))
        m["市销率 (PS)"] = ratio(get_val("priceToSales"))
        m["EV/EBITDA"] = ratio(get_val("enterpriseToEbitda"))

        # 2. Profitability
        m["净资产收益率 (ROE)"] = pct(get_val("returnOnEquity") or get_val("roe"))
        m["总资产收益率 (ROA)"] = pct(get_val("returnOnAssets") or get_val("roa"))
        m["毛利率"] = pct(get_val("grossMargins") or get_val("grossMargin"))
        m["营业利润率"] = pct(get_val("operatingMargins") or get_val("operatingMargin"))
        m["净利率"] = pct(get_val("profitMargins") or get_val("profitMargin"))
        m["每股收益 (EPS)"] = ratio(get_val("eps"))

        # 3. Growth
        m["营收同比增长 (YoY)"] = pct(get_val("revenueGrowth"))
        m["净利润同比增长 (YoY)"] = pct(get_val("earningsGrowth") or get_val("netProfitGrowth"))
        m["营收3年复合增长 (CAGR)"] = pct(get_val("revenueCagr3y"))
        m["净利润3年复合增长 (CAGR)"] = pct(get_val("incomeCagr3y"))

        # 4. Financial Health
        m["资产负债率"] = pct(get_val("debtRatio") or (get_val("debtToEquity")/100 if get_val("debtToEquity") else None))
        m["流动比率"] = ratio(get_val("currentRatio"))
        m["速动比率"] = ratio(get_val("quickRatio"))

        # 5. Cash Flow & Dividends
        m["经营现金流"] = money(get_val("operatingCashflow"))
        m["自由现金流 (FCF)"] = money(get_val("freeCashflow"))
        m["资本开支 (CAPEX)"] = money(get_val("capitalExpenditure")) or ui_data.get("capex") or "N/A"
        m["分红率"] = pct(get_val("payoutRatio"))
        
        div = get_val("dividendYield") or get_val("dividend")
        if div is not None and isinstance(div, (int, float)):
            if div > 0.5 and div < 100: m["股息率"] = f"{round(div, 2)}%"
            else: m["股息率"] = f"{round(div*100, 2)}%"
        else: m["股息率"] = "N/A"

        # 6. Efficiency
        m["总资产周转率"] = ratio(get_val("assetTurnover")) if get_val("assetTurnover") else (ui_data.get("asset_turnover") or "N/A")
        m["存货周转率"] = ratio(get_val("inventoryTurnover")) if get_val("inventoryTurnover") else (ui_data.get("inventory_turnover") or "N/A")

        # 7. Ownership
        m["大股东持股"] = pct(get_val("heldPercentInsiders"))
        m["机构持仓"] = pct(get_val("heldPercentInstitutions"))

        # 8. Market Context
        high = get_val("fiftyTwoWeekHigh")
        low = get_val("fiftyTwoWeekLow")
        curr = get_val("price") or get_val("currentPrice")
        if high and low and curr and high > low:
            percentile = (curr - low) / (high - low)
            m["股价百分位 (52周)"] = pct(percentile)
        else:
            m["股价百分位 (52周)"] = "N/A"

        m["PE百分位"] = ui_data.get("pe_percentile") or "N/A"

        return m

    def _default_scenarios(self):
        return [{"case": "Bull", "probability": 30, "targetPrice": "N/A", "logic": "Market outperformance"}, {"case": "Base", "probability": 50, "targetPrice": "N/A", "logic": "Steady growth"}, {"case": "Bear", "probability": 20, "targetPrice": "N/A", "logic": "Increased competition"}]
