"""
Export Service — PDF generation and share card rendering via Playwright.
"""
from typing import Optional


class ExportService:
    """Converts HTML reports to PDF and generates share card images."""

    async def html_to_pdf(self, html_content: str, landscape: bool = False) -> bytes:
        """Convert HTML string to PDF bytes using Playwright Chromium."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html_content, wait_until="networkidle")
            pdf_bytes = await page.pdf(
                format="A4",
                landscape=landscape,
                print_background=True,
                margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
            )
            await browser.close()
        return pdf_bytes

    async def html_to_image(self, html_content: str, width: int = 800, device_scale_factor: float = 2.0) -> bytes:
        """Render HTML to a PNG screenshot using Playwright."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": width, "height": 600},
                device_scale_factor=device_scale_factor,
            )
            await page.set_content(html_content, wait_until="networkidle")
            # Let content determine height
            height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": width, "height": min(height + 40, 4096)})
            png_bytes = await page.screenshot(full_page=True, type="png")
            await browser.close()
        return png_bytes

    def build_share_card_html(
        self,
        title: str,
        verdict: str = "",
        score: Optional[float] = None,
        price: Optional[str] = None,
        change_pct: Optional[str] = None,
        highlights: Optional[list] = None,
        report_type: str = "stock",
    ) -> str:
        """Build a compact, visually appealing share card HTML template."""
        # Color scheme
        if verdict.lower() in ("strong_buy", "buy", "bull", "bullish"):
            verdict_color = "#16a34a"
            verdict_bg = "#dcfce7"
            verdict_text = "看多"
        elif verdict.lower() in ("sell", "strong_sell", "bear", "bearish"):
            verdict_color = "#dc2626"
            verdict_bg = "#fee2e2"
            verdict_text = "看空"
        else:
            verdict_color = "#d97706"
            verdict_bg = "#fef3c7"
            verdict_text = verdict or "中性"

        # Score bar
        score_val = score or 0
        score_color = "#16a34a" if score_val >= 70 else "#d97706" if score_val >= 40 else "#dc2626"

        # Change percent color
        change_color = "#dc2626"
        if change_pct:
            try:
                if float(change_pct.replace("%", "").replace("+", "")) >= 0:
                    change_color = "#16a34a"
            except:
                pass

        # Highlights HTML
        highlights_html = ""
        if highlights:
            items = "".join(f'<li style="margin-bottom:4px;">{h}</li>' for h in highlights[:5])
            highlights_html = f'<ul style="margin:8px 0 0;padding-left:18px;color:#374151;font-size:13px;line-height:1.6;">{items}</ul>'

        type_label = "板块分析" if report_type == "sector" else "个股深度研报"
        
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f8fafc; padding: 16px; }}
  .card {{ background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 420px; }}
  .header {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); padding: 20px 24px 16px; color: #fff; }}
  .header .type {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; margin-bottom: 4px; }}
  .header .title {{ font-size: 22px; font-weight: 700; }}
  .price-row {{ display: flex; align-items: baseline; gap: 12px; margin-top: 10px; }}
  .price {{ font-size: 28px; font-weight: 700; }}
  .change {{ font-size: 15px; font-weight: 600; }}
  .body {{ padding: 16px 24px 20px; }}
  .verdict-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
  .verdict-badge {{ display: inline-block; padding: 4px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; }}
  .score-bar {{ flex: 1; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }}
  .score-fill {{ height: 100%; border-radius: 4px; }}
  .score-label {{ font-size: 12px; color: #6b7280; margin-top: 2px; }}
  .footer {{ padding: 12px 24px; border-top: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center; }}
  .footer .brand {{ font-size: 11px; color: #94a3b8; font-weight: 500; }}
  .footer .time {{ font-size: 11px; color: #94a3b8; }}
</style></head><body>
<div class="card">
  <div class="header">
    <div class="type">{type_label}</div>
    <div class="title">{title}</div>
    {"" if not price else f'<div class="price-row"><span class="price">{price}</span><span class="change" style="color:{change_color}">{change_pct or ""}</span></div>'}
  </div>
  <div class="body">
    <div class="verdict-row">
      <span class="verdict-badge" style="background:{verdict_bg};color:{verdict_color};">{verdict_text}</span>
      <div style="flex:1">
        <div class="score-bar"><div class="score-fill" style="width:{score_val}%;background:{score_color};"></div></div>
        <div class="score-label">综合评分 {score_val:.0f}/100</div>
      </div>
    </div>
    {highlights_html}
  </div>
  <div class="footer">
    <span class="brand">ALSA AI 研究平台</span>
    <span class="time">{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
  </div>
</div>
</body></html>"""


# Singleton
export_service = ExportService()
