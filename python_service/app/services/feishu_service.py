import os
import json
import threading
import logging
import lark_oapi as lark
from app.db.repositories.alert_repo import AlertRepository
from app.db.database import session_factory

logger = logging.getLogger("FeishuWS")

APP_ID = os.getenv("FEISHU_APP_ID", "cli_aaabfb340fb89cdc")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "YOUR_APP_SECRET")

def do_interactive_card(data: lark.Card) -> None:
    # Actually data is a CardAction object in older versions or something, but we can try to parse it.
    try:
        val = {}
        if hasattr(data, "action"):
            action = data.action
            if hasattr(action, "value"):
                val = action.value
            elif isinstance(action, dict):
                val = action.get("value", {})
        elif isinstance(data, dict):
            action = data.get("action", {})
            if isinstance(action, dict):
                val = action.get("value", {})
                
        if isinstance(val, str):
            import json
            try:
                val = json.loads(val)
            except:
                pass
        
        if not isinstance(val, dict):
            val = {}
            
        logger.info(f"[FeishuWS] Received card action value: {val}")
        
        if val.get("action") == "acknowledge_alert":
            alert_id = val.get("alert_id")
            if alert_id:
                repo = AlertRepository(session_factory)
                repo.acknowledge_alert(alert_id)
                logger.info(f"[FeishuWS] Acknowledged alert {alert_id}")
    except Exception as e:
        logger.error(f"[FeishuWS] Error handling card action: {e}", exc_info=True)

class FeishuWSService:
    def __init__(self):
        self.cli = None
        self._thread = None

    def start(self):
        if not APP_ID or not APP_SECRET:
            logger.warning("[FeishuWS] FEISHU_APP_ID or FEISHU_APP_SECRET not set, skipping Feishu WS")
            return

        logger.info("[FeishuWS] Starting Feishu Long Connection in background thread...")
        
        # We only care about card actions for now
        card_handler = lark.CardActionHandler.builder("", "").register(do_interactive_card).build()

        self.cli = lark.ws.Client(APP_ID, APP_SECRET,
                                  event_handler=card_handler,
                                  log_level=lark.LogLevel.INFO)
        
        self._thread = threading.Thread(target=self.cli.start, daemon=True)
        self._thread.start()

    def stop(self):
        if self.cli:
            # Note: lark_oapi ws client may not have a clean stop method exposed easily,
            # but since it's a daemon thread it will exit when the main program exits.
            pass

feishu_ws_service = FeishuWSService()
