import * as lark from '@larksuiteoapi/node-sdk';

export function startFeishuWsClient() {
  const appId = process.env.FEISHU_APP_ID;
  const appSecret = process.env.FEISHU_APP_SECRET;

  if (!appId || !appSecret) {
    console.log('[Feishu WS] Missing FEISHU_APP_ID or FEISHU_APP_SECRET. Skipping WS connection.');
    return;
  }

  console.log('[Feishu WS] Starting Feishu WebSocket Client (Long Connection mode)...');

  // Handle Card Actions (button clicks on Interactive Cards)
  const cardActionHandler = new lark.CardActionHandler({
    encryptKey: '', 
    verificationToken: '' 
  }, async (data: any) => {
    console.log('[Feishu WS] CardAction triggered:', JSON.stringify(data));
    
    if (data && data.action && data.action.value) {
      const actionValue = data.action.value as any;
      if (actionValue.action === 'acknowledge_alert' && actionValue.alert_id) {
        try {
          const pythonUrl = process.env.PYTHON_BACKEND_URL || 'http://127.0.0.1:8001';
          const apiToken = process.env.API_TOKEN;
          const response = await fetch(`${pythonUrl}/api/alerts/${actionValue.alert_id}/acknowledge`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${apiToken}`,
              'Content-Type': 'application/json'
            }
          });

          if (response.ok) {
            console.log(`[Feishu WS] Successfully acknowledged alert ${actionValue.alert_id}`);
            // Return updated card & toast
            return {
              toast: { type: 'success', content: '已确认关注预警' },
              config: { wide_screen_mode: true },
              header: {
                title: { tag: "plain_text", content: "✅ 已阅确认成功" },
                template: "green"
              },
              elements: [
                {
                  tag: "div",
                  text: {
                    tag: "lark_md",
                    content: "您已成功确认此警报，**今日及后续将不再发送此股票的通知**。\n如需恢复，请前往 ALSA 系统前端的 [信号监控] - [历史触发] 列表中点击恢复。"
                  }
                }
              ]
            } as any;
          } else {
            console.error('[Feishu WS] Failed to acknowledge alert via backend API:', await response.text());
          }
        } catch (err) {
          console.error('[Feishu WS] Error calling backend API:', err);
        }
      }
    }
    
    // Default fallback return value
    return null;
  });

  const wsClient = new lark.WSClient({
    appId,
    appSecret,
    loggerLevel: lark.LoggerLevel.info
  });

  wsClient.start({ eventDispatcher: cardActionHandler as any }).then(() => {
    console.log('[Feishu WS] Feishu WebSocket Client started successfully.');
  }).catch((err) => {
    console.error('[Feishu WS] Failed to start Feishu WebSocket Client:', err);
  });
}
