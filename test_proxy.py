import asyncio, httpx, json, os

async def test():
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⚡ ALSA 代理直连测试"},
            "template": "blue"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "系统已成功将底层配置切换为 App ID 直连，卡片发送完全恢复！"
                }
            }
        ]
    }
    
    api_token = "5vQho3djKaHyCuWQWBdMOlLgJDCpQvQFzKcLlrOwbDw"
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://127.0.0.1:3000/api/v1/feishu/proxy-card",
            headers={"Authorization": f"Bearer {api_token}"},
            json={
                "card": card
            }
        )
        print("Send Result:", resp.status_code, resp.text)

asyncio.run(test())
