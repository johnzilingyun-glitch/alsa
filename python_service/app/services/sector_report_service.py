"""
Sector Report Service — Generates HTML reports for sector/industry analysis.
"""
import os
import re
import markdown2
from typing import Dict, Any, List
from datetime import datetime


class SectorReportService:
    """Generates Bloomberg-style HTML reports for sector analysis."""

    async def generate_sector_report(self, result: Dict[str, Any], output_path: str, model: str = None) -> str:
        """Generate a sector analysis HTML report."""
        discussion = result.get("discussion", [])
        sector_name = result.get("symbol", "Unknown Sector")
        realtime_prices = result.get("realtime_prices", {})

        # Convert each expert round's content to HTML
        expert_sections = []
        for msg in discussion:
            role = msg.get("role", "Expert")
            content = msg.get("content", "")
            if not content or len(content.strip()) < 10:
                continue
            formatted_content = self._format_expert_content(content)
            html_content = self._markdown_to_html(formatted_content)
            expert_sections.append({"role": role, "html": html_content})

        # Extract structured data from Chief Strategist (last expert)
        recommendation_table = self._extract_recommendation_table(discussion)
        scenarios_html = self._extract_scenarios(discussion)

        # Build real-time price verification section
        price_verification_html = self._build_price_verification_html(realtime_prices) if realtime_prices else ""

        html = self._render_sector_html(sector_name, expert_sections, recommendation_table, scenarios_html, price_verification_html)

        abs_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_path) if os.path.dirname(abs_path) else ".", exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(html)

        return abs_path

    def _format_expert_content(self, content: str) -> str:
        """Format raw content into markdown. If it's a JSON string, convert it to a readable markdown structure."""
        import json
        import re
        
        # Strip fenced code block markers (```json ... ```)
        stripped = re.sub(r'^```(?:json)?\s*\n?', '', content.strip(), flags=re.MULTILINE)
        stripped = re.sub(r'\n?```\s*$', '', stripped.strip(), flags=re.MULTILINE)
        
        json_match = re.search(r'\{.*\}', stripped, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                md_lines = []
                
                KEY_LABELS = {
                    "core_thesis": "核心论点 (Core Thesis)",
                    "key_metrics_extracted": "关键指标 (Key Metrics)",
                    "key_metrics": "关键指标 (Key Metrics)",
                    "risks": "风险提示 (Risks)",
                    "rating": "评级 (Rating)",
                    "catalysts": "催化剂 (Catalysts)",
                    "recommendations": "推荐 (Recommendations)",
                    "conclusion": "结论 (Conclusion)",
                    "summary": "摘要 (Summary)",
                    "valuation": "估值 (Valuation)",
                    "industry_outlook": "行业展望 (Industry Outlook)",
                    "supply_demand": "供需分析 (Supply & Demand)",
                    "competitive_landscape": "竞争格局 (Competitive Landscape)",
                }
                
                for k, v in data.items():
                    label = KEY_LABELS.get(k, k.replace("_", " ").title())
                    
                    if k == "rating":
                        md_lines.append(f"### {label}: **{v}**\n")
                        continue
                    
                    md_lines.append(f"### {label}")
                    md_lines.append("")
                    self._format_value(v, md_lines, indent=0)
                    md_lines.append("")
                
                return "\n".join(md_lines)
            except (json.JSONDecodeError, ValueError):
                pass
        return content

    def _format_value(self, v, md_lines: list, indent: int = 0):
        """Recursively format a JSON value into markdown lines."""
        prefix = "  " * indent
        if isinstance(v, str):
            md_lines.append(f"{prefix}{v}")
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    parts = []
                    for sub_k, sub_v in item.items():
                        parts.append(f"**{sub_k}**: {sub_v}")
                    md_lines.append(f"{prefix}- {' | '.join(parts)}")
                elif isinstance(item, list):
                    md_lines.append(f"{prefix}- {', '.join(str(x) for x in item)}")
                else:
                    md_lines.append(f"{prefix}- {item}")
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if isinstance(sub_v, (str, int, float)):
                    md_lines.append(f"{prefix}- **{sub_k}**: {sub_v}")
                elif isinstance(sub_v, list):
                    md_lines.append(f"{prefix}- **{sub_k}**:")
                    for item in sub_v:
                        md_lines.append(f"{prefix}  - {item}")
                elif isinstance(sub_v, dict):
                    md_lines.append(f"{prefix}- **{sub_k}**:")
                    self._format_value(sub_v, md_lines, indent + 1)
                else:
                    md_lines.append(f"{prefix}- **{sub_k}**: {sub_v}")
        else:
            md_lines.append(f"{prefix}{v}")

    def _markdown_to_html(self, content: str) -> str:
        """Convert markdown to HTML."""
        stripped = content.strip()
        if not stripped:
            return "<p><em>(无内容)</em></p>"
        # Strip DSML tokens
        stripped = re.sub(r'<[｜|]*DSML[｜|]*[^>]*>', '', stripped)
        stripped = re.sub(r'</[｜|]*DSML[｜|]*[^>]*>', '', stripped)
        stripped = re.sub(r'\n{3,}', '\n\n', stripped).strip()
        if not stripped:
            return "<p><em>(无内容)</em></p>"
        try:
            return markdown2.markdown(stripped, extras=["fenced-code-blocks", "tables", "header-ids"])
        except Exception:
            return f"<pre>{stripped}</pre>"

    def _extract_recommendation_table(self, discussion: List[Dict]) -> str:
        """Extract the final recommendation table from Chief Strategist."""
        for msg in reversed(discussion):
            if "Chief" in msg.get("role", "") or "Strategist" in msg.get("role", ""):
                content = msg.get("content", "")
                # Look for the recommendation table
                lines = content.split("\n")
                in_table = False
                table_lines = []
                for line in lines:
                    if "排序" in line and "|" in line and ("股票" in line or "名称" in line):
                        in_table = True
                    if in_table:
                        if line.strip().startswith("|"):
                            table_lines.append(line)
                        elif table_lines and not line.strip().startswith("|"):
                            break
                if table_lines:
                    return self._markdown_to_html("\n".join(table_lines))
        return ""

    def _extract_scenarios(self, discussion: List[Dict]) -> str:
        """Extract scenario analysis table."""
        for msg in reversed(discussion):
            if "Chief" in msg.get("role", "") or "Strategist" in msg.get("role", ""):
                content = msg.get("content", "")
                lines = content.split("\n")
                in_table = False
                table_lines = []
                for line in lines:
                    # Match scenario table header: 情景/场景/Scenario + probability/牛市
                    if not in_table and "|" in line:
                        if ("情景" in line or "场景" in line or "Scenario" in line) and ("概率" in line or "牛市" in line or "Probability" in line):
                            in_table = True
                    if in_table:
                        if line.strip().startswith("|"):
                            table_lines.append(line)
                        elif table_lines and not line.strip().startswith("|"):
                            break
                if table_lines:
                    return self._markdown_to_html("\n".join(table_lines))
        return ""

    ROLE_NAMES = {
        "Sector Macro Strategist": ("板块宏观战略分析", "macro"),
        "Sector Stock Screener": ("板块个股筛选", "screener"),
        "Serenity Alpha Analyst": ("Serenity Alpha 量化分析", "screener"),
        "Sector Risk Auditor": ("板块风险审计", "risk"),
        "Sector Chief Strategist": ("板块首席策略", "chief"),
    }

    def _build_price_verification_html(self, realtime_prices: Dict[str, Any]) -> str:
        """Build a real-time price verification table from enrichment data."""
        if not realtime_prices:
            return ""
        rows = ""
        for code, data in sorted(realtime_prices.items(), key=lambda x: x[1].get("market_cap_yi", 0) or 0, reverse=True):
            name = data.get("name", "")
            price = data.get("price")
            change_pct = data.get("change_pct")
            prev_close = data.get("prev_close")
            pe = data.get("pe")
            pb = data.get("pb")
            market_cap = data.get("market_cap_yi")
            exchange = data.get("exchange", "")
            volume = data.get("volume_yi")
            high = data.get("high")
            low = data.get("low")

            change_class = "bull" if (change_pct and change_pct > 0) else "bear" if (change_pct and change_pct < 0) else ""
            change_str = f'<span class="{change_class}">{change_pct:+.2f}%</span>' if change_pct is not None else "N/A"

            rows += f"""<tr>
                <td><strong>{code}</strong></td>
                <td>{name}</td>
                <td>{exchange}</td>
                <td><strong>{f'{price:.2f}' if price else 'N/A'}</strong></td>
                <td>{change_str}</td>
                <td>{f'{prev_close:.2f}' if prev_close else 'N/A'}</td>
                <td>{f'{high:.2f}' if high else 'N/A'}</td>
                <td>{f'{low:.2f}' if low else 'N/A'}</td>
                <td>{f'{pe:.1f}' if pe else 'N/A'}</td>
                <td>{f'{pb:.2f}' if pb else 'N/A'}</td>
                <td>{f'{market_cap:.0f}' if market_cap else 'N/A'}</td>
                <td>{f'{volume:.2f}' if volume else 'N/A'}</td>
            </tr>"""

        timestamp = ""
        for data in realtime_prices.values():
            ts = data.get("timestamp")
            if ts:
                timestamp = ts
                break

        return f"""
        <section class="section price-verification-section">
            <h2 class="section-title">实时价格校验 (Real-Time Price Verification)</h2>
            <p class="price-notice">⚠ 以下价格来自交易所实时数据 (AkShare API)，数据时间: {timestamp}。如与上述分析中的价格存在差异，请以此表为准。</p>
            <table class="price-table">
                <thead>
                    <tr>
                        <th>代码</th><th>名称</th><th>交易所</th><th>最新价</th><th>涨跌幅</th>
                        <th>昨收</th><th>最高</th><th>最低</th><th>PE(动)</th><th>PB</th>
                        <th>总市值(亿)</th><th>成交额(亿)</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </section>
"""

    def _render_sector_html(self, sector_name: str, expert_sections: list, recommendation_table: str, scenarios_html: str, price_verification_html: str = "") -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Build expert round sections
        rounds_html = ""
        for i, section in enumerate(expert_sections):
            role = section["role"]
            display_name, css_class = self.ROLE_NAMES.get(role, (role, "default"))
            rounds_html += f"""
        <section class="section expert-round round-{css_class}">
            <h2 class="section-title">
                <span class="round-badge">Round {i+1}</span>
                {display_name} ({role})
            </h2>
            <div class="expert-content">
                {section["html"]}
            </div>
        </section>
"""

        # Recommendation highlight section
        rec_section = ""
        if recommendation_table:
            rec_section = f"""
        <section class="section highlight-section">
            <h2 class="section-title">最终推荐组合 (Final Portfolio)</h2>
            <div class="recommendation-table">
                {recommendation_table}
            </div>
        </section>
"""

        # Scenarios section
        scenario_section = ""
        if scenarios_html:
            scenario_section = f"""
        <section class="section">
            <h2 class="section-title">情景分析 (Scenario Analysis)</h2>
            <div class="scenario-table">
                {scenarios_html}
            </div>
        </section>
"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{sector_name}板块 - 深度研究报告</title>
    <style>
        :root {{
            --primary: #1e293b; --accent: #3b82f6; --text: #334155;
            --light: #f8fafc; --border: #e2e8f0; --bull: #10b981; --bear: #ef4444;
        }}
        body {{ font-family: 'Inter', -apple-system, system-ui, sans-serif; color: var(--text); line-height: 1.6; margin: 0; background: #f1f5f9; }}
        .report-page {{ max-width: 1100px; margin: 40px auto; background: #fff; padding: 60px 80px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border-radius: 4px; border: 1px solid var(--border); }}

        /* Header */
        .report-header {{ border-bottom: 2px solid var(--primary); padding-bottom: 25px; margin-bottom: 40px; }}
        .brand-logo {{ font-size: 12px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 10px; }}
        .header-main {{ display: flex; justify-content: space-between; align-items: center; }}
        .ticker-info h1 {{ margin: 0; font-size: 32px; font-weight: 800; color: var(--primary); }}
        .ticker-sub {{ color: #64748b; font-size: 14px; font-weight: 500; margin-top: 5px; }}
        .report-meta {{ text-align: right; color: #64748b; font-size: 13px; }}
        .report-type {{ display: inline-block; background: var(--accent); color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 700; letter-spacing: 1px; }}

        /* Sections */
        .section {{ margin-bottom: 50px; text-align: left; }}
        .section-title {{ font-size: 20px; font-weight: 800; color: var(--primary); border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 25px; display: flex; align-items: center; gap: 10px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .section-title::before {{ content: ''; display: inline-block; width: 4px; height: 20px; background: var(--accent); border-radius: 2px; }}

        /* Round badges */
        .round-badge {{ display: inline-block; background: var(--accent); color: white; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }}
        .round-macro .section-title::before {{ background: #8b5cf6; }}
        .round-screener .section-title::before {{ background: #10b981; }}
        .round-risk .section-title::before {{ background: #ef4444; }}
        .round-chief .section-title::before {{ background: #f59e0b; }}

        /* Expert content */
        .expert-content {{ font-size: 14px; line-height: 1.8; }}
        .expert-content h1, .expert-content h2 {{ font-size: 18px; font-weight: 700; color: var(--primary); margin: 25px 0 15px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; }}
        .expert-content h3 {{ font-size: 15px; font-weight: 600; color: #475569; margin: 20px 0 10px; }}
        .expert-content table {{ width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 13px; }}
        .expert-content th {{ background: #f8fafc; font-weight: 700; text-align: left; padding: 10px 12px; border: 1px solid var(--border); color: var(--primary); white-space: nowrap; }}
        .expert-content td {{ padding: 8px 12px; border: 1px solid var(--border); vertical-align: top; }}
        .expert-content tr:hover {{ background: #fafbfd; }}
        .expert-content ul, .expert-content ol {{ padding-left: 24px; }}
        .expert-content li {{ margin-bottom: 6px; }}
        .expert-content strong {{ color: var(--primary); }}
        .expert-content blockquote {{ border-left: 3px solid var(--accent); padding-left: 15px; margin: 15px 0; color: #64748b; font-style: italic; }}

        /* Highlight section */
        .highlight-section {{ background: #f0f7ff; border-radius: 8px; padding: 30px; border: 1px solid #dbeafe; }}
        .highlight-section .section-title {{ border-bottom-color: #bfdbfe; }}
        .recommendation-table table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 4px; font-size: 13px; }}
        .recommendation-table th {{ background: var(--accent); color: white; padding: 10px 12px; border: 1px solid var(--accent); white-space: nowrap; text-align: left; }}
        .recommendation-table td {{ padding: 8px 12px; border: 1px solid var(--border); vertical-align: top; }}

        /* Scenario table */
        .scenario-table table {{ width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 13px; background: #fdfdfd; }}
        .scenario-table th {{ background: #f8fafc; font-weight: 700; text-align: left; padding: 10px 12px; border: 1px solid var(--border); color: var(--primary); white-space: nowrap; }}
        .scenario-table td {{ padding: 8px 12px; border: 1px solid var(--border); vertical-align: top; }}
        .scenario-table tr:hover {{ background: #fafbfd; }}

        /* Price verification section */
        .price-verification-section {{ background: #fef3c7; border: 2px solid #f59e0b; border-radius: 8px; padding: 30px; }}
        .price-verification-section .section-title::before {{ background: #f59e0b; }}
        .price-notice {{ color: #92400e; font-weight: 600; font-size: 13px; margin-bottom: 15px; padding: 8px 12px; background: #fffbeb; border-radius: 4px; border-left: 3px solid #f59e0b; }}
        .price-table {{ width: 100%; border-collapse: collapse; font-size: 12px; background: white; border-radius: 4px; overflow: hidden; }}
        .price-table th {{ background: #1e293b; color: white; padding: 8px 10px; text-align: right; white-space: nowrap; font-weight: 600; }}
        .price-table th:first-child, .price-table th:nth-child(2), .price-table th:nth-child(3) {{ text-align: left; }}
        .price-table td {{ padding: 6px 10px; border-bottom: 1px solid #f1f5f9; text-align: right; }}
        .price-table td:first-child, .price-table td:nth-child(2), .price-table td:nth-child(3) {{ text-align: left; }}
        .price-table tr:hover {{ background: #f8fafc; }}
        .price-table .bull {{ color: #10b981; font-weight: 600; }}
        .price-table .bear {{ color: #ef4444; font-weight: 600; }}

        /* Footer */
        .report-footer {{ border-top: 1px solid var(--border); padding-top: 20px; margin-top: 40px; font-size: 11px; color: #94a3b8; text-align: center; }}

        @media print {{
            body {{ background: white; }}
            .report-page {{ box-shadow: none; border: none; margin: 0; padding: 40px; max-width: 100%; }}
        }}
        @media (max-width: 768px) {{
            .report-page {{ padding: 20px; margin: 10px; }}
            .header-main {{ flex-direction: column; align-items: flex-start; gap: 15px; }}
            .report-meta {{ text-align: left; }}
            .expert-content table {{ font-size: 11px; }}
            .expert-content th, .expert-content td {{ padding: 6px 8px; }}
        }}
    </style>
</head>
<body>
    <div class="report-page">
        <header class="report-header">
            <div class="brand-logo">ALSA Multi-Agent Intelligence</div>
            <div class="header-main">
                <div class="ticker-info">
                    <h1>{sector_name}板块</h1>
                    <div class="ticker-sub">板块深度研究报告 | {now}</div>
                </div>
                <div class="report-meta">
                    <div class="report-type">SECTOR ANALYSIS</div>
                    <div style="margin-top: 8px;">4轮多专家论证</div>
                    <div>3个月~2年行情推测</div>
                </div>
            </div>
        </header>

{rec_section}

{price_verification_html}

{scenario_section}

{rounds_html}

        <footer class="report-footer">
            <p>ALSA Sector Analysis Report | Generated {now} | 本报告由多轮AI专家讨论自动生成，仅供参考，不构成投资建议。</p>
        </footer>
    </div>
</body>
</html>"""
