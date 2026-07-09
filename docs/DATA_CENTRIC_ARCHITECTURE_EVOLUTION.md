# ALSA 架构演进：从「上下文累积」到 Data-Centric 多智能体系统

> 版本：v2.0 · 2026-07-09
> 基于代码库 full diff 分析，覆盖 30 个源文件、8447 行核心服务代码。

---

## 0. TL;DR（结论先行）

**根因**：当前 native tool loop 把每一轮的完整工具结果不断 append 进 `messages`，
每次调用都把全部历史重发给 LLM。上下文随轮次线性膨胀（实测单个 quick 任务
prompt 从 7k → 40k+ chars），直接导致单次 DeepSeek 调用 400–500s，一个 quick
任务被拖到 28–30 分钟。

**方向**：不是继续在"对话历史"里打补丁，而是转向 **Data-Centric** 架构——
数据是一等资产，LLM 只做推理；上下文由 **Context Builder 主动构建最小高价值集合**，
而不是被动累积。

**Phase 0 已完成的止血**：
- Tool 结果外置存储 + 摘要压缩 + 近轮全文 + `recall_tool_result` 按需回调
- 查询去重缓存（批内 + 跨轮）+ 市场上下文注入
- 失败快速退出（确定性错误不重试 + 3 轮全失败早停）
- DataRouter akshare-fallback 熔断器 + 质量评分体系 + provider_policies.yaml
- 故障快照系统（failure_capture + IncidentConsole + Admin API）
- `reasoning_content` 回传修复 + LLM 轮超时 360s→150s
- 分析任务序列化安全（config/result_payload 自动清洗）
- A股直连数据源（EastMoney balance/income/dividends 替代 AkShare）
- 日志文件轮转 + 结构化日志

**本文目标**：把这些点状修复收敛成一套**分层架构**，识别当前实现与目标架构的
不兼容点和需调整项，给出精确的落地路线。

---

## 1. 现状诊断（v2.0 实测数据）

### 1.1 当前调用链

```
analysis_job_service._run_job()
    │
    ├─ Step 0: API Key 获取/验证 (llm_gateway.validate_api_key)
    ├─ Step 1: Market Snapshot (market_snapshot_service)
    ├─ Step 2: Quantitative Indicators (polars_indicators)
    ├─ Step 3: Expert Discussion
    │    │
    │    ▼
    │  discussion_service.run_discussion()      ← LangGraph 多专家状态机
    │    │  build_topology(level)                ← 固定拓扑：QUICK/STANDARD/DEEP
    │    │  每个专家节点 make_node()
    │    ▼
    │  _call_expert() → _assemble_prompt()      ← 拼装 snapshot + history + tools
    │    │
    │    ▼
    │  agent_orchestrator.generate_with_native_tools()
    │    │  for round in range(max_tool_rounds):    ← ★ 核心循环
    │    │     messages.append(assistant + tool_results)
    │    │     [工具结果外置 + 摘要压缩 + recall]     ← Phase 0 止血
    │    │     llm_gateway.generate_content(messages)
    │    ▼
    │  llm_gateway → DeepSeek/Gemini API
    │
    ├─ Step 3b: Critic Agent (可选)
    ├─ Step 4: Final Payload Assembly
    ├─ Step 5: DB Persistence
    └─ Error: capture_failure_incident → 写入磁盘快照
```

### 1.2 Phase 0 止血效果量化

| 指标 | 止血前 | 止血后 | 变化 |
|---|---|---|---|
| 单次 prompt 上下文 | 无界增长 (40k+ chars) | 有上界 (近2轮全文 + 旧轮摘要) | ↓ ~60% 峰值 |
| 工具重复请求 | 每轮重复调用相同工具 | 会话级去重缓存 | ↓ ~30% 调用量 |
| 工具失败处理 | 无限重试至超时 | 3轮全失败早停 + 快速退出 | ↓ 等待时间 |
| AkShare 故障影响 | 每次调用都触发超时 | 熔断器 (3次失败→120s冷却) | ↓ 日志噪声 |
| LLM 轮超时 | 360s (6分钟) | 150s (可配) | ↓ 卡死风险 |
| 序列化崩溃 | DataFrame/Series 导致 DB 写入失败 | 自动清洗非JSON类型 | 消除崩溃 |
| 故障诊断 | 仅日志，需 SSH 查看 | 前端一键查看故障快照 | ↓ MTTR |

### 1.3 关键文件规模与复杂度

| 文件 | 行数 | 职责 | 复杂度评估 |
|---|---|---|---|
| `expert_tools.py` | 1952 | 28个工具定义+执行+缓存 | 🔴 远超250行限制 |
| `market_data_service.py` | 1274 | 行情/财务/历史数据聚合 | 🔴 远超250行限制 |
| `discussion_service.py` | 1133 | LangGraph拓扑+专家执行+prompt组装 | 🔴 远超250行限制 |
| `agent_orchestrator.py` | 1131 | Tool loop+上下文压缩+recall | 🔴 远超250行限制 |
| `analysis_job_service.py` | 978 | 任务生命周期+失败处理+序列化 | 🔴 远超250行限制 |
| `llm_gateway.py` | 820 | 多Provider路由+重试+限流+缓存 | 🔴 远超250行限制 |
| `router.py` | 739 | 数据路由+熔断+质量评分+策略 | 🟡 接近上限 |
| `failure_capture.py` | 420 | 故障快照捕获+查询 | 🟡 偏大 |

---

## 2. 目标架构分层

```
User
 │
 ▼
┌──────────────── Request Layer ────────────────┐
│  Symbol Resolve · Intent Parse · 参数/时间/市场 │  ← 尽量不用大模型
└────────────────────────────────────────────────┘
 │
 ▼
┌──────────────── Planning Layer ───────────────┐
│  Planner(Flash) → Execution Plan (DAG)         │  ← 决定取哪些数据/哪些 Agent/是否并行
└────────────────────────────────────────────────┘
 │
 ▼
┌──────────────── Execution Layer ──────────────┐
│  DAG Engine：Parallel / Conditional / Retry     │
│    ├─ Data Route（统一供数，snapshot 优先 + tools 兜底）│
│    ├─ Multi-Agent（6–8 个专业 Agent）            │
│    └─ Memory / RAG（按需检索）                   │
└────────────────────────────────────────────────┘
 │
 ▼
┌──────────────── Reasoning Layer ──────────────┐
│  Agent(Pro)：输入 = Question + Context + Role   │
│  输出 = 结构化 {summary, score, confidence,     │
│          evidence[], risk[]}                    │
└────────────────────────────────────────────────┘
 │
 ▼
┌──────────────── Evidence Layer ───────────────┐
│  Evidence Aggregator → 可解释/可验证/可追溯      │
└────────────────────────────────────────────────┘
 │
 ▼
┌──────────────── Presentation Layer ───────────┐
│  Investment Report                              │
└────────────────────────────────────────────────┘
```

---

## 3. 当前实现与目标架构的不兼容点

### 3.1 🔴 Context 仍被动累积（未根本解决）

**现状**：`agent_orchestrator.py:430-445` 的 tool loop 仍然向 `messages` 列表不断 append assistant 和 tool 消息。Phase 0 的摘要压缩只是在旧轮上做了"截断+摘要"，但：

- **每轮仍发送全部 messages 给 LLM**（line 557: `await llm_gateway.generate_content(current_prompt, ...)` 其中 `current_prompt` 是拼接后的全部 messages）
- `KEEP_RECENT_ROUNDS=2` 意味着近 2 轮仍全量保留，加上 system prompt + 工具定义，base context 约 8-12k tokens
- 30 轮 tool loop 中，即使旧轮被压缩，累积的 assistant + tool 消息仍在 `messages` 列表中占位
- **`_summarize_tool_result` 只压缩 tool 消息**（line 769-776），assistant 消息（含 reasoning_content）不压缩

**目标**：Context Builder 主动构建最小集合，每轮 prompt 规模恒定上界。

**需调整**：
1. 将 tool loop 的 `messages` 从"完整历史"改为"滑动窗口 + 外置存储"
2. assistant 消息也需要摘要机制（当前只处理 tool 消息）
3. Context Builder 应作为独立组件，而非嵌入 tool loop

### 3.2 🔴 Agent 联网工具未收口（重复请求 + 上下文膨胀）

**现状**：`expert_tools.py` 中的 ToolExecutor 允许 LLM 通过 28 个工具直接联网：

- `web_search` → iwencai API（line 1304: `httpx.AsyncClient(timeout=15.0)`）
- `news_search` → iwencai news API
- `deep_scrape` → crawl4ai（line 1468: `page_timeout=15000`）
- `financial_data` → AkShare + yfinance（line 1579+）
- `macro_query` / `business_query` / `finance_query` → iwencai query2data API

虽然 `data_providers/router.py` 已经是"统一供数入口"，但 **tool loop 中的 LLM 仍然可以通过 web_search/news_search/deep_scrape 等工具绕过 Data Route 直接联网**。

**问题**：
- 没有 Planner 预取 → Agent 在 tool loop 中即兴决定查什么，每轮都可能重新请求相同数据
- 每个 Agent 独立联网 → 重复请求、不一致数据、上下文膨胀
- iwencai API 有频率限制，多 Agent 并发调用容易触发
- snapshot 数据不全时 Agent 仍需联网，但缺乏"先查 snapshot、再查网络"的优先级机制

**目标**：Planner 预取常用数据写入 snapshot → Agent 优先从 snapshot 读取 → snapshot 缺失时 tools 兜底。

**需调整**：
1. 新增 Planner 预取阶段，在执行前通过 Data Route 获取 quote/history/financial 等常用数据写入 snapshot
2. Agent 的 `financial_data` 工具应优先从 snapshot 读取，仅在 snapshot 缺失时降级到 DataRouter/AkShare
3. `web_search`/`news_search` 保留作为 Agent 的兜底能力（snapshot 不覆盖新闻/公告等非结构化数据）
4. `deep_scrape` 保留但降级为 emergency fallback（仅在 web_search 也无法满足时使用）

### 3.3 🔴 固定拓扑 vs 动态 DAG

**现状**：`discussion_service.py` 使用 LangGraph 但拓扑是**硬编码**的：

```python
QUICK_TOPOLOGY = [
    {"round": 1, "experts": [{"role": "Deep Research Specialist"}]},
    {"round": 2, "experts": [{"role": "Technical Analyst"}, {"role": "Fundamental Analyst"}]},
    {"round": 3, "experts": [{"role": "Professional Reviewer"}]},
    {"round": 4, "experts": [{"role": "Chief Strategist"}]},
]
```

5 种固定拓扑（DEEP/STANDARD/QUICK/SECTOR/SERENITY_ALPHA），根据 `level` 参数选择。

**问题**：
- 无论股票特征如何，都走相同路径（A股科技股和港股金融股用同一拓扑）
- 无法根据数据可用性动态跳过不需要的专家
- 代码中定义了条件路由逻辑（line 426-443: 检查 `数据严重不足`/`CRITICAL_DATA_MISSING`），但 **未接入 LangGraph 的 `add_conditional_edge`**（line 448 仍用 `add_edge`）
- 无法并行执行不相关的专家

**目标**：Planner 根据股票特征 + 数据可用性动态生成 DAG。

**需调整**：
1. 将条件路由逻辑接入 LangGraph（当前是死代码）
2. Planner 输出执行计划，discussion_service 按计划构建图
3. 支持真正的并行执行（当前 `parallel: true` 只是语法糖）

### 3.4 🟡 无角色→模型路由（全程 Pro 级）

**现状**：`llm_gateway.py` 的路由逻辑是**按模型名前缀**分发：

```python
if model.lower().startswith("gemini"):
    providers = [("gemini", ...), ("default", ...)]
else:
    providers = [("deepseek", ...), ("default", ...), ("gemini", ...)]
```

- 没有 role→model 映射
- 全程使用 `DEFAULT_LLM_MODEL`（默认 `deepseek-v4-pro`）
- Planner/工具选择/摘要/上下文压缩 等轻量任务也用 Pro 级模型

**目标**：Flash 做整理，Pro 做推理。

**需调整**：
1. 在 `llm_gateway` 中增加 `role→model` 映射表
2. Planner/工具选择/摘要/上下文压缩 用 Flash
3. Agent 推理/自检/报告 用 Pro

### 3.5 🟡 结构化输出未强制

**现状**：`discussion_service.py:373-376` 将专家输出截断到 2000 字符：

```python
if len(content) > 2000:
    content = content[:2000] + "\n...[truncated]"
```

- 专家输出是**自由文本**，不是结构化 JSON
- `ExpertDiscussionResult` Pydantic schema 只对非 final、非 intermediate 专家强制（line 798）
- 下游 Evidence Aggregator 无法解析非结构化文本

**目标**：Agent 输出 `{summary, score, confidence, evidence[], risk[]}`。

**需调整**：
1. 所有 Agent 统一输出结构化 JSON
2. 移除 2000 字符截断（结构化输出天然紧凑）
3. Evidence 从 Agent 输出中提取，不需要额外解析

### 3.6 🟡 Memory 未分层

**现状**：
- `brain_manager.py`（371行）管理"基因组"和跨会话记忆
- `agent_memory.py` 管理 Agent 个人记忆
- Redis 存储 `analysis_progress:*`（24h TTL）
- 但 **Session 级记忆仍依赖 `messages` 列表**（tool loop 的 messages）

**问题**：
- Session 记忆与 tool loop 的 messages 耦合
- 无法区分"本次分析进度"和"历史分析结论"
- Agent 跨任务学习依赖 `brain_manager`，但更新不及时

**目标**：Session/Analysis/Project/User 四层记忆分离。

### 3.7 🟡 无 Evidence Layer

**现状**：
- `grounding_verifier.py` 做事实核验
- `output_validator.py` 做输出校验
- 但没有统一的 Evidence Store

**问题**：
- 每个 Agent 独立产出结论，无法追溯到具体数据源
- 报告生成时无法引用"第3轮技术分析师引用了XX数据"
- 无法做跨 Agent 证据一致性检查

### 3.8 🟡 超大文件需要拆分

**现状**：8 个核心服务文件总计 8447 行，远超项目 250 行限制：

| 文件 | 当前行数 | 建议拆分为 |
|---|---|---|
| `expert_tools.py` (1952) | 工具定义 + 执行 + 缓存 + 财务数据 | `tool_definitions.py` + `tool_executor.py` + `tool_cache.py` + `financial_tools.py` |
| `market_data_service.py` (1274) | 行情 + 财务 + 历史 + 解析 | `quote_service.py` + `financial_service.py` + `history_service.py` + `symbol_resolver.py` |
| `discussion_service.py` (1133) | 拓扑 + 执行 + prompt组装 + 验证 | `topology.py` + `expert_runner.py` + `prompt_assembler.py` + `batch_verifier.py` |
| `agent_orchestrator.py` (1131) | Tool loop + 压缩 + recall + 心跳 | `tool_loop.py` + `context_compressor.py` + `recall_handler.py` |
| `analysis_job_service.py` (978) | 生命周期 + API Key + 序列化 + 部分结果 | `job_lifecycle.py` + `api_key_manager.py` + `result_serializer.py` |
| `llm_gateway.py` (820) | 多Provider + 重试 + 限流 + 缓存 | `provider_chain.py` + `rate_limiter.py` + `response_cache.py` + `quality_gate.py` |

---

## 4. 组件级设计与代码落点

### 4.1 Context Builder（最关键组件 — 未实现）

**唯一目标**：决定"哪些数据进入 Prompt"，绝不发送 raw data。

```python
# 新增 python_service/app/services/context_builder.py
class ContextBuilder:
    """把原始数据压成最小高价值上下文。Never send raw data."""

    def build(self, question, snapshot, evidence_store, memory, budget_tokens):
        return {
            "question": question,
            "market_summary": self._summarize_market(snapshot),   # 3000根K线 → 趋势/MA/MACD/RSI/ATR
            "fundamentals": self._key_tables(snapshot),           # 200页财报 → Summary + Key Tables
            "news": self._top_n_news(snapshot, n=5),              # 100条 → Top5
            "retrieved": self._rag_retrieve(question, k=8),       # PDF → 相关 chunks
            "recent_context": memory.session.tail(5),             # 最近5轮，不无限增长
            "evidence": evidence_store.relevant(question),        # 已验证证据
        }
```

**关键转换规则**：

| 原始 | 进入 Prompt 的形态 | 现有基础 |
|---|---|---|
| 3000 根 K 线 | 趋势 + MA排列 + MACD + RSI + ATR | `quant/polars_indicators.py` ✅ |
| 100 条新闻 | Top5（按相关性/时间打分） | 需新增 |
| 200 页财报 | Summary + Key Tables（RAG chunk） | 需新增 |
| 全部工具历史 | 近 2 轮全文 + 旧轮摘要 + ref 指针 | `agent_orchestrator.py` ✅ 已部分实现 |

**与现有实现的衔接**：
- `agent_orchestrator.py:769-776` 的 `_summarize_tool_result` 是 Context Builder 摘要能力的雏形
- 但它是嵌入在 tool loop 内部的，需要上提为独立组件
- `recall_tool_result` (line 697-702) 是 RAG 按需检索的雏形

### 4.2 Data Route 收口（部分实现）

**现状**：`data_providers/router.py` (739行) 已具备：
- ✅ 多 Provider 并发竞速 + 质量评分
- ✅ 熔断器 (akshare-fallback)
- ✅ provider_policies.yaml 热加载
- ✅ 运行时统计 + 缓存 TTL
- ✅ `get_quotes_with_meta` / `get_history_with_meta` 带路由元数据

**未完成的收口**：
- ❌ Agent/tool 层仍可绕过 Data Route 直接联网
- ❌ Planner 未通过 Data Route 预取数据
- ❌ `expert_tools.py:1579+` 的 `financial_data` 工具仍直接调用 AkShare/yfinance

**需调整**：
1. `ToolExecutor._exec_financial_data()` 应优先从 DataRouter 获取，仅在 DataRouter 失败时降级
2. 禁用 `web_search`/`news_search`/`deep_scrape` 在 tool loop 中的使用（改为 Planner 预取）
3. DataRouter 应支持批量预取接口（一次调用获取 quote + history + financial）

### 4.3 Multi-Agent 结构化输出（部分实现）

**现状**：
- 5 种固定拓扑（QUICK 4轮 / STANDARD 6轮 / DEEP 10轮 / SECTOR 5轮 / ALPHA 1轮）
- `ExpertDiscussionResult` Pydantic schema 存在但只对部分专家强制
- 专家输出截断到 2000 字符
- `batch_verify_and_reflect` 做批量验证

**需调整**：
1. 所有 Agent 统一输出 `{summary, score, confidence, evidence[], risk[]}`
2. 移除 2000 字符截断（结构化输出天然紧凑，通常 < 500 tokens）
3. 从结构化输出中自动提取 Evidence

### 4.4 Evidence Layer（未实现）

**新增** `evidence_store.py`：

```python
@dataclass
class Evidence:
    claim: str
    confidence: float
    source: list[str]        # 数据/文档来源，可追溯
    agent: str
    created_at: datetime

class EvidenceStore:
    def add(self, ev: Evidence): ...
    def relevant(self, question) -> list[Evidence]: ...   # 供 Context Builder 回填
    def aggregate(self) -> FinalReport: ...               # 汇总成报告
```

复用现有 `grounding_verifier.py` 为 Evidence 打 confidence。

### 4.5 Model 分层路由（未实现）

```python
# llm_gateway.py 增加 role → model 映射
MODEL_TIER = {
    "planner":   "deepseek-v4-flash",   # 规划
    "tool_router":"deepseek-v4-flash",  # 工具选择
    "summarizer":"deepseek-v4-flash",   # 摘要
    "context":   "deepseek-v4-flash",   # 上下文压缩
    "agent":     "deepseek-v4-pro",     # 深度分析
    "reflection":"deepseek-v4-pro",     # 自检
    "report":    "deepseek-v4-pro",     # 报告
}
```

当前 `llm_gateway.py` 的路由仅按模型名前缀分发，需要增加 role 维度。

### 4.6 Memory 四层（部分实现）

| 层 | 存储 | 生命周期 | 现有基础 | 差距 |
|---|---|---|---|---|
| Session | 最近 5–10 轮 | 单次会话 | `messages` 尾窗 + tool loop 摘要 | 与 tool loop 耦合，需解耦 |
| Analysis | 本次分析进度 | 单任务 | Redis `analysis_progress:*` + `failure_capture` | 已实现 ✅ |
| Project | 股票池/自定义指标 | 跨任务 | `brain_manager.py` | 更新不及时 |
| User | 偏好/风险/风格 | 永久 | `agent_memory` + DB | 需要更结构化的存储 |

---

## 5. 不兼容点优先级矩阵

| # | 不兼容点 | 影响 | 实现难度 | 优先级 |
|---|---|---|---|---|
| 1 | Context 仍被动累积 | 性能瓶颈根因 | 高 | 🔴 P0 |
| 2 | Agent 直接联网 | 数据不一致+重复请求 | 中 | 🔴 P0 |
| 3 | 固定拓扑 vs 动态 DAG | 分析质量受限 | 高 | 🟡 P1 |
| 4 | 无角色→模型路由 | 成本浪费 | 低 | 🟡 P1 |
| 5 | 结构化输出未强制 | 下游可追溯性差 | 中 | 🟡 P1 |
| 6 | Memory 未分层 | 跨任务学习受限 | 中 | 🟢 P2 |
| 7 | 无 Evidence Layer | 可解释性差 | 中 | 🟢 P2 |
| 8 | 超大文件需拆分 | 可维护性 | 高 | 🟢 P2 |

---

## 6. 分阶段落地路线

### Phase 0 — 止血（✅ 已完成）

**改动清单**：

| 改动 | 文件 | 效果 |
|---|---|---|
| Tool 结果外置存储 + 摘要压缩 | `agent_orchestrator.py:375-420` | 近轮全文 + 旧轮摘要 |
| `recall_tool_result` 按需回调 | `agent_orchestrator.py:697-702` | 按需恢复完整结果 |
| 查询去重缓存 | `expert_tools.py:783-830` | 同Job内相同参数复用 |
| 市场上下文注入 | `expert_tools.py:845-870` | tool结果带市场元数据 |
| 失败快速退出 | `agent_orchestrator.py:191-205` | 3轮全失败强制完成 |
| 熔断器 | `router.py:108-135` | AkShare 3次失败→120s冷却 |
| 质量评分体系 | `base.py:176-235` + `router.py` | quote/history/financial 评分 |
| provider_policies.yaml | `data_providers/provider_policies.yaml` | 可配置策略 |
| 故障快照 | `failure_capture.py` + `IncidentConsole.tsx` | 前端一键查看 |
| A股直连数据源 | `a_stock_direct.py:198-355` | EastMoney替代AkShare |
| 序列化安全 | `analysis_job_service.py:35-107` | config/result自动清洗 |
| LLM轮超时 | `agent_orchestrator.py:557` | 360s→150s可配 |
| reasoning_content回传 | `agent_orchestrator.py:673-678` | DeepSeek v4兼容 |
| 日志文件轮转 | `logging.py:89-100` | RotatingFileHandler |

### Phase 1 — Context Builder + Data Route 收口（1–2 周）

**目标**：quick 任务单次 prompt ≤ 12k tokens，端到端 ≤ 8 分钟。

- [ ] 新增 `context_builder.py`，把 `_assemble_prompt` 改为"构建最小上下文"
  - 复用 `polars_indicators` 做 K 线→指标摘要
  - 新闻→Top-N（按相关性/时间打分）
  - 财报→Key Tables（结构化摘要）
- [ ] Agent/tool 数据获取优先级改造
  - `ToolExecutor._exec_financial_data()` 改为优先从 snapshot/DataRouter 获取，仅在缺失时降级到 AkShare/yfinance
  - `web_search`/`news_search` 保留作为 Agent 的兜底能力（snapshot 不覆盖非结构化数据）
  - `deep_scrape` 保留但降级为 emergency fallback
- [ ] 新增 Planner 预取阶段（Phase 2 实现，此处先定义接口）
- [ ] **验收**：quick 任务单次 prompt ≤ 12k tokens，端到端 ≤ 8 分钟

### Phase 2 — Planner + 结构化 Agent（2–3 周）

**目标**：Agent 间传递体积下降 >70%，可并行执行。

- [ ] 新增 `planner_service.py`（Flash 出 DAG plan：取数清单 + Agent 编排）
  - 根据股票特征 + 数据可用性动态生成执行计划
  - 接入 LangGraph 条件路由（当前是死代码）
- [ ] Planner **预取**数据写入 snapshot；Agent 只读 snapshot
- [ ] Agent 输出改结构化 `{summary, score, confidence, evidence[], risk[]}`
  - 移除 2000 字符截断
  - 强制所有专家输出 Pydantic schema
- [ ] **验收**：Agent 间传递体积下降 >70%，可并行执行

### Phase 3 — Evidence Layer + Model 分层（2 周）

**目标**：报告每条结论可追溯到 source；Token 成本下降 >50%。

- [ ] 新增 `evidence_store.py` + Aggregator，报告由 Evidence 汇总生成
  - 复用 `grounding_verifier` 给 Evidence 打分
- [ ] `llm_gateway` 增加 role→model 路由（Flash/Pro）
  - Planner/工具选择/摘要/上下文压缩 → Flash
  - Agent 推理/自检/报告 → Pro
- [ ] **验收**：报告每条结论可追溯到 source；Token 成本下降 >50%

### Phase 4 — RAG + Memory 四层（3–4 周）

**目标**：支持数百 MB 文档分析；Session 永不无限增长。

- [ ] 文档（财报/研报/公告）chunk + 向量化（LanceDB）
  - 复用现有 `vector/` 目录的 LanceDB 基础设施
- [ ] Retriever 按需 Top-K，替代"整份 PDF 入 prompt"
- [ ] Memory 拆 Session/Analysis/Project/User，Session 严格窗口化
- [ ] **验收**：支持数百 MB 文档分析；Session 永不无限增长

### Phase 5 — DAG Engine 正式化 + 文件拆分（可选，2–3 周）

- [ ] 用 LangGraph 把"固定拓扑"升级为"Planner 驱动的动态 DAG"
  - 支持 Parallel / Conditional / Retry / Loop / Human Review
  - 支持长时任务断点续跑（依赖 Analysis Memory）
- [ ] 超大文件拆分（expert_tools → 4文件, discussion_service → 4文件, 等）
- [ ] **验收**：每个文件 ≤ 250 行；动态 DAG 可运行

---

## 7. 核心设计原则（落地对照）

| # | 原则 | 本仓库落地点 | 现状 |
|---|---|---|---|
| 1 | Snapshot 优先，tools 兜底 | Planner 预取 → snapshot；Agent 先读 snapshot，缺失时 tools 兜底 | ⚠️ 无预取，Agent 直接联网 |
| 2 | 数据统一经 Data Route | `data_providers/router.py` 收口 | ⚠️ 已实现但未强制 |
| 3 | Planner 决定计划，非 LLM 即兴 | 新增 `planner_service.py` | ❌ 未实现 |
| 4 | DAG 工作流，支持并行/分支 | `discussion_service` → 动态 DAG | ⚠️ 固定拓扑，条件路由是死代码 |
| 5 | Context Builder 构建最小高价值上下文 | 新增 `context_builder.py` | ⚠️ tool loop 内有雏形但未独立 |
| 6 | Memory 与 Session 分离 | Memory 四层，Session 窗口化 | ⚠️ 部分实现 |
| 7 | Evidence First | 新增 `evidence_store.py` | ❌ 未实现 |
| 8 | Flash 整理 / Pro 推理 | `llm_gateway` role→model 路由 | ❌ 全程 Pro |
| 9 | RAG 按需检索 | LanceDB + Retriever | ⚠️ 有基础设施但未集成 |
| 10 | Data-Centric | 全链路以数据为核心资产 | ⚠️ 方向正确但未收口 |

---

## 8. 预期收益

| 指标 | 现状（Phase 0 后） | 目标（Phase 3 后） | 目标（Phase 5 后） |
|---|---|---|---|
| quick 任务耗时 | 15–20 分钟 | ≤ 5 分钟 | ≤ 3 分钟 |
| 单次 prompt 规模 | ~15k tokens（有上界） | ≤ 12k tokens（恒定） | ≤ 8k tokens |
| Token 成本 | 单任务 ~400k input | 下降 >50% | 下降 >70% |
| 可解释性 | 长文，部分可追溯 | 每条结论关联 source | 完整 Evidence 链 |
| 可扩展性 | 单机对话历史 | 数百 MB 数据 + 长时任务 | 动态 DAG + 断点续跑 |
| Agent 间传递体积 | 全文截断 2000 字 | 结构化摘要 <500 tokens | Evidence 指针 |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 重构范围大 | 分 5 阶段，每阶段独立可上线/回滚 |
| Context Builder 摘要漏关键数据 | `recall_tool_result` 按需回全文；Evidence 保留 source |
| Planner 规划错误 | Flash 出 plan + 规则校验兜底；保留人工 Review 节点 |
| RAG 检索不准 | Top-K + rerank；关键财务数据仍走结构化 Data Route |
| 多模型切换兼容 | `llm_gateway` 统一抽象，已支持 DeepSeek/Gemini |
| Agent 联网工具影响性能 | Planner 预取覆盖常用数据（quote/history/financial），减少 70%+ 工具调用；保留 web_search/news_search 作为兜底 |
| 文件拆分引入回归 | 拆分后立即跑 pytest，CI 覆盖 |

---

## 附录 A：Phase 0 改动与目标架构的衔接

Phase 0 的改动已经是本架构的"局部实现"：

| Phase 0 改动 | 目标架构组件 | 当前状态 |
|---|---|---|
| `tool_result_store` (agent_orchestrator) | Analysis Memory / 外置存储 | ✅ 已实现，但嵌入 tool loop |
| `_summarize_tool_result()` | Context Builder 摘要 | ⚠️ 雏形，只处理 tool 消息 |
| `recall_tool_result` | RAG 按需检索 | ✅ 已实现 |
| `expert_tools._result_cache` | Data Route Cache | ✅ 已实现 |
| `router.py` 熔断器 | Data Route Failover | ✅ 已实现 |
| `provider_policies.yaml` | Data Route 策略配置 | ✅ 已实现 |
| `failure_capture.py` | Observability | ✅ 已实现 |
| `IncidentConsole.tsx` | 前端诊断 | ✅ 已实现 |
| `a_stock_direct.py` 直连 | Data Route 收口 | ✅ 已实现 |
| `_sanitize_result_payload` | 序列化安全 | ✅ 已实现 |
| `_inject_market_context` | 数据质量标注 | ✅ 已实现 |

后续阶段是把这些"雏形"从 tool loop 内部**上提为独立分层组件**，形成统一架构。

---

## 附录 B：环境变量清单（Phase 0 新增）

| 变量 | 默认值 | 作用 |
|---|---|---|
| `TOOLLOOP_KEEP_RECENT_ROUNDS` | `2` | 保留全文的最近轮数 |
| `TOOLLOOP_SUMMARY_CHARS` | `600` | 旧轮摘要字符上限 |
| `TOOLLOOP_FINAL_TOOL_BUDGET` | `30000` | 最终轮工具结果总预算 |
| `LLM_ROUND_TIMEOUT` | `150` | 单轮 LLM 调用超时(秒) |
| `AKSHARE_CB_THRESHOLD` | `3` | AkShare 熔断阈值 |
| `AKSHARE_CB_COOLDOWN` | `120` | AkShare 熔断冷却(秒) |
| `ALSA_FILE_LOG_ENABLED` | `true` | 是否启用文件日志 |
| `ALSA_LOG_FILE` | `<project>/logs/python_service.log` | 日志文件路径 |
| `ALSA_LOG_FILE_MAX_BYTES` | `20971520` (20MB) | 日志文件最大大小 |
| `ALSA_LOG_FILE_BACKUP_COUNT` | `10` | 日志备份数 |
| `ALSA_INCIDENT_DIR` | `<project>/data/incidents` | 故障快照存储目录 |

---

## 附录 C：文件拆分建议

| 现有文件 | 行数 | 建议拆分 |
|---|---|---|
| `expert_tools.py` | 1952 | `tool_definitions.py` (工具schema) + `tool_executor.py` (执行逻辑) + `tool_cache.py` (去重缓存) + `financial_tools.py` (financial_data专用) |
| `market_data_service.py` | 1274 | `quote_service.py` (实时行情) + `financial_service.py` (财务数据) + `history_service.py` (历史K线) + `symbol_resolver.py` (代码解析) |
| `discussion_service.py` | 1133 | `topology.py` (拓扑定义) + `expert_runner.py` (专家执行) + `prompt_assembler.py` (prompt组装) + `batch_verifier.py` (批量验证) |
| `agent_orchestrator.py` | 1131 | `tool_loop.py` (核心循环) + `context_compressor.py` (摘要压缩) + `recall_handler.py` (按需恢复) |
| `analysis_job_service.py` | 978 | `job_lifecycle.py` (生命周期) + `api_key_manager.py` (密钥管理) + `result_serializer.py` (序列化) |
| `llm_gateway.py` | 820 | `provider_chain.py` (多Provider) + `rate_limiter.py` (限流) + `response_cache.py` (缓存) + `quality_gate.py` (质量门) |
