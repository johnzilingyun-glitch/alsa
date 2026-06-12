import asyncio
import httpx
import json
import hmac
import hashlib
from datetime import datetime

WEBHOOK_URL = "http://localhost:8644/webhooks/alsa-alert"
WEBHOOK_SECRET = "jR9oR2-DrTyHKLnwXB2mIPFK8mLlozbOL1IcsiLsbs0"

async def test_rich_card():
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⚡ 信号触发: 腾讯控股 (0700.HK)"},
            "template": "orange",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**🎯 目标价达成**\n当前价 415.00 已达目标价 410.00\n💡 建议分批止盈退出"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "📈 **价格监控详情**\n**入场价**: 380.00 | **目标价**: 410.00 | **止损价**: 360.00\n**当前偏离入场价**: +9.21%\n📋 **投资论点**: 核心游戏业务复苏，视频号广告商业化提速"
                }
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [{
                    "tag": "plain_text",
                    "content": f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ALSA Test Monitor | 仅供参考"
                }]
            }
        ],
    }

    payload_dict = {
        "msg_type": "interactive",
        "card": card,
    }
    payload_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    sig = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    headers["X-Hub-Signature-256"] = sig

    print("Sending POST request to:", WEBHOOK_URL)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
        print("Status Code:", resp.status_code)
        print("Response:", resp.text)

if __name__ == "__main__":
    asyncio.run(test_rich_card())
