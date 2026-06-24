<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# ALSA — AI-powered Living Stock Analyst

AI驱动的跨市场量化交易与研究平台。三层层架构：React SPA → Express API 网关 → FastAPI 后端。支持 A股、港股、美股，集成 LLM 智能分析、多专家讨论系统、模拟交易引擎和实时仪表盘。

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    用户访问方式                                │
│   浏览器 (http://localhost:5173)  │  CLI 命令行  │  飞书      │
└──────────────┬────────────────────┬──────────────┬───────────┘
               │                    │              │
┌──────────────▼────────────────────▼──────────────▼───────────┐
│              第1层：Express 网关 (Node.js)                     │
│              server.ts — 端口 3000                            │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ • 托管 React SPA (生产环境) / Vite 代理 (开发环境)       │    │
│  │ • AI 调用代理 (Gemini/DeepSeek/OpenAI/Anthropic)       │    │
│  │ • WebSocket 实时推送 (socket.io)                        │    │
│  │ • 转发数据请求到 Python 后端                             │    │
│  │ • 分析历史记录管理 (JSON 文件)                           │    │
│  │ • JWT 认证 + API 令牌鉴权 + 速率限制                     │    │
│  └──────────────────────────────────────────────────────┘    │
└────────────────────────────┬─────────────────────────────────┘
                            │ HTTP 代理 (/api/* → :8001)
┌───────────────────────────▼─────────────────────────────────┐
│              第2层：FastAPI 后端 (Python 3.11)                 │
│              python_service/main.py — 端口 8001               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ 分析引擎   │ │ 讨论系统   │ │ 数据湖    │ │ LLM 网关       │  │
│  │ (analysis) │ │(discussion)│ │ (lake)   │ │ (llm_gateway) │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ 量化引擎   │ │ 选股引擎   │ │ 行业分析   │ │ 回测引擎       │  │
│  │ (quant)   │ │(screening)│ │ (sector) │ │ (backtest)    │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ 风险管理   │ │ 大脑管理   │ │ 模拟交易   │ │ Celery 队列    │  │
│  │ (risk)    │ │ (brain)   │ │ (mtrading)│ │ (worker)      │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
└───────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              第3层：外部服务 & 数据源                             │
│  ┌──────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ Gemini    │ │ DeepSeek   │ │ AkShare   │ │ Yahoo Finance│  │
│  │ (AI主力)   │ │ (AI备用)   │ │ (A股数据)  │ │ (美股/港股)   │  │
│  └──────────┘ └───────────┘ └───────────┘ └──────────────┘  │
│  ┌──────────┐ ┌───────────┐ ┌───────────┐                   │
│  │ 讯飞 iask │ │ iwencai   │ │ SearXNG   │                   │
│  │ (快讯搜索) │ │ (金融搜索)  │ │ (通用搜索)  │                   │
│  └──────────┘ └───────────┘ └───────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

## 核心功能

| 功能 | 说明 |
|------|------|
| **多专家讨论分析** | 7-10 个 AI 专家角色轮流发言辩论，最终由首席策略师给出判断 |
| **跨市场支持** | A股 (AkShare) + 港股/美股 (Yahoo Finance) |
| **HTML 研报生成** | 带图表的专业级 HTML 研究报告 |
| **模拟交易 (Paper Trading)** | 基于 Qlib 的高保真模拟交易引擎 |
| **实时行情仪表盘** | React SPA 实时展示行情、信号、持仓 |
| **CLI 命令行工具** | 无需浏览器，终端中直接运行分析 |
| **多智能体大脑** | 长期记忆 + 系统演化 (genome) |
| **行业扫描** | LLM 驱动的板块轮动分析与选股推荐 |

## 快速启动

```bash
# 1. 安装 Node 依赖
npm install

# 2. 启动 Python 后端 (必需，提供 A股数据)
npm run dev:py

# 3. 启动前端 + Express 网关 (另一个终端)
npm run dev:no-ibkr

# 4. 浏览器打开 http://localhost:5173
```

或者使用启动脚本一键启动全部服务:

```bash
bash start-alsa.sh
```

## 命令速查

| 命令 | 用途 | 端口 |
|------|------|------|
| `npm run dev:no-ibkr` | Express 网关 + Vite 前端 (无 IBKR) | 3000 + 5173 |
| `npm run dev:py` | FastAPI 后端 | 8001 |
| `npm run dev` | 全栈 (含 IBKR 网关) | 3000 + 5173 + 8001 |
| `npm run build` | Vite 生产构建 → `dist/` | - |
| `npm run lint` | TypeScript 类型检查 (`tsc --noEmit`) | - |
| `npm test` | Vitest 前端测试 | - |
| `npm run test:all` | Vitest + Pytest 全量测试 | - |
| `npm run audit:repo` | 仓库卫生检查 (禁止 data/.db/.log/.env 进 git) | - |

### Python 命令行

```bash
# 分析股票并生成 HTML 研报
python python_service/cli.py analyze "贵州茅台"
python python_service/cli.py analyze "AAPL" -l deep -m US-Share
python python_service/cli.py analyze "00700" -m HK-Share -o ~/report.html

# 行业分析 (不传板块名称则先扫描市场推荐板块)
python python_service/cli.py sector "半导体"
python python_service/cli.py sector  # 交互式选择板块

# 配置管理
python python_service/cli.py config show
python python_service/cli.py config set gemini_api_key "你的Key"
python python_service/cli.py config get gemini_api_key
python python_service/cli.py config unset gemini_api_key
```

## 项目结构

```
├── src/                    # React 19 SPA
│   ├── components/         # 30+ UI 组件
│   ├── stores/             # 11 个 Zustand 状态仓库
│   ├── hooks/              # 业务逻辑 Hooks
│   ├── services/           # AI 分析管线 + 多专家讨论系统
│   └── types.ts            # 规范类型定义 (735行)
├── server/                 # Express 4 API 网关
│   ├── routes/             # API 路由
│   ├── llmGateway.ts       # LLM 代理 (Gemini/DeepSeek/OpenAI)
│   └── indicators/         # 技术/基本面/风控指标
├── python_service/         # FastAPI 后端 (325 文件)
│   ├── app/api/            # 26 个 API 端点
│   ├── app/services/       # 50+ 业务服务
│   ├── app/db/             # SQLite (SQLModel ORM)
│   ├── app/lake/           # DuckDB + Parquet 数据湖
│   ├── app/quant/          # Polars 量化指标
│   ├── app/backtest/       # 回测引擎
│   ├── app/risk/           # 风控 (熔断/预交易)
│   ├── cli.py              # CLI 命令行工具
│   └── tests/              # 62 个 pytest 测试
├── sdk/                    # 发布的 SDK 包 (js/ + python/)
├── scripts/                # IBKR 网关启动脚本
├── data/                   # 分析历史、大脑状态、SQLite 数据库
└── reports/                # 生成的 HTML/TXT 报告
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 19 + TypeScript |
| 样式 | Tailwind CSS 4 |
| 状态管理 | Zustand 5 |
| 图表 | Recharts 3 |
| 构建工具 | Vite 6 |
| Node 网关 | Express 4 + tsx |
| 实时通信 | Socket.IO 4 |
| Python 后端 | FastAPI + Uvicorn |
| ORM | SQLModel (SQLAlchemy) |
| 数据库 | SQLite (开发) / PostgreSQL (Docker) |
| 数据湖 | Parquet + DuckDB + Polars |
| 向量存储 | LanceDB |
| AI 主力 | Google Gemini SDK |
| AI 备用 | OpenAI / Anthropic SDK |
| A股数据 | AkShare |
| 美股/港股 | Yahoo Finance 2 |
| 异步队列 | Celery + Redis |
| 搜索 | DuckDuckGo / SearXNG |
| CLI | Click (Python) |
| 测试 | Vitest (前端) + Pytest (后端) |

## 环境变量

复制 `.env.runtime` 并填入 API 密钥:

```bash
# 必需
GEMINI_API_KEY=your_gemini_key_here      # Gemini AI (主要 LLM)

# 可选 (备用 LLM)
OPENAI_API_KEY=your_openai_key_here      # OpenAI GPT-4o-mini
ANTHROPIC_API_KEY=your_anthropic_key_here # Anthropic Claude

# 运行时
API_TOKEN=your_api_token                  # API 鉴权令牌
JWT_SECRET_KEY=your_jwt_secret            # JWT 签名密钥
SQLITE_PATH=data/alsa.db                  # SQLite 数据库路径
```

## 测试

```bash
# 前端测试 (Vitest)
npm test

# 单个测试文件
npx vitest run src/test/aiService.test.ts

# 全量测试 (前端 + Python)
npm run test:all

# Python 测试单独运行
PYTHONPATH=/abs/path/to/python_service python_service/.venv/bin/pytest python_service/tests/
```

## Docker 部署

```bash
# 构建并启动全部服务
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

## 文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 项目全景架构文档（中文）
- [AGENTS.md](AGENTS.md) — 项目知识库（AI 开发辅助）
- [CLAUDE.md](CLAUDE.md) — Karpathy 编码规范
- [docs/ALSA_CLI_GUIDE.md](docs/ALSA_CLI_GUIDE.md) — CLI 详细使用指南

## 已知问题

- `package.json` 中的名称是 `"react-example"` — 已知 Bug，非项目名称
- 没有 ESLint/Prettier/Biome — 仅使用 `tsc --noEmit` 做类型检查
- 没有 CI/CD 部署管线 — CI 只运行测试，不自动部署
- 两套 Python 虚拟环境: `python_service/.venv/` (3.11) + `.venv_qlib/` (3.9, Qlib 兼容)
- Python 200+ 处 `print()` 未使用日志框架 — 新代码应使用 `logging`
- Node 60+ 处 `console.log` 未使用结构化日志 — 新代码应避免
