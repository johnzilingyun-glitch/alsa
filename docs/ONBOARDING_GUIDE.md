# ALSA 新手入门与项目架构说明书

> **ALSA** = **AI**-powered **L**iving **S**tock **A**nalyst（AI 驱动的智能股票分析师）
>
> 💡 **目标**：输入任意股票名称或代码，系统自动拉取实时行情与基本面数据，编排十余位“AI 专家”召开投资共识辩论会，最终生成一份具备机构级专业度、图文并茂的 HTML 投资研报。

---

## 1. 核心业务愿景：解决什么痛点？

在传统金融领域，要对一只股票做深度研究，通常需要雇佣一个庞大的**分析师团队**：
1. **深度研究员**：全网抓取最新新闻、公告、行业研报。
2. **技术分析师**：看K线走势、均线支撑、超买超卖指标。
3. **基本面分析师**：精读财报，分析 ROE、利润率、负债比及估值水平。
4. **看多/看空研究员**：寻找买入逻辑，同时挑毛病（风险防范）。
5. **策略师与风控师**：做压力测试，计算安全边际，最终给出合理的交易计划。

这一套流程不仅耗时数天，而且极其依赖个人精力。
**ALSA 的核心价值**：**用多 Agent 协作网络，在数分钟内高质量、低成本地复刻上述流程。** 它不仅仅是让一个 AI 概括信息，而是让一群不同分工的 AI 专家在后台激烈辩论，互相挑错，直到达成具有风控考量的投资共识。

---

## 2. 整体技术架构（三层模型）

ALSA 采用现代全栈架构设计，分为三层，层层解耦：

```mermaid
graph TD
    User[用户访问: 浏览器 / CLI] --> Express[第一层：Node.js Express 网关 <br> Port: 3000]
    Express -- WebSocket / HTTP Proxy --> FastAPI[第二层：Python FastAPI 核心 <br> Port: 8001]
    
    subgraph Python Backend
        FastAPI --> JobService[任务管理器: job_service.py]
        JobService --> Snapshot[数据抓取: snapshot_service.py]
        JobService --> Quant[量化计算: polars_indicators.py]
        JobService --> Orchestrator[多专家编排: discussion_service.py]
        Orchestrator --> LLMGateway[LLM 网关: llm_gateway.py]
        Orchestrator --> BrainMgr[长期记忆: brain_manager.py]
        BrainMgr --> Qdrant[Qdrant 向量DB <br> Port: 6333]
        JobService --> ReportGen[研报渲染: report_generator_service.py]
    end
    
    subgraph 第三层：外部服务与数据引擎
        Snapshot --> DataSrc[行情源: AkShare / yfinance / Sina Finance]
        Quant --> DataLake[时序数据湖: Parquet + DuckDB]
        LLMGateway --> Models[大模型: Gemini 3.1 Pro / DeepSeek V4]
        Orchestrator --> Search[网络搜索: SearXNG / 同花顺问财]
    end
```

### 2.1 第一层：Node.js Express 网关 (端口 `3000`)
- **定位**：前端资源的托管者、API 网关与数据持久化层。
- **关键技术**：Express, Socket.io (WebSocket), http-proxy-middleware。
- **主要职责**：
  1. **托管前端**：在生产环境下托管 React (Vite) 静态资源；在开发环境下重定向到 Vite 调试服务器 (`5173`)。
  2. **WebSocket 实时推送**：由于 AI 讨论过程长达数分钟，网关通过 Socket.io 将每一轮专家的发言实时推送到前端，让用户看到“开会”的动态进展。
  3. **数据代理**：拦截 `/api/analysis/*` 等请求，并使用代理中间件转发至 Python 后端。
  4. **历史记录管理**：将分析结果以 JSON 文件持久化在本地 `data/history/` 下，保留 30 天，无需复杂的云数据库。

### 2.2 第二层：Python FastAPI 核心后端 (端口 `8001`)
- **定位**：量化计算引擎与多智能体（Agent）编排中心。
- **关键技术**：FastAPI, SQLModel (SQLite ORM), Polars, DuckDB。
- **主要职责**：
  1. **数据抓取**：通过 `AkShare` 模块抓取 A 股数据，通过 `yfinance` 抓取港美股数据。
  2. **时序处理**：利用高效的 **Polars** 计算 MA、RSI、MACD、布林带等量化指标。
  3. **任务调度**：`AnalysisJobService` 后台管理队列，控制任务以 "Fire and Forget" 模式异步执行，防止 HTTP 连接超时。
  4. **专家编排**：`DiscussionService` 驱动多专家多轮对话，处理 Prompt 注入、向量库检索（LanceDB）以及多模态工具调用。

### 2.3 第三层：数据引擎与外部服务
- **数据湖 (DuckDB + Parquet)**：时序行情数据以分区 Parquet 格式保存在磁盘上，使用 DuckDB 进行超快速的 SQL 查询。
- **LLM 智能体**：统一的 `llm_gateway.py`，支持 DeepSeek V4（原生 Function Calling，主力模型）和 Gemini 3.1（Google Search Grounding）。
- **向量记忆 (Qdrant)**：通过 Docker 运行的 Qdrant 实例提供 AI 长期记忆存储，支持多进程并发访问。
- **工具系统 (Expert Tools)**：24 个可调用工具（搜索、财务数据、问财查询、计算工具），AI 专家通过 Function Calling 自主决定何时使用哪些工具。

---

## 3. 核心机制：多专家共识辩论会议

ALSA 不会仅让一个 AI 一言堂。系统支持三种级别的讨论拓扑（Topology），代表了不同的研究深度。

### 3.1 深度研究拓扑（Deep Topology - 10 轮辩论）
如果选择深度分析（Deep 模式），后台将按照以下工序依次唤醒专家：

| 轮次 | 专家角色 (Expert Role) | 发言模式 | 核心任务 |
| :--- | :--- | :---: | :--- |
| **R1** | **Deep Research Specialist** | 串行 | 联网搜索行业最新新闻、重大事件，注入第一手客观事实。 |
| **R2** | **Chief Audit Officer** | 串行 | **审计官**紧跟数据层介入，核对事实准确性，防止后续专家基于错误数据建立空中楼阁。 |
| **R3** | **Technical Analyst** <br> **Fundamental Analyst** | 并行 | **技术派**看图表（量化指标 + Minervini 阶段分析）；<br>**基本面派**读财报（ROE、增长率），互不干扰，提供各自维度的原始论据。 |
| **R4** | **Sentiment Analyst** | 串行 | 分析市场情绪，抓取北向资金流向与论坛舆情，评估当下是恐慌还是贪婪。为多空辩论提供筹码。 |
| **R5** | **Bull Researcher** <br> **Bear Researcher** | 并行 | **多空对撞**。基于完整数据+情绪面的辩论矩阵。多方寻找买入逻辑；空方找潜在风险。 |
| **R6** | **Professional Reviewer** | 串行 | **专业评审员**检查多空辩论中是否存在"确认偏差"或"叙事过拟合"，进行逻辑纠偏。 |
| **R7** | **Soros-style Financial Philosopher** <br> **Value Investing Sage** | 并行 | 两位投资大师从各自哲学高度升华：索罗斯反身性思维 + 价值投资安全边际。 |
| **R8** | **Contrarian Strategist** | 串行 | **逆向策略师**跳出共识，专门寻找大众忽视的特立独行机会。 |
| **R9** | **Risk Manager** | 串行 | 风险量化：VaR、仓位管理、止损、相关性分析、尾部风险评估。 |
| **R10** | **Chief Strategist** | 串行 | **首席策略师**盖棺定论。综合所有辩论成果，输出包含“期望价格、合理买点、硬止损线、逻辑止损点、退出条件”的最终交易计划。 |

---

## 4. 源码目录与新手寻宝图

### 4.1 目录结构速览
```text
alsa/
├── 📄 server.ts               # Node.js 网关入口 (端口 3000)
├── 📂 server/                 # Express 路由、日志、健康检查
├── 📂 src/                    # 🖥️ 前端 React (19) 源码
│   ├── App.tsx                # 前端主入口
│   ├── components/            # UI 组件 (dashboard, analysis)
│   ├── hooks/                 # 核心 Hooks (useStockAnalysis, useDiscussion)
│   └── services/              # 前端服务 (gemini, socket 客户端)
├── 📂 python_service/         # 🐍 Python 核心后端
│   ├── main.py                # FastAPI 入口 (端口 8001)
│   ├── cli.py                 # 终端命令行入口
│   ├── app/
│   │   ├── api/               # 路由模块 (market, sector, analysis)
│   │   ├── services/          # ★ 核心业务服务 (讨论编排、数据采集、报告渲染)
│   │   ├── quant/             # Polars 量化指标计算
│   │   ├── db/                # SQLite 数据库模型 (SQLModel)
│   │   ├── lake/              # DuckDB + Parquet 数据湖
│   │   └── prompting/         # 50+ 个专家的 Prompt 模板与运行时管理
│   └── data/                  # 本地数据湖存储目录
└── 📂 docs/                   # 项目说明文档与 CLI 指南
```

### 4.2 小白快速修改定位指南

| 我想要修改... | 应该去改哪个文件？ |
| :--- | :--- |
| **HTML 报告的排版和 CSS 样式** | `python_service/app/services/report_generator_service.py` |
| **某位 AI 专家的提示词 (Prompt)** | `python_service/app/prompting/templates/` 目录下的 Markdown 模板 |
| **增减讨论会议的专家或修改轮次** | `python_service/app/services/discussion_service.py` 中的 `DEEP_TOPOLOGY` 等数组 |
| **修改选股（Screener）的财务过滤条件**| `python_service/app/services/screening_service.py` 中的 `SCREEN_PRESETS` |
| **调整前端 UI 某个卡片或走势图样式** | `src/components/analysis/` 下对应的 React 组件 |
| **修改默认使用的大模型 (Gemini ↔ DeepSeek)**| 修改根目录下的 `.env` 文件中的 `DEFAULT_LLM_PROVIDER` |
| **启用/禁用某个 AI 工具** | `python_service/app/services/tools_config.yaml` |
| **调整 AI 工具输出的 token 预算** | `python_service/app/services/token_guard.py` 中的 `LEVEL_CONFIGS` |

---

## 5. 小白极速上手安装与启动

请严格按照以下步骤在本地启动 ALSA：

### 步骤 1：准备环境
1. 安装 **Node.js** (推荐 v18 或 v20 以上)。
2. 安装 **Python** (推荐 3.10 或 3.11)。

### 步骤 2：下载并安装前端与网关依赖
在项目根目录下打开终端，运行：
```powershell
# 安装 Node 依赖
npm install
```

### 步骤 3：配置 API Key
在项目根目录下创建一个名为 `.env` 的文件，填入配置：
```env
GEMINI_API_KEY="你的_GEMINI_API_KEY"
DEFAULT_LLM_PROVIDER="gemini"
GEMINI_MODEL="gemini-3.1-pro-preview"

# ── Qdrant 向量数据库 (推荐) ──
# 多进程共享的向量记忆库，用于 AI 长期记忆
QDRANT_URL=http://localhost:6333

# ── 模型质量与废弃模型配置 (可选，有默认值) ──
# 逗号分隔的废弃模型列表（命中后自动回退默认模型）
# DEPRECATED_MODELS="gemini-1.5-pro"
# 逗号分隔的垃圾过滤关键词（LLM 输出前 200 字包含这些词时会重试）
# LLM_GARBAGE_KEYWORDS="h2020,erasmus,empowering women,stem education"
```
*(注：如果想用 DeepSeek，可以配置 `DEFAULT_LLM_PROVIDER="deepseek"`，并填写对应的 `DEEPSEEK_API_KEY`)*

### 步骤 4：启动 Qdrant 向量数据库
ALSA 使用 Qdrant 存储 AI 的长期记忆（向量数据库），通过 Docker 启动：
```bash
docker run -d --name qdrant-alsa \
  -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/data/brain/qdrant_storage:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant
```
验证服务是否正常：
```bash
curl http://localhost:6333/healthz
# 输出: healthz check passed
```
> 💡 如果没有 Docker，系统会自动降级为无向量记忆模式运行（不影响核心分析功能）。

### 步骤 5：配置并激活 Python 后端
1. 在根目录下创建一个虚拟环境：
   ```powershell
   python -m venv .venv
   ```
2. 激活虚拟环境：
   - **Windows (PowerShell)**: `.\.venv\Scripts\activate`
   - **macOS / Linux**: `source .venv/bin/activate`
3. 安装 Python 依赖：
   ```powershell
   # 确保处于激活状态，运行：
   pip install -r python_service/requirements.txt
   ```
   *(或者使用 `uv` 极速安装)*

### 步骤 6：启动服务
你需要启动两个后台服务（Qdrant 已在步骤 4 启动）：
1. **启动 Python 后端** (提供行情抓取与 AI 核心服务)：
   ```powershell
   npm run dev:py
   # 终端显示 Uvicorn running on http://127.0.0.1:8001 即成功
   ```
2. **启动 Node & React 网关** (提供用户访问界面)：
   ```powershell
   # 另开一个终端窗口，运行：
   npm run dev
   # 终端显示 Server running on http://localhost:3000 即成功
   ```

此时在浏览器中打开 **`http://localhost:3000`**，即可开始使用！

---

## 6. 使用命令行（CLI）直接生成研报

ALSA 提供了一个开箱即用的命令行工具。如果你不需要网页界面，只需在终端敲下一行命令，就能生成一份精美的静态 HTML 报告。

### 6.1 激活虚拟环境
确保你正处于 Python 虚拟环境下：
```powershell
.\.venv\Scripts\activate
```

### 6.2 初始化 API 密钥
```powershell
python python_service/cli.py config set gemini_api_key "你的密钥"
```

### 6.3 运行股票分析
输入你想分析的股票（支持拼音或中文模糊识别）：
```powershell
# 分析 贵州茅台，默认生成 HTML 报告在当前目录下
python python_service/cli.py analyze "贵州茅台"

# 分析美股特斯拉 (TSLA)，指定深度模式 (deep) 和输出路径
python python_service/cli.py analyze "TSLA" -l deep -o ./tesla_report.html
```

---

## 7. 核心技术原理简析 (适合进阶小白)

### 7.1 为什么用 Polars + DuckDB？
传统的 Python 数据分析通常用 `pandas`。但 `pandas` 在处理大规模时序行情（比如近十年的日K、分时数据）时内存占用高、速度慢。
- **Polars**：用 Rust 语言编写，底层基于 Apache Arrow。它采用多线程并发计算，性能是 pandas 的 5~10 倍，能够在毫秒级内完成数百只股票技术指标的重计算。
- **DuckDB**：一个专门用于分析的“SQL 关系型数据库”。它可以直接以 SQL 语法查询本地磁盘上的 `.parquet` 文件，而不需要将数据完全加载到内存，甚至不需要像 MySQL 那样安装数据库服务。非常适合本地“零配置”数据湖开发。

### 7.2 怎么预防 AI 在金融分析中“胡言乱语 (幻觉)”？
金融研究是一项非常严谨的工作，AI 编造一个虚假的市盈率（PE）或财报数字是不可接受的。ALSA 采取了多重保障：
1. **首轮硬事实注入**：在 AI 辩论的第一轮，`Deep Research Specialist` 会直接拉取 API 提供的确定性财报数据，将其作为系统提示词（System Prompt）牢牢锁死在上下文的最上方。
2. **三轮硬伤审计（CAO 审计官）**：第三轮的 `Chief Audit Officer`（首席审计官）是专门被赋予“挑刺”任务的 AI。它不负责给出股票评级，只负责逐字检查前面几位专家说的数据是否跟第一轮 API 抓取的数据一致。一旦发现不一致，立即在上下文中打回修正。
3. **优先级排序机制 (Priority)**：系统在 Prompt 中强制注入约定——“API 提供的实时快照是最高真理，网络搜索数据是二级参考，你的历史记忆排在最末位。三者冲突时，必须采信 API 快照”。
---

## 8. 机构级风控与运维模块 (Institutional Modules)

> 2025 年新增。这些模块为 ALSA 补齐了从「研究工具」到「准生产交易辅助系统」的关键基础设施。

### 8.1 模块总览

```text
python_service/app/
├── risk/                  # 风险控制
│   ├── pre_trade.py       # 盘前风控网关（单票集中度 / 日内新增暴露 / 仓位上限）
│   └── kill_switch.py     # 紧急熔断开关（8 种触发器 + 分级降级）
├── decision/              # 决策治理
│   ├── court.py           # 证据法庭 — 多 Agent 证据仲裁
│   ├── trading_fields_validator.py  # 交易字段正则校验（价格 / 仓位 / 评分）
│   └── schemas.py         # AgentDecisionOutput / AgentClaim / ConflictLevel
├── backtest/              # 事件驱动回测
│   ├── engine.py          # 回测引擎（组合账本 / 逐日盯市 / 绩效指标）
│   ├── costs.py           # A 股成本模型（佣金 / 印花税 / 滑点）
│   └── simulator.py       # 成交模拟器（涨跌停拒绝 / 停牌处理）
├── observability/         # 可观测性
│   ├── metrics.py         # 内存指标收集器（带标签 / 统计 / 速率）
│   └── audit.py           # 审计日志（10 类动作 / 自动轮转）
├── prompting/
│   └── version_registry.py # PromptOps 版本治理（金丝雀 / 灰度 / 废弃生命周期）
├── evaluation/
│   └── model_eval.py      # 模型评估框架（golden / regression / adversarial 套件）
└── reconciliation/
    └── engine.py          # 每日对账引擎（持仓匹配 + 现金容差）
```

### 8.2 API 端点 (路由前缀 `/api/institutional/`)

| 方法 | 路径 | 用途 |
|:---|:---|:---|
| GET | `/kill-switch` | 查看熔断开关状态 |
| POST | `/kill-switch/trigger` | 手动触发熔断（body: `{trigger, reason}`) |
| POST | `/kill-switch/reset` | 重置熔断（需 `approval_id`） |
| POST | `/risk/pre-trade-check` | 提交盘前风控校验请求 |
| GET | `/metrics/summary` | 获取系统指标摘要（延迟 / 计数 / 速率） |
| GET | `/audit/recent?limit=50` | 获取最近审计日志 |

### 8.3 HTTP 中间件

所有 API 请求自动被 `record_api_metrics` 中间件拦截，记录：
- 请求耗时 (ms)
- 请求方法 / 路径 / 状态码

数据流向 `MetricsCollector` 单例，可通过 `/api/institutional/metrics/summary` 查询。

### 8.4 集成点

| 模块 | 接入位置 | 说明 |
|:---|:---|:---|
| `TradingFieldsValidator` | `analysis_job_service.py` | 分析任务完成后自动校验交易计划字段 |
| `MetricsCollector` | `main.py` 中间件 | 全局 API 延迟采集 |
| `KillSwitch` | `main.py` 单例 + API | 供前端/运维触发紧急熔断 |
| `PreTradeRiskGateway` | `main.py` 单例 + API | 交易前风控校验 |
| `AuditLogger` | `main.py` 单例 + API | 操作审计日志 |
| `PromptVersionRegistry` | `main.py` 单例 | Prompt 版本治理 |

### 8.5 测试覆盖

共 84 个单元测试，覆盖所有新增模块：
```bash
cd /home/zily/alsa
rm -f python_service/data/test_app.db
.venv/bin/python -m pytest python_service/tests/test_pre_trade_risk.py \
  python_service/tests/test_kill_switch.py \
  python_service/tests/test_prompt_ops.py \
  python_service/tests/test_decision_court.py \
  python_service/tests/test_backtest_engine.py \
  python_service/tests/test_observability.py \
  python_service/tests/test_reconciliation.py \
  python_service/tests/test_model_eval.py -q
```