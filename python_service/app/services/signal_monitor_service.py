"""
Signal Monitor Service — Background loop that checks active alerts against real-time prices
and sends Feishu notifications when signals are triggered.
"""
import os
import logging
logger = logging.getLogger(__name__)
import json
import asyncio
from datetime import datetime
from typing import List, Dict
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

        # Use DataRouter for all markets — automatic fallback across providers
        from .data_providers import data_router
        tasks = []
        for alert in alerts:
            if not alert.monitoring_enabled:
                continue
            tasks.append(self._check_alert_via_router(alert, data_router))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_alert_via_router(self, alert: SearchAlert, router):
        """Check a single alert using the DataRouter (multi-source with fallback)."""
        try:
            quote = await router.get_quote(alert.symbol)
            if quote is None or quote.price <= 0:
                return
            await self._evaluate_alert(alert, quote.price)
        except Exception as e:
            logger.warning(f"[SignalMonitor] Quote fetch failed for {alert.symbol}: {e}")

    async def _evaluate_alert(self, alert: SearchAlert, current_price: float):
        """Evaluate whether the current price triggers any signal for this alert."""
        triggered_signals = []

        is_short = alert.target_price < alert.entry_price if alert.target_price and alert.entry_price else False

        # Check stop loss (highest priority)
        if alert.stop_loss and alert.stop_loss > 0:
            stop_loss_hit = (current_price >= alert.stop_loss) if is_short else (current_price <= alert.stop_loss)
            if stop_loss_hit:
                triggered_signals.append({
                    "type": "stop_loss",
                    "emoji": "🚨",
                    "title": "止损触发",
                    "detail": f"当前价 {current_price:.2f} 已{'涨' if is_short else '跌'}破止损位 {alert.stop_loss:.2f}",
                    "action": "建议立即执行止损清仓",
                    "urgency": "CRITICAL"
                })

        # Check target reached
        if alert.target_price and alert.target_price > 0:
            target_hit = (current_price <= alert.target_price) if is_short else (current_price >= alert.target_price)
            if target_hit:
                triggered_signals.append({
                    "type": "target",
                    "emoji": "🎯",
                    "title": "目标价达成",
                    "detail": f"当前价 {current_price:.2f} 已达目标价 {alert.target_price:.2f}",
                    "action": "建议分批止盈退出",
                    "urgency": "HIGH"
                })

        # Check entry zone (price enters the buy zone)
        if alert.entry_price and alert.entry_price > 0:
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
        now = datetime.utcnow()
        today = now.date()

        # Reset daily count if last notification was on a different day
        if alert.last_notified_at and alert.last_notified_at.date() != today:
            self.alert_repo.reset_daily_notify_count(alert.alert_id)
            alert.notify_count = 0

        # Max 3 notifications per day per stock
        if (alert.notify_count or 0) >= 3:
            logger.info(f"[SignalMonitor] Skipping {alert.symbol} (daily limit 3 reached)")
            return

        # Minimum 30 minutes interval between notifications
        if alert.last_notified_at:
            elapsed = (now - alert.last_notified_at.replace(tzinfo=None)).total_seconds() / 60
            if elapsed < 30:
                logger.info(f"[SignalMonitor] Skipping {alert.symbol} (interval {elapsed:.0f}min < 30min)")
                return

        webhook_url = alert.feishu_webhook_url or os.getenv("FEISHU_WEBHOOK_URL")
        if not webhook_url:
            logger.info(f"[SignalMonitor] No webhook URL for alert {alert.alert_id} ({alert.symbol})")
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
        is_short = alert.target_price < alert.entry_price if alert.target_price and alert.entry_price else False
        if alert.entry_price and alert.entry_price > 0:
            change_from_entry = ((alert.entry_price - price) if is_short else (price - alert.entry_price)) / alert.entry_price * 100
        else:
            change_from_entry = 0.0

        risk_reward_info = (
            f"**入场价**: {alert.entry_price:.2f} | **目标价**: {alert.target_price:.2f} | **止损价**: {alert.stop_loss:.2f} {'(空头)' if is_short else '(多头)'}\n"
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
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "已阅确认 (停止今日及后续提醒)"
                            },
                            "type": "primary",
                            "value": {
                                "action": "acknowledge_alert",
                                "alert_id": alert.alert_id
                            }
                        }
                    ]
                },
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
            import json
            import hmac
            import hashlib

            payload_dict = {
                "msg_type": "interactive",
                "card": card,
            }
            payload_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json"}

            # Include API Token for Node Proxy authentication
            api_token = os.getenv("API_TOKEN")
            if api_token:
                headers["Authorization"] = f"Bearer {api_token}"

            # Hermes HMAC Forwarding Support
            webhook_secret = os.getenv("HERMES_WEBHOOK_SECRET")
            if not webhook_secret:
                logger.warning("WARNING: HERMES_WEBHOOK_SECRET not set, webhook signing disabled")
            if webhook_secret:
                sig = "sha256=" + hmac.new(
                    webhook_secret.encode(), payload_bytes, hashlib.sha256
                ).hexdigest()
                headers["X-Hub-Signature-256"] = sig

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, content=payload_bytes, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    code = data.get("code")
                    status_code = data.get("StatusCode")
                    msg = str(data.get("msg") or data.get("StatusMessage") or data.get("message") or "").lower()
                    
                    is_success = False
                    if str(code) == "0" or str(status_code) == "0" or data.get("status") in ("delivered", "success"):
                        is_success = True
                    elif "success" in msg:
                        is_success = True
                    elif code is None and status_code is None:
                        is_success = True
                        
                    if is_success:
                        self.alert_repo.increment_notify_count(alert.alert_id)
                        logger.info(f"[SignalMonitor] ✓ Feishu notification sent for {alert.symbol}: {[s['type'] for s in signals]}")
                    else:
                        logger.error(f"[SignalMonitor] Feishu/Hermes API error: {data}")
                else:
                    logger.error(f"[SignalMonitor] Feishu/Hermes HTTP error: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.info(f"[SignalMonitor] Notification send failed: {e}")

    async def monitor_loop(self, interval_seconds: int = 60):
        """Main monitoring loop — runs continuously."""
        self._running = True
        logger.info(f"[SignalMonitor] Started. Checking every {interval_seconds}s.")
        while self._running:
            try:
                await self.check_all_alerts()
            except Exception as e:
                logger.error(f"[SignalMonitor] Loop error: {e}")
            await asyncio.sleep(interval_seconds)

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False
