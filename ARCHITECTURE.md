# ALSA 项目架构文档

> **ALSA** = AI-powered Living Stock Analyst（AI 驱动的智能股票分析师）
>
> 一份让新手也能快速理解的项目全景图

---

## 0. 这个项目是做什么的？

用一句话说：**输入一只股票的名字，AI 会像专业分析团队一样，多个"专家"开会讨论，最终生成一份完整的投资研报（HTML 格式）。**

就像你同时雇了：
- 🔍 一个深度研究员（搜集资料）
- 📊 一个技术分析师（看K线图）
- 📈 一个基本面分析师（读财报）
- 🐂 一个看多研究员 + 🐻 一个看空研究员（正反辩论）
- 🎯 一个首席策略师（做最终决策）

他们在后台开完会，给你一份带图表的 HTML 报告。

---

## 1. 整体架构（三层结构）

```
┌─────────────────────────────────────────────────────────────┐
│                     用户访问方式                              │
│  浏览器 (http://localhost:3000)  │  CLI 命令行  │  Feishu飞书  │
└──────────────┬──────────────────┬──────────────┬─────────────┘
               │                  │              │
┌──────────────▼──────────────────▼──────────────▼─────────────┐
│              第 1 层：Express 网关 (Node.js)                  │
│              server.ts — 端口 3000                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 功能：                                                │   │
│  │ • 托管 React 前端 (Vite SPA)                          │   │
│  │ • 代理 AI 调用到 Gemini/DeepSeek                      │   │
│  │ • WebSocket 实时推送 (socket.io)                      │   │
│  │ • 转发数据请求到 Python 后端                           │   │
│  │ • 分析历史记录管理 (JSON 文件存储)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP 代理
┌──────────────────────────▼──────────────────────────────────┐
│           第 2 层：Python FastAPI 后端 — 端口 8001            │
│           python_service/main.py                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│  │ 分析引擎    │ │ 讨论系统    │ │ 数据湖      │ │ 量化引擎  │ │
│  │ (analysis) │ │ (discussion)│ │ (lake)     │ │ (quant)  │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │ 选股引擎    │ │ 行业分析    │ │ LLM 网关    │               │
│  │ (screening)│ │ (sector)   │ │ (gateway)  │               │
│  └────────────┘ └────────────┘ └────────────┘               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              第 3 层：外部服务 & 数据源                        │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Gemini  │ │DeepSeek  │ │ AkShare  │ │Yahoo Finance │  │
│  │  (AI)   │ │  (AI)    │ │(A股数据) │ │ (美股/港股)   │  │
│  └─────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 核心流程：一次分析是如何运行的？

```
用户输入 "贵州茅台"
        │
        ▼
┌──────────────────┐
│ 1. 智能识别股票    │  输入股票名 → CLI/前端自动匹配代码 (600519)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ 2. 采集市场快照    │  AkShare 拉取实时行情、K线历史
│                   │  存入 Parquet 数据湖 (python_service/data/lake/)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ 3. 计算量化指标    │  Polars 引擎计算 MA、RSI、MACD、布林带等
│                   │  quant/polars_indicators.py
└──────┬───────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│ 4. 多专家讨论会 (核心!)                        │
│                                              │
│  根据分析深度 (quick/standard/deep/sector)     │
│  不同专家按轮次发言：                           │
│                                              │
│  Deep 深度模式 (10 轮)：                       │
│  Round 1: 深度研究员 (搜集所有资料)             │
│  Round 2: 技术分析师 + 基本面分析师 (并行)       │
│  Round 3: 情绪分析师                          │
│  Round 4: 看多研究员 + 看空研究员 (正反辩论)     │
│  Round 5: 激进/保守/中性 三位风险评估师 (并行)   │
│  Round 6: 逆向策略师 (挑战主流观点)             │
│  Round 7: 专业评审员 (审核前面所有结论)          │
│  Round 8: 再次辩论 (多空研究员复核)             │
│  Round 9: 索罗斯风格 + 增长愿景 + 宏观对冲      │
│           + 价值投资大师 (四人并行)             │
│  Round 10: 首席策略师 (最终判断: 买/持/卖)       │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────┐
│ 5. 生成 HTML 报告  │  report_generator_service.py
│                   │  输出带图表的专业研报
└──────────────────┘
```

---

## 3. 目录结构速览

```
alsa/
│
├── 📄 server.ts                # Node.js Express 网关入口
├── 📄 vite.config.ts           # 前端构建配置
├── 📄 package.json             # Node 依赖 (React, Gemini SDK, Socket.io...)
│
├── 📂 src/                     # 🖥️ 前端 React 代码
│   ├── App.tsx                 # 主应用组件
│   ├── types.ts                # 所有 TypeScript 类型定义 (730行)
│   ├── components/             # UI 组件
│   │   ├── analysis/           # 分析结果展示组件
│   │   ├── dashboard/          # 仪表盘 (市场概览, 信号中心, 行业扫描)
│   │   ├── layout/             # 布局组件 (Header)
│   │   └── shared/             # 通用组件 (Toast, Dialog)
│   ├── hooks/                  # 业务逻辑 Hooks
│   │   ├── useStockAnalysis.ts # 股票分析核心逻辑
│   │   ├── useDiscussion.ts   # 讨论状态管理
│   │   └── useChat.ts         # AI 聊天逻辑
│   ├── stores/                 # Zustand 状态管理
│   │   ├── useAnalysisStore.ts # 分析结果状态
│   │   ├── useUIStore.ts       # UI 显示状态
│   │   └── useConfigStore.ts   # 配置状态
│   ├── services/               # 业务服务层
│   │   ├── geminiService.ts    # Gemini AI 调用
│   │   ├── llmProvider.ts      # 多 LLM 回退策略
│   │   ├── discussion/         # 多专家讨论编排
│   │   │   ├── orchestrator.ts # 讨论编排器
│   │   │   ├── skipRules.ts    # 跳过规则
│   │   │   └── prompts/        # 各专家角色 Prompt
│   │   └── api/                # API 客户端
│   └── i18n/                   # 国际化 (中/英)
│
├── 📂 server/                  # 🖥️ Express 路由 & 工具
│   ├── routes/
│   │   └── analysisRoutes.ts   # 分析 API 路由
│   ├── indicators/
│   │   ├── technicalCalc.ts    # 技术指标计算
│   │   ├── fundamentalScoring.ts # 基本面评分
│   │   └── riskMetrics.ts      # 风险度量
│   ├── repositories/
│   │   └── analysisRepository.ts # 分析结果存储
│   └── __tests__/              # 服务端测试
│
├── 📂 python_service/          # 🐍 Python 后端
│   ├── main.py                 # FastAPI 入口 (端口 8001)
│   ├── cli.py                  # CLI 命令行工具 (alsacli)
│   ├── pyproject.toml          # Python 依赖配置
│   ├── app/
│   │   ├── api/                # REST API 端点
│   │   │   ├── router.py       # 总路由
│   │   │   ├── analysis.py     # 分析 API
│   │   │   ├── market.py       # 市场数据 API
│   │   │   ├── sector.py       # 行业分析 API
│   │   │   ├── screening.py    # 选股 API
│   │   │   ├── alerts.py       # 价格预警 API
│   │   │   ├── watchlist.py    # 自选股 API
│   │   │   ├── journal.py      # 交易日志 API
│   │   │   ├── brain.py        # 大脑管理 API
│   │   │   └── technicals.py   # 技术指标 API
│   │   ├── services/           # 核心业务服务
│   │   │   ├── analysis_job_service.py    # 分析任务编排 (566行)
│   │   │   ├── discussion_service.py       # 多专家讨论 (810行)
│   │   │   ├── llm_gateway.py             # LLM 网关 (743行)
│   │   │   ├── sector_analysis_service.py # 行业分析
│   │   │   ├── screening_service.py       # 选股引擎
│   │   │   ├── market_snapshot_service.py # 市场快照
│   │   │   ├── market_data_service.py     # 市场数据服务
│   │   │   ├── report_generator_service.py # 报告生成
│   │   │   ├── search_toolkit.py          # 搜索工具箱
│   │   │   ├── sentiment_data_service.py  # 情绪数据
│   │   │   ├── macro_service.py           # 宏观分析
│   │   │   ├── brain_manager.py           # 大脑管理
│   │   │   └── expert_tools.py            # 专家工具集
│   │   ├── db/                 # 数据库层 (SQLite)
│   │   │   ├── models.py       # 数据模型 (SQLModel)
│   │   │   ├── sqlite.py       # 数据库初始化
│   │   │   └── repositories/   # 数据仓库
│   │   ├── lake/               # 数据湖 (Parquet + DuckDB)
│   │   │   ├── parquet_store.py  # Parquet 存储
│   │   │   └── duckdb_engine.py  # DuckDB 查询引擎
│   │   ├── quant/              # 量化引擎
│   │   │   └── polars_indicators.py  # Polars 技术指标
│   │   ├── prompting/          # Prompt 管理
│   │   │   ├── registry.py     # Prompt 注册
│   │   │   ├── runtime.py      # Prompt 运行时
│   │   │   └── templates/      # 50+ 专家角色 Prompt 模板
│   │   ├── vector/             # 向量存储
│   │   │   └── lancedb_store.py # LanceDB 向量检索
│   │   └── utils/              # 工具函数
│   ├── data/                   # 数据文件
│   │   └── lake/               # Parquet 分区数据
│   └── tests/                  # Python 测试
│
├── 📂 data/                    # Node 端数据存储
│   ├── history/                # 分析历史 (JSON, 30天保留)
│   └── alsa.db / app.db        # SQLite 数据库
│
└── 📂 docs/                    # 文档
    ├── ALSA_CLI_GUIDE.md       # CLI 使用指南
    └── superpowers/plans/      # 开发计划
```

---

## 4. 核心子系统详解

### 4.1 多专家讨论系统 (`discussion_service.py`)

这是项目最核心的创新点。不是让一个 AI 判断股票，而是让 **多个"专家 AI"开会辩论**。

**讨论拓扑 (Topology)**：

| 模式 | 轮数 | 适用于 |
|------|------|--------|
| `quick` | 4 轮 | 快速扫描 |
| `standard` | 7 轮 | 常规分析 |
| `deep` | 10 轮 | 深度研究 |
| `sector` | 4 轮 | 行业分析 |

**核心机制**：
- **并行发言**：同一轮内的多个专家同时发言（如多空研究员同时输出）
- **上下文传递**：每轮专家的输出会传给下一轮，形成链式推理
- **辩论博弈**：看多研究员和看空研究员在 Round 4 和 Round 8 进行两轮辩论
- **首席决策**：最后首席策略师综合所有观点给出最终判断

### 4.2 LLM 网关 (`llm_gateway.py`)

统一的 AI 调用层，支持多模型回退：

```
请求 → Gemini 3.1 Pro → (失败)
     → Gemini 3.1 Flash Lite → (失败)
     → Gemini 1.5 Pro → (失败)
     → DeepSeek V4 Pro → (失败)
     → 默认 LLM
```

支持：
- **Gemini** (Google genai SDK) — 原生工具调用 (tool use)
- **DeepSeek** (OpenAI 兼容 API) — 备用模型
- **默认 LLM** (可配置任意 OpenAI 兼容端点)

### 4.3 数据湖 (`lake/`)

使用 **Parquet + DuckDB** 架构：

```
python_service/data/lake/
  └── ohlc/                          # OHLC 行情数据
      ├── market=A-Share/            # A股分区
      │   └── year=2026/
      │       └── symbol=600519/     # 贵州茅台
      │           └── part-000.parquet
      ├── market=US-Share/           # 美股分区
      │   └── year=2026/
      │       └── symbol=UBER/
      │           └── part-000.parquet
      └── ...
```

- **Parquet**：列式存储，压缩率高，适合时序数据
- **DuckDB**：嵌入式 OLAP 引擎，SQL 查询 Parquet 文件，无需启动数据库服务
- **Polars**：Rust 写的 DataFrame 库，比 Pandas 快 5-10 倍

### 4.4 数据库层 (`db/`)

使用 **SQLite + SQLModel**（类似 SQLAlchemy 的现代 ORM）：

| 表名 | 用途 |
|------|------|
| `User` | 用户管理 |
| `Watchlist` / `WatchlistItem` | 自选股列表 |
| `AnalysisJob` | 分析任务（排队/运行/完成/失败） |
| `AnalysisRun` | 每次分析的最终结果 |
| `AnalysisArtifact` | 分析产物（HTML报告/讨论记录） |
| `JournalEntry` | 交易日志（买入/卖出/持有决策） |
| `SearchAlert` | 价格预警（含止损/止盈/事后复盘） |
| `Catalyst` | 催化剂事件（财报/产品发布/监管） |
| `PromptVersion` / `PromptRun` | Prompt 版本管理和调用追踪 |
| `AuditLog` | 审计日志 |

### 4.5 选股引擎 (`screening_service.py`)

预设 5 种选股策略：

| 策略 | 筛选条件 |
|------|----------|
| **深度价值** | PE < 15, PB < 2, 自由现金流收益率 > 5% |
| **高增长** | 营收增长 > 15%, 盈利增长 > 20% |
| **质量复利** | ROE > 15%, 负债率 < 1, 连续3年正现金流 |
| **做空候选** | 营收下滑 > 5%, 利润率压缩, 高负债 |
| **动量领先** | RS排名 > 80, 站上200日均线, 放量 |

### 4.6 CLI 命令行工具 (`cli.py`)

可以在终端独立使用，无需打开浏览器：

```bash
# 基本分析
python python_service/cli.py analyze "贵州茅台"

# 指定分析深度和市场
python python_service/cli.py analyze "AAPL" -l deep -m US-Share

# 配置 API Key
python python_service/cli.py config set gemini_api_key "你的Key"

# 查看配置
python python_service/cli.py config show
```

---

## 5. 技术栈总览

| 层级 | 技术 | 用途 |
|------|------|------|
| **前端框架** | React 19 + TypeScript | 单页应用 |
| **UI 样式** | Tailwind CSS 4 | 原子化 CSS |
| **状态管理** | Zustand 5 | 轻量状态管理 |
| **图表** | Recharts 3 | 股票走势图 |
| **动画** | Motion (Framer Motion) | 过渡动画 |
| **国际化** | i18next | 中/英文切换 |
| **构建工具** | Vite 6 | 前端构建 |
| **Node 网关** | Express 4 | API 代理 + 静态托管 |
| **实时通信** | socket.io 4 | WebSocket 推送 |
| **Python 后端** | FastAPI + Uvicorn | REST API 服务 |
| **ORM** | SQLModel (SQLAlchemy) | 数据库建模 |
| **数据库** | SQLite | 嵌入式数据库 |
| **数据湖** | Parquet + DuckDB + Polars | 时序行情存储和查询 |
| **向量存储** | LanceDB | 语义检索 |
| **A股数据** | AkShare | 免费 A 股数据源 |
| **美股/港股** | Yahoo Finance 2 | 美股港股数据 |
| **AI 引擎** | Gemini SDK + OpenAI SDK | 多 LLM 支持 |
| **搜索** | DuckDuckGo / SearXNG | 联网搜索补充信息 |
| **CLI** | Click | Python 命令行框架 |
| **测试** | Vitest (前端) + Pytest (后端) | 双端测试覆盖 |

---

## 6. 启动方式

```bash
# 1. 启动全栈 (前端 + Node 网关)
npm run dev          # 端口 3000

# 2. 单独启动 Python 后端 (必须，提供 A 股数据)
npm run dev:py       # 端口 8001

# 3. 或者使用 CLI 独立运行分析
python python_service/cli.py analyze "贵州茅台"
```

---

## 7. 新手快速上手指南

### 想理解代码，从哪看起？

1. **先看 `src/types.ts`** — 了解所有数据结构（StockInfo, Market, AnalysisResult...）
2. **再看 `python_service/main.py`** — 理解后端如何启动，有哪些服务
3. **再看 `python_service/app/services/analysis_job_service.py`** — 理解一次分析的生命周期
4. **深入 `discussion_service.py`** — 理解多专家讨论如何编排
5. **最后看 `src/App.tsx`** — 理解前端如何把后端数据展示出来

### 想修改某个功能？

| 想改什么 | 改哪个文件 |
|----------|-----------|
| 修改分析报告的样式 | `python_service/app/services/report_generator_service.py` |
| 新增一个专家角色 | `python_service/app/prompting/templates/` 添加新模板 + `discussion_service.py` 注册 |
| 修改选股策略 | `python_service/app/services/screening_service.py` 的 `SCREEN_PRESETS` |
| 改前端 UI 组件 | `src/components/analysis/` 下的对应组件 |
| 添加新的数据源 | `python_service/app/services/market_data_service.py` |
| 修改讨论拓扑 | `discussion_service.py` 的 `DEEP_TOPOLOGY` 等数组 |

---

## 8. 关键约定

- **市场类型** 固定为 `"A-Share" | "HK-Share" | "US-Share"`，不可随意用字符串
- **A 股代码** 必须是 6 位数字，科创板 (68xxxx) 和创业板 (30xxxx) 涨跌幅 ±20%
- **API 响应格式** 统一为 `{ success: boolean, data?: any, error?: string }`
- **国际化** UI 文本一律放到 `src/i18n/locales/zh.json` 和 `en.json`
- **大组件懒加载** 在 `App.tsx` 中使用 `React.lazy()`
- **分析历史** 在 `data/history/` 目录以 JSON 文件存储，保留 30 天

---

# 第二部分：v3.1 多智能体新架构（已就绪，待接入）

> 基于 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` v3.1
> 落地日期：2026-07-09 ~ 2026-07-10
> 状态：**七层架构全部落地 + 端到端可运行 + 132 项测试全绿**，当前为增量非破坏设计，**尚未接入 API/Job Service**（旧 discussion_service 仍在运行）

## 9. 新架构总览（七层 + 横切）

```
┌──────────────────────────────────────────────────────────────┐
│  前台: React SPA "AI 每日智析" (端口 3000)                     │
│  → Express 网关 (Node.js server.ts) → Python FastAPI (8001)   │
└──────────────────────────┬───────────────────────────────────┘
                           │ /api/analysis/jobs (POST 202 异步)
┌──────────────────────────▼───────────────────────────────────┐
│  AnalysisJobService (现状: 调 discussion_service 旧流程)       │
│  ┌─ 灰度开关(待加): use_new_pipeline=True → AnalysisPipeline ─┐│
│  │                                                              ││
│  │  ① Request    Symbol Resolve + Intent Parse                  ││
│  │  ② Planning   PlannerService.plan() → ExecutionPlan (Flash)  ││
│  │  ③ Execution  DAGEngine.run() → list[AgentResult] (动态并行) ││
│  │     └─ BaseAgent.run: ContextBuilder + Handoff + SubAgent    ││
│  │                  + 结构化输出 + EvidenceBus                   ││
│  │  ④ Evidence   EvidenceAggregator.aggregate() (stance 聚合)   ││
│  │  ⑤ Reflection ReflectionAgent.critique() (可回溯 max=2)     ││
│  │     └─ [HITL interrupt: post_reflection / pre_decision]      ││
│  │  ⑥ Decision   DecisionAgent.decide() → FinalDecision        ││
│  │  ⑦ Report     ReportBuilder.build_markdown() (证据可追溯)    ││
│  │     └─ OutputGuardrail.check() 拦截低质输出                   ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
│  横切层:                                                          │
│  • ToolRegistry (能力矩阵+前置校验+跨Agent缓存)  [Phase 1]       │
│  • ContextBuilder (原始数据→最小高价值上下文)     [Phase 1]       │
│  • CheckpointStore (pause/resume)                [Phase 5]       │
│  • Memory 四层 (Session/Analysis/Project/User)   [Phase 5]       │
│  • Tracer (全链路 span 调用树)                   [§10.3 #4]      │
│  • RoleRouter (Flash 整理 / Pro 推理, 成本↓>50%) [Phase 4]       │
│  • HITL interrupt + Streaming (§10.3 #1/#3)      [Pipeline]      │
└───────────────────────────────────────────────────────────────────┘
```

## 10. 前台用户如何使用

### 当前可用方式（旧流程，已上线）
1. **浏览器访问** `http://localhost:3000` → "AI 每日智析" 首页
2. **输入股票**：股票代码或名称（如 "贵州茅台" / "AAPL" / "0700.HK"）
3. **选择分析深度**：quick / standard / deep
4. **提交分析**：前端 POST `/api/analysis/jobs` → 返回 job_id（202 异步）
5. **查看进度**：前端轮询 `/api/analysis/jobs/{job_id}` 或 WebSocket 推送
6. **查看报告**：完成后 GET `/api/analysis/runs/{id}` → HTML 报告（带图表）
7. **导出分享**：`/api/analysis/jobs/{id}/report`（重新生成）/ `export/pdf` / `export/share-card`

### 新架构启用后（待接入，灰度）
- 同样的前台操作流程不变
- 后端 `AnalysisJobService` 通过开关切换到 `AnalysisPipeline.run()`
- **新增能力**（待 API 暴露）：
  - 结构化 `FinalDecision`（评分/立场/行动/置信/可执行性）
  - 证据可追溯报告（每条结论带 source/agent/stance）
  - HITL 审批（关键决策前暂停等人工确认）
  - Streaming 阶段进度（Planner→DAG→Reflection→Decision 实时事件）

## 11. 前后台匹配度分析

| 维度 | 状态 | 说明 |
|------|------|------|
| 前端 API 调用 ↔ 后端端点 | ✅ 匹配 | 前端调 `/api/analysis/jobs` 等，后端有完整端点 |
| 旧流程（discussion_service）| ✅ 完整可用 | 前端能正常生成 HTML 报告 |
| 新架构 Pipeline 接入 API | ⚠️ 未接入 | `AnalysisJobService` 仍调 `discussion_service.run_discussion`（line 398），未调 `analysis_pipeline.run()` |
| FinalDecision 结构化输出 | ⚠️ 未暴露 | 新架构产出 `FinalDecision`，但 API 仍返回旧 discussion 自由文本 |
| ReportBuilder markdown 报告 | ⚠️ 未暴露 | 新 `ReportBuilder` 产出 markdown，API 仍用旧 `report_generator_service` HTML |
| HITL 审批 | ⚠️ 未暴露 | Pipeline 支持 interrupt，但无 API 端点暂停/审批 |
| Streaming 进度 | 🟡 部分 | 前端有 WebSocket，但新 Pipeline 的 `run_streaming` 阶段事件未对接 |
| OutputGuardrail | ⚠️ 未接入 | 新 guardrail 拦截低质输出，但未在 API 层生效 |
| Tracer 可观测性 | ⚠️ 未对接 | 新 Tracer 全链路 span，但未对接现有 metrics/audit 展示 |

**结论**：前台 UI 与后台**接口层匹配**（能正常运行），但**新架构（Phase 1-7）尚未接入业务流程**。新架构是"已就绪待接入"状态，需通过灰度开关切换。

## 12. 新架构接入路径（灰度，3 步）

### 步骤 1：AnalysisJobService 加灰度开关
```python
# analysis_job_service.py (line ~398)
if config.get("use_new_pipeline"):
    from .analysis_pipeline import analysis_pipeline
    result = await analysis_pipeline.run(symbol, question, market=market, snapshot=snapshot)
    # result.decision / result.report / result.aggregated / result.critique
else:
    discussion_messages = await discussion_service.run_discussion(...)  # 旧流程
```

### 步骤 2：API 暴露新结构化字段
在 `/api/analysis/runs/{id}` 响应中追加：
```json
{
  "final_decision": {"score": 0.75, "stance": "bullish", "action": "buy", "can_act": true},
  "evidence": [{"claim": "...", "supporting": [...], "contradicting": [...], "consensus": 0.8}],
  "guardrail": {"action": "pass", "issues": []},
  "report_markdown": "...",
  "trace_summary": {"span_count": 7, "total_duration_ms": 12345}
}
```

### 步骤 3：HITL + Streaming API（可选增强）
- `POST /api/analysis/jobs/{id}/interrupt` → 暂停点查询
- `POST /api/analysis/jobs/{id}/approve` → 审批继续
- WebSocket 推送 `run_streaming` 阶段事件（复用现有 socket.io）

## 13. 新架构文件清单（Phase 1-7 全部模块）

```
python_service/app/
├── schemas/contracts.py              # 层间数据契约 (Phase 1)
├── services/
│   ├── context_builder.py            # 上下文构建器 (Phase 1)
│   ├── tools/{registry,shared_cache,preconditions,metrics}.py  # Tool 治理 (Phase 1)
│   ├── planner_service.py            # Planner 动态规划 (Phase 3)
│   ├── evidence_store.py             # Evidence Aggregator (Phase 3)
│   ├── role_router.py                # role→model 路由 (Phase 4)
│   ├── checkpoint_store.py           # pause/resume (Phase 5)
│   ├── memory_store.py               # Memory 四层 (Phase 5)
│   ├── doc_chunker.py                # RAG 文档分块 (Phase 5 补全)
│   ├── output_guardrail.py           # 输出校验 (§10.3 #2)
│   └── analysis_pipeline.py          # ★ 端到端编排器 (架构闭环)
├── agents/
│   ├── base_agent.py                 # BaseAgent (Phase 2)
│   ├── handoff.py                    # Handoff 双向委托 (Phase 2)
│   ├── evidence_bus.py               # EvidenceBus (Phase 2)
│   ├── agent_result_schema.py        # 结构化输出 (Phase 2)
│   ├── expert_agents.py              # SubAgent + 具体 Agent (Phase 2)
│   ├── reflection_agent.py           # 可回溯反思 (Phase 4)
│   ├── decision_agent.py             # Decision → FinalDecision (Phase 4)
│   └── report_builder.py             # ⑦ Report (Phase 7)
├── engine/dag_engine.py              # DAG 动态并行 (Phase 3)
└── observability/trace.py            # 全链路 trace (§10.3 #4)

测试: tests/test_phase{1,2,3,4,5_7}*.py + test_remaining* + test_analysis_pipeline*
     + run_phase*_standalone.py (132 项全绿)
```

## 14. v3.1 修复与 §10.3 完成状态

- **v3.1 的 12 处逻辑矛盾修复**：全部落地（stance 维度 / Handoff 双向 / ToolRegistry 治理 / rerun 动态预算 / Checkpoint 归属 / Phase 边界等）
- **11 个 P0/P1 差距**：全部修复（规划/并行/通信/实例/Evidence/Reflection/上下文/输出/模型路由/联网收口/Tool治理）
- **§10.3 六项**：✅ #1 HITL / #2 输出校验 / #3 Streaming / #4 trace / #6 记忆持久化；🟡 #5 多模型（tier 已做，多厂商配置扩展）

## 15. 新旧架构对照

| 维度 | 旧（discussion_service，运行中）| 新（AnalysisPipeline，已就绪）|
|------|--------------------------------|------------------------------|
| 编排 | 固定拓扑 QUICK/STANDARD/DEEP + LangGraph | Planner 动态规划 + DAGEngine 动态并行 |
| Agent | make_node 闭包 | BaseAgent 独立实例 + Handoff + SubAgent |
| 通信 | history_states dict（只读上一轮）| EvidenceBus + Handoff 双向委托 |
| Evidence | Professional Reviewer 找矛盾 | Aggregator stance 维度聚合 + 冲突标记 |
| Reflection | 一次性 self_reflection | 可回溯 rerun max=2 |
| 输出 | 自由文本截断 2000 字 | 结构化 JSON FinalDecision |
| 模型 | 全程 Pro | Flash 整理 / Pro 推理（成本↓>50%）|
| 报告 | HTML（report_generator_service）| Markdown + 结构化 dict（ReportBuilder）|
| 可观测 | failure_capture 事件级 | + Tracer 全链路 span |
| 治理 | 会话级去重 | ToolRegistry 跨Agent缓存 + 前置校验 |

> **迁移原则**：增量非破坏，灰度切换。旧流程保留可用，新架构通过开关接入，逐验证后切换。

---

**文档版本**：ARCHITECTURE.md v2（追加 v3.1 新架构章节）· 2026-07-10
**新架构状态**：全部落地 + 端到端可运行 + 132 项测试全绿，待接入 API 层