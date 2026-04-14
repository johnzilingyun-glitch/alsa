import { Router } from 'express';

const router = Router();

router.post('/feishu/send-report', async (req, res) => {
  const { content, feishuWebhookUrl } = req.body;
  const webhookUrl = feishuWebhookUrl || process.env.FEISHU_WEBHOOK_URL;

  if (!webhookUrl) {
    return res.status(500).json({ error: '飞书 Webhook 未配置。请在系统设置中填入 Webhook URL。' });
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

    // If it's a stock report and we have structured data, we could build a richer card here.
    // For now, the markdown content from the AI is already very rich.

    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        msg_type: 'interactive',
        card: card,
      }),
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

export default router;
