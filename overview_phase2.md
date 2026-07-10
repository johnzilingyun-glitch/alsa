# ALSA 多智能体架构 Phase 2 优化概览

> 对应开发指南 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` v3.1 §4.2 + §6 Phase 2
> 日期：2026-07-09
> 范围：SubAgent 框架 + Handoff 双向委托 + EvidenceBus + 结构化输出
> 前置：Phase 1（Context Builder + Tool Registry 治理 + 数据契约）已完成

---

## 一、本次做了什么

基于开发指南 v3.1 §4.2（★ v3.1 核心新增），把 Phase 0 的 `make_node` 闭包改造为**独立 Agent 实例**，落地 Phase 2 的三大 🔴 P0 差距修复：

| 差距 # | 维度 | Phase 0 现状 | Phase 2 修复 |
|--------|------|--------------|--------------|
| #3 | Agent 通信 | `history_states` dict（只读上一轮） | **EvidenceBus**（异步证据共享）+ **Handoff**（双向委托） |
| #4 | Agent 实例 | 闭包函数 | **BaseAgent** 独立实例 + **SubAgent as_tool** 嵌套 |
| #8 | 输出格式 | 自由文本截断 2000 字 | **结构化 JSON**（Pydantic schema + response_format） |

### v3.1 边界修正（严格遵守）
- ✅ Phase 2 **不做动态并行**（留 Phase 3），保留固定拓扑但 Agent 实例化 + handoff
- ✅ Phase 2 **只有 degrade**，pause/resume 归 Phase 5（Checkpoint）
- ✅ Handoff 链深度上限 `HANDOFF_MAX_DEPTH=2`（防 A→B→A→B）

---

## 二、新增文件清单

```
python_service/app/agents/
├── __init__.py
├── evidence_bus.py           # ★ EvidenceBus 证据发布/订阅 (替换 history_states)
├── handoff.py                # ★ Handoff 双向委托 + input_filter (治 context)
├── agent_result_schema.py    # ★ 结构化输出 Schema (Pydantic, 移除 2000 字截断)
├── base_agent.py             # ★ BaseAgent 基类 (独立实例/handoff/as_tool/降级)
└── expert_agents.py          # ★ SubAgent + 具体 Agent (Technical/Fundamental/Macro/Sentiment)

python_service/tests/
├── test_phase2_agents.py     # Phase 2 测试 (21 项)
└── run_phase2_standalone.py  # 独立运行器 (绕过 conftest 重型导入)
```

---

## 三、关键设计

### 1. BaseAgent（§4.2.2）— 独立 Agent 实例
```
run(plan, snapshot) → AgentResult
  1. context_builder.build() 构建最小高价值上下文 (复用 Phase 1)
  2. _reason_with_tools: tool loop (LLM 工具列表含 数据工具 + SubAgent + Handoff)
  3. parse_agent_output 解析结构化 JSON → AgentResult (移除 2000 字截断)
  4. evidence_bus.publish(role, evidence) (替换 history_states)

run_delegate(filtered_history, input_data, snapshot, depth)
  被 Handoff 委托时执行 (双向委托接收方, input_filter 已裁剪)

_execute_decision(decision, snapshot)
  handoff:  双向委托 (结果回灌, 不替换控制权, §7.5)
  subagent: as_tool 嵌套 (不转移控制权)
  data:     普通工具 → ToolRegistry.execute (Phase 1 治理)
```
- **依赖注入** `llm_runner`：默认懒导入 `agent_orchestrator`，测试时注入 mock，不依赖重型 LLM/数据栈
- **降级**（§7.3）：`skip`/`default`(中性 score=0.5)/`retry`；单 Agent 失败不阻塞

### 2. Handoff（§4.2.3）— 双向委托
- 作为 tool 暴露给 LLM（`transfer_to_<target>`），LLM 决定何时委托
- **input_filter 治 context**（OpenAI 范式）：
  - `summary_only`（默认）：只传上一轮摘要（最小 context）
  - `recent_2`：传最近 2 轮全文
  - `full`：传完整历史（仅关键决策）
- **与 EvidenceBus 区别**：Handoff=同步委托（有依赖），EvidenceBus=异步共享（独立并行）
- 链深度上限 `HANDOFF_MAX_DEPTH=2`

### 3. EvidenceBus（§4.2）— 替换 history_states
- `publish(role, evidence)`：Agent 完成后发布结构化 Evidence（含 v3.1 stance 维度）
- `relevant(consumer_role)`：独立并行 Agent 读取其他 Agent 结论（排除自己）
- `stance_summary()`：按 role 统计 bullish/bearish/neutral 分布（供 Reflection 判冲突）

### 4. SubAgent as_tool 嵌套（§4.2.1）— 两级树
```
Technical Agent ──as_tool──► News SubAgent      (取新闻证据)
                ──as_tool──► Industry SubAgent  (取行业证据)
                ──handoff──► Fundamental Agent  (发现需基本面印证时委托)
Macro Agent     ──as_tool──► Risk SubAgent      (风险评估)
                ──as_tool──► Valuation SubAgent (估值)
```
- `run_as_tool(input_data, snapshot)`：作为工具被父 Agent 调用，**不转移控制权**（OpenAI `Agent.as_tool()` 范式），结果回灌父 Agent 上下文

### 5. 结构化输出（§7.1）
- `AgentOutputSchema`（Pydantic v2）：`summary/score/confidence/stance/evidence[]/risk[]/status`
- `response_format_spec()`：OpenAI `json_schema` response_format
- `parse_agent_output()`：容错解析（markdown 包裹/非法 JSON 降级，不抛异常保证不阻塞）
- **禁止 `content[:2000]` 截断**，evidence 带 v3.1 stance 维度

---

## 四、验收结果

### 测试
- **独立运行器** `run_phase2_standalone.py`：**21/21 通过**
- **pytest** `test_phase2_agents.py`（`--noconftest`）：**21/21 通过**（1.97s）
- **回归** Phase 1 `run_phase1_standalone.py`：**26/26 通过**（零破坏）

### 开发指南 Phase 2 验收对照
| 验收项 | 状态 |
|--------|------|
| `make_node` 闭包 → `BaseAgent` 子类实例 | ✅ `expert_agents.py` |
| Handoff 机制（双向委托 + input_filter） | ✅ `handoff.py` |
| SubAgent as_tool 嵌套（News/Industry/Risk/Valuation） | ✅ `expert_agents.py` |
| EvidenceBus 替换 history_states dict | ✅ `evidence_bus.py` |
| Agent 输出结构化 JSON（移除 2000 字截断） | ✅ `agent_result_schema.py` |
| Agent 可 handoff 委托 | ✅ 测试 `test_handoff_execute_delegates` |
| SubAgent 可被 as_tool 调用 | ✅ 测试 `test_subagent_as_tool` |
| 单 Agent 失败不阻塞 | ✅ 测试 `test_base_agent_failure_degrades` |
| LangGraph 条件路由死代码激活 | ⏳ Phase 3（动态并行时激活） |

---

## 五、与现有代码的衔接（非破坏性）

| 现有文件 | 衔接方式 |
|----------|----------|
| `discussion_service.make_node` 闭包 | → `BaseAgent` 子类实例（渐进迁移，旧闭包保留可用） |
| `discussion_service.history_states` dict | → `EvidenceBus` + handoff |
| `agent_orchestrator.generate_with_tools` | BaseAgent 默认 `llm_runner` 懒导入复用 |
| `expert_tools.TOOL_DEFINITIONS` | BaseAgent `_exec_data_tool` 经 Phase 1 ToolRegistry 治理 |
| Phase 1 `context_builder` | BaseAgent 直接复用 ✅ |
| Phase 1 `schemas.contracts` | AgentSpec/HandoffSpec/Evidence/AgentResult ✅ |

**渐进迁移路径**（灰度，旧流程零改动）：
1. 现有 `discussion_service` 继续工作（闭包未删）。
2. 新 Agent 实例可通过 `create_agent(role)` 创建，注入到编排层。
3. `make_node` 可逐步替换为 `agent.run(plan, snapshot)`。
4. `history_states` 读写可逐步替换为 `evidence_bus.publish/relevant`。

---

## 六、后续 Phase 衔接点

| Phase | 衔接点 | 本次已铺垫 |
|-------|--------|-----------|
| Phase 3 | Planner + Send 动态并行 | `BaseAgent` 独立实例可直接被 Send 派发；`create_agent` 工厂供 Planner；固定拓扑→动态拓扑 |
| Phase 4 | Reflection Agent | `EvidenceBus.stance_summary()` 供判冲突；`contracts.CritiqueResult`（Phase 1）已定义；`parse_agent_output` 降级机制可复用 |
| Phase 5 | Checkpoint (pause/resume) | `AgentState` 可序列化；`BaseAgent` 降级接口已留（pause/resume 在此扩展） |

---

**文档版本**：Phase 2 实施概览 · 2026-07-09
**下次评审**：Phase 3 启动前
