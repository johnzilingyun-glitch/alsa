import asyncio
import httpx
import json
import hmac
import hashlib
import os

async def main():
    webhook_url = "http://127.0.0.1:8644/webhooks/alsa-alert"
    webhook_secret = "jR9oR2-DrTyHKLnwXB2mIPFK8mLlozbOL1IcsiLsbs0"

    payload_dict = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "⚡ 测试信号触发: ALSA Test"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "这是一条测试消息，用于验证 Hermes 链路是否连通。"
                    }
                }
            ],
        },
    }
    payload_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    sig = "sha256=" + hmac.new(
        webhook_secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    headers["X-Hub-Signature-256"] = sig

    async with httpx.AsyncClient(timeout=10.0) as client:
        print(f"Sending to {webhook_url} with signature {sig}")
        resp = await client.post(webhook_url, content=payload_bytes, headers=headers)
        print("Status code:", resp.status_code)
        print("Response:", resp.text)

if __name__ == "__main__":
    asyncio.run(main())
