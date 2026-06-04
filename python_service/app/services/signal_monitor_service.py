"""
Signal Monitor Service — Background loop that checks active alerts against real-time prices
and sends Feishu notifications when signals are triggered.
"""
import os
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from ..db.models import SearchAlert
from ..db.repositories.alert_repo import AlertRepository


class SignalMonitorService:
    """Monitors active alerts and triggers notifications."""

    def __init__(self, alert_repo: AlertRepository):
        self.alert_repo = alert_repo
        self._running = False

    async def check_all_alerts(self):
        """Check all monitored alerts against current prices."""
        alerts = self.alert_repo.list_monitored()
        if not alerts:
            return

        # Group by market for batch fetching
        a_share_alerts = [a for a in alerts if a.market == "A-Share"]
        hk_alerts = [a for a in alerts if a.market == "HK-Share"]
        us_alerts = [a for a in alerts if a.market == "US-Share"]

        if a_share_alerts:
            await self._check_a_share_batch(a_share_alerts)
        if hk_alerts:
            await self._check_hk_batch(hk_alerts)
        if us_alerts:
            await self._check_us_batch(us_alerts)

    async def _check_a_share_batch(self, alerts: List[SearchAlert]):
        """Check A-Share alerts using akshare spot data."""
        try:
            import akshare as ak
            from ..utils.network import safe_ak_call
            df = await safe_ak_call(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return

            for alert in alerts:
                code = alert.symbol.replace(".SH", "").replace(".SZ", "")[:6]
                row = df[df["代码"] == code]
                if row.empty:
                    continue
                price = float(row.iloc[0].get("最新价", 0) or 0)
                if price <= 0:
                    continue
                await self._evaluate_alert(alert, price)
        except Exception as e:
            print(f"[SignalMonitor] A-Share batch check error: {e}")

    async def _check_hk_batch(self, alerts: List[SearchAlert]):
        """Check HK-Share alerts using yfinance."""
        try:
            import yfinance as yf
            for alert in alerts:
                symbol = alert.symbol
                if not symbol.endswith(".HK"):
                    # Normalize: 0700 -> 0700.HK
                    clean = symbol.replace(".HK", "").lstrip("0") or "0"
                    symbol = f"{clean.zfill(4)}.HK"
                ticker = yf.Ticker(symbol)
                price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice")
                if price and price > 0:
                    await self._evaluate_alert(alert, float(price))
        except Exception as e:
            print(f"[SignalMonitor] HK batch check error: {e}")

    async def _check_us_batch(self, alerts: List[SearchAlert]):
        """Check US-Share alerts using yfinance."""
        try:
            import yfinance as yf
            for alert in alerts:
                ticker = yf.Ticker(alert.symbol)
                price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice")
                if price and price > 0:
                    await self._evaluate_alert(alert, float(price))
        except Exception as e:
            print(f"[SignalMonitor] US batch check error: {e}")

    async def _evaluate_alert(self, alert: SearchAlert, current_price: float):
        """Evaluate whether the current price triggers any signal for this alert."""
        triggered_signals = []

        # Check stop loss (highest priority)
        if current_price <= alert.stop_loss:
            triggered_signals.append({
                "type": "stop_loss",
                "emoji": "🚨",
                "title": "止损触发",
                "detail": f"当前价 {current_price:.2f} 已跌破止损位 {alert.stop_loss:.2f}",
                "action": "建议立即执行止损清仓",
                "urgency": "CRITICAL"
            })

        # Check target reached
        if current_price >= alert.target_price:
            triggered_signals.append({
                "type": "target",
                "emoji": "🎯",
                "title": "目标价达成",
                "detail": f"当前价 {current_price:.2f} 已达目标价 {alert.target_price:.2f}",
                "action": "建议分批止盈退出",
                "urgency": "HIGH"
            })

        # Check entry zone (price enters the buy zone)
        if alert.entry_price * 0.99 <= current_price <= alert.entry_price * 1.01:
            triggered_signals.append({
                "type": "entry",
                "emoji": "📍",
                "title": "入场信号",
                "detail": f"当前价 {current_price:.2f} 进入买点区间 (锚定 {alert.entry_price:.2f})",
                "action": "可考虑按计划分批建仓",
                "urgency": "MEDIUM"
            })

        # Check step-in plan triggers (分步建仓)
        if alert.step_in_plan:
            try:
                plan = json.loads(alert.step_in_plan)
                for level in plan:
                    trigger_price = level.get("trigger_price", 0)
                    if trigger_price > 0 and abs(current_price - trigger_price) / trigger_price < 0.005:
                        triggered_signals.append({
                            "type": "step_in",
                            "emoji": "📊",
                            "title": f"建仓层级触发: {level.get('name', '')}",
                            "detail": f"当前价 {current_price:.2f} 触及 {trigger_price:.2f} ({level.get('position', '')}仓位)",
                            "action": level.get("logic", "按计划执行"),
                            "urgency": "MEDIUM"
                        })
            except (json.JSONDecodeError, TypeError):
                pass

        # Update last checked state
        self.alert_repo.update_check_state(alert.alert_id, current_price)

        # Send notifications for triggered signals
        if triggered_signals:
            await self._send_notifications(alert, current_price, triggered_signals)

            # Mark as triggered if stop_loss or target hit
            critical_types = {"stop_loss", "target"}
            if any(s["type"] in critical_types for s in triggered_signals):
                trigger_type = next(s["type"] for s in triggered_signals if s["type"] in critical_types)
                self.alert_repo.mark_triggered(alert.alert_id, trigger_type, current_price)

    async def _send_notifications(self, alert: SearchAlert, price: float, signals: List[Dict]):
        """Send Feishu notification for triggered signals."""
        webhook_url = alert.feishu_webhook_url or os.getenv("FEISHU_WEBHOOK_URL")
        if not webhook_url:
            print(f"[SignalMonitor] No webhook URL for alert {alert.alert_id} ({alert.symbol})")
            return

        # Build Feishu interactive card
        signal_elements = []
        for sig in signals:
            signal_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{sig['emoji']} {sig['title']}**\n"
                        f"{sig['detail']}\n"
                        f"💡 {sig['action']}"
                    )
                }
            })
            signal_elements.append({"tag": "hr"})

        # Price context
        change_from_entry = ((price - alert.entry_price) / alert.entry_price * 100)
        risk_reward_info = (
            f"**入场价**: {alert.entry_price:.2f} | **目标价**: {alert.target_price:.2f} | **止损价**: {alert.stop_loss:.2f}\n"
            f"**当前偏离入场价**: {change_from_entry:+.2f}%"
        )

        # Thesis info
        thesis_text = ""
        if alert.thesis:
            thesis_text = f"\n📋 **投资论点**: {alert.thesis}"
        if alert.invalidation_criteria:
            thesis_text += f"\n⚠️ **论点证伪条件**: {alert.invalidation_criteria}"

        urgency_map = {"CRITICAL": "red", "HIGH": "orange", "MEDIUM": "blue"}
        max_urgency = max(signals, key=lambda s: ["LOW", "MEDIUM", "HIGH", "CRITICAL"].index(s.get("urgency", "LOW")))
        template_color = urgency_map.get(max_urgency["urgency"], "blue")

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"⚡ 信号触发: {alert.name or alert.symbol}"},
                "template": template_color,
            },
            "elements": [
                *signal_elements,
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📈 **价格监控详情**\n{risk_reward_info}{thesis_text}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{
                        "tag": "plain_text",
                        "content": f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ALSA Signal Monitor | 仅供参考，不构成投资建议"
                    }]
                }
            ],
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json={
                    "msg_type": "interactive",
                    "card": card,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == 0:
                        self.alert_repo.increment_notify_count(alert.alert_id)
                        print(f"[SignalMonitor] ✓ Feishu notification sent for {alert.symbol}: {[s['type'] for s in signals]}")
                    else:
                        print(f"[SignalMonitor] Feishu API error: {data.get('msg')}")
                else:
                    print(f"[SignalMonitor] Feishu HTTP error: {resp.status_code}")
        except Exception as e:
            print(f"[SignalMonitor] Notification send failed: {e}")

    async def monitor_loop(self, interval_seconds: int = 60):
        """Main monitoring loop — runs continuously."""
        self._running = True
        print(f"[SignalMonitor] Started. Checking every {interval_seconds}s.")
        while self._running:
            try:
                await self.check_all_alerts()
            except Exception as e:
                print(f"[SignalMonitor] Loop error: {e}")
            await asyncio.sleep(interval_seconds)

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False
