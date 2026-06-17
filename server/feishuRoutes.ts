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

  if (!webhookUrl) {
    return res.status(500).json({ error: '飞书 Webhook 未配置。' });
  }

  if (!isValidFeishuUrl(webhookUrl)) {
    return res.status(403).json({ error: '非法的 Webhook URL 域名，仅允许飞书官方域名' });
  }

  const payloadObj = { msg_type: 'interactive', card: card };
  const payloadStr = JSON.stringify(payloadObj);
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

  try {
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(signature ? { 'X-Hub-Signature-256': signature } : {})
      },
      body: payloadStr
    });

    if (!response.ok) {
      throw new Error(`Feishu API HTTP ${response.status}`);
    }
    const data = await response.json();
    if (data.code !== 0) {
      throw new Error(data.msg || 'Feishu API 返回错误');
    }
    res.json({ success: true });
  } catch (error) {
    console.error('Feishu Webhook Error:', error);
    res.status(500).json({ error: '无法发送报告至飞书' });
  }
});

export default router;
