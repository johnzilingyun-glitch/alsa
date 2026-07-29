import { Router } from 'express';
import crypto from 'crypto';

const router = Router();

function isValidFeishuUrl(url: string): boolean {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.endsWith('.feishu.cn') || urlObj.hostname === 'feishu.cn';
  } catch (e) {
    return false;
  }
}

router.post('/feishu/send-report', async (req, res) => {
  const { content, feishuWebhookUrl } = req.body;
  const webhookUrl = feishuWebhookUrl || process.env.FEISHU_WEBHOOK_URL;

  if (!webhookUrl) {
    return res.status(500).json({ error: '飞书 Webhook 未配置。请在系统设置中填入 Webhook URL。' });
  }

  if (!isValidFeishuUrl(webhookUrl)) {
    return res.status(403).json({ error: '非法的 Webhook URL 域名，仅允许飞书官方域名' });
  }

  if (!content?.trim()) {
    return res.status(400).json({ error: '内容不能为空' });
  }

  const TRUNCATE_LIMIT = 28000;
  let finalContent = content;
  if (finalContent.length > TRUNCATE_LIMIT) {
    finalContent = finalContent.substring(0, TRUNCATE_LIMIT) + '\n\n... (由于长度确认，已截断剩余内容)';
  }

  try {
    let title = 'AI 交易研报';
    let template = 'blue';

    if (req.body.type === 'daily') {
      title = '📅 市场晨间内参';
      template = 'orange';
    } else if (req.body.type === 'discussion') {
      title = '🚀 联席专家研报总结';
      template = 'indigo';
    } else if (req.body.type === 'chat') {
      title = '🧠 深度追问解答';
      template = 'turquoise';
    } else if (req.body.type === 'stock') {
      title = '🔍 个股速览报告';
      template = 'green';
    }

    const sections = finalContent.split('---');
    const cardElements: any[] = [];

    sections.forEach((section: string, index: number) => {
      const trimmedSection = section.trim();
      if (trimmedSection) {
        cardElements.push({
          tag: 'div',
          text: {
            tag: 'lark_md',
            content: trimmedSection
          }
        });
        if (index < sections.length - 1) {
          cardElements.push({ tag: 'hr' });
        }
      }
    });

    let card: any = {
      config: { wide_screen_mode: true },
      header: {
        title: { tag: 'plain_text', content: title },
        template: template,
      },
      elements: [
        ...cardElements,
        { tag: 'hr' },
        {
          tag: 'note',
          elements: [
            {
              tag: 'plain_text',
              content: `📅 ${new Date().toLocaleString('zh-CN')} | 🤖 TradingAgents 机构决策引擎 | 5-Layer Model`
            }
          ]
        }
      ],
    };

    const payloadObj = {
      msg_type: 'interactive',
      card: card,
    };
    const payloadStr = JSON.stringify(payloadObj);
    const webhookSecret = process.env.FEISHU_WEBHOOK_SECRET;
    let signature = '';

    if (webhookSecret) {
      const hmac = crypto.createHmac('sha256', webhookSecret);
      hmac.update(payloadStr, 'utf8');
      signature = `sha256=${hmac.digest('hex')}`;
    }

    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        ...(signature ? { 'X-Hub-Signature-256': signature } : {})
      },
      body: payloadStr,
    });

    if (!response.ok) {
      throw new Error(`Feishu API HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    if (data.code !== 0) {
      throw new Error(data.msg || 'Feishu API 返回错误');
    }

    res.json({ success: true });
  } catch (error) {
    console.error('Feishu Webhook Error:', error);
    res.status(500).json({ error: '无法发送报告至飞书，请检查 Webhook URL 是否正确。' });
  }
});

router.post('/feishu/proxy-card', async (req, res) => {
  const { card, feishuWebhookUrl } = req.body;
  const webhookUrl = feishuWebhookUrl || process.env.FEISHU_WEBHOOK_URL;
  const appId = process.env.FEISHU_APP_ID;
  const appSecret = process.env.FEISHU_APP_SECRET;
  const receiveId = process.env.FEISHU_RECEIVE_ID;

  if (!webhookUrl && !(appId && appSecret && receiveId)) {
    return res.status(500).json({ error: '飞书配置缺失（需配置 Webhook 或 AppID/Secret/ReceiveID）。' });
  }

  const payloadObj = { msg_type: 'interactive', card: card };
  const payloadStr = JSON.stringify(payloadObj);

  try {
    if (appId && appSecret && receiveId) {
      // Use Feishu Open API App Bot approach
      const authRes = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app_id: appId, app_secret: appSecret })
      });
      const authData = await authRes.json();
      if (!authData.tenant_access_token) {
        throw new Error('无法获取 tenant_access_token');
      }

      // Automatically determine receive_id_type
      const receiveIdType = receiveId.startsWith('ou_') ? 'open_id' : 
                           receiveId.startsWith('oc_') ? 'chat_id' : 'email';

      const sendRes = await fetch(`https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=${receiveIdType}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authData.tenant_access_token}`
        },
        body: JSON.stringify({
          receive_id: receiveId,
          msg_type: 'interactive',
          content: JSON.stringify(card)
        })
      });

      if (!sendRes.ok) throw new Error(`Feishu API HTTP ${sendRes.status}`);
      const sendData = await sendRes.json();
      if (sendData.code !== 0) throw new Error(sendData.msg || 'Feishu API 返回错误');
      
    } else {
      // Legacy Webhook approach
      if (!isValidFeishuUrl(webhookUrl)) {
        return res.status(403).json({ error: '非法的 Webhook URL 域名，仅允许飞书官方域名' });
      }

      const webhookSecret = process.env.FEISHU_WEBHOOK_SECRET;
      let signature = '';

      if (webhookSecret) {
        try {
          const hmac = crypto.createHmac('sha256', webhookSecret);
          hmac.update(payloadStr, 'utf8');
          signature = `sha256=${hmac.digest('hex')}`;
        } catch (e) {
          console.error("Failed to generate HMAC signature:", e);
        }
      }

      const response = await fetch(webhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(signature ? { 'X-Hub-Signature-256': signature } : {})
        },
        body: payloadStr
      });

      if (!response.ok) throw new Error(`Feishu API HTTP ${response.status}`);
      const data = await response.json();
      if (data.code !== 0) throw new Error(data.msg || 'Feishu API 返回错误');
    }

    res.json({ success: true });
  } catch (error) {
    console.error('Feishu Proxy Error:', error);
    res.status(500).json({ error: '无法发送报告至飞书' });
  }
});

router.post('/feishu/callback', async (req, res) => {
  const payload = req.body;

  // Handle Feishu URL Verification
  if (payload && payload.type === 'url_verification') {
    return res.json({ challenge: payload.challenge });
  }

  // Handle Interactive Card Button Clicks
  try {
    if (payload && payload.action && payload.action.value) {
      const actionValue = payload.action.value;
      
      if (actionValue.action === 'acknowledge_alert' && actionValue.alert_id) {
        // Call internal Python API to acknowledge
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
          // Return an updated card JSON & toast to Feishu to reflect the acknowledged state
          return res.json({
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
          });
        } else {
          console.error("Failed to acknowledge alert:", await response.text());
        }
      }
    }
    
    // Default success response
    res.json({ code: 0, msg: "success" });
  } catch (err) {
    console.error("Feishu Callback Error:", err);
    res.status(500).json({ error: "Internal Server Error" });
  }
});

export default router;
