import os
import json
import asyncio
from dotenv import load_dotenv
import lark_oapi as lark
import logging

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FeishuWS")

APP_ID = "cli_aaabfb340fb89cdc"
APP_SECRET = "YOUR_APP_SECRET"

def do_interactive_card(data: lark.CardAction) -> None:
    logger.info(f"[FeishuWS] Received card action: {data.action.value}")
    # Here we would call the repository
    try:
        from app.db.repositories.alert_repo import AlertRepository
        from app.db.database import get_session
        
        val = data.action.value
        if val.get("action") == "acknowledge_alert":
            alert_id = val.get("alert_id")
            if alert_id:
                # Need a new session
                with next(get_session()) as db:
                    repo = AlertRepository(db)
                    repo.acknowledge_alert(alert_id)
                    logger.info(f"[FeishuWS] Acknowledged alert {alert_id}")
    except Exception as e:
        logger.error(f"[FeishuWS] Error handling card action: {e}")

def main():
    logger.info("Starting Feishu Long Connection...")
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .build()
    
    # We only care about card actions for now
    card_handler = lark.CardActionHandler.builder("", "", do_interactive_card).build()

    cli = lark.ws.Client(APP_ID, APP_SECRET,
                         event_handler=event_handler,
                         action_handler=card_handler,
                         log_level=lark.LogLevel.INFO)
    cli.start()

if __name__ == "__main__":
    main()
