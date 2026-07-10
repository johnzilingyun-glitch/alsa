# ALSA 多智能体架构 Phase 3 优化概览

> 对应开发指南 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` v3.1 §4.1 / §4.2.5 / §4.3 + §6 Phase 3
> 日期：2026-07-09
> 范围：Planner 动态规划 + DAGEngine 动态并行 + Evidence Aggregator
> 前置：Phase 1（Tool 治理 + ContextBuilder + 契约）+ Phase 2（SubAgent + Handoff + EvidenceBus）已完成

---

## 一、本次做了什么

基于开发指南 v3.1，把 Phase 0 的**固定拓扑**（`build_topology(level)` + LangGraph StateGraph）升级为 **Planner 动态规划 + 运行时动态并行 + stance 维度证据聚合**，解决 3 个 🔴 P0 差距：

| 差距 # | 维度 | Phase 0/2 现状 | Phase 3 修复 |
|--------|------|----------------|--------------|
| #1 | 规划 | 固定拓扑 QUICK/STANDARD/DEEP | **PlannerService** 按股票特征动态选 Agent 数 |
| #2 | 并行 | 固定 Send（硬编码分支） | **DAGEngine** 运行时决定并行分支数（asyncio.gather） |
| #5 | Evidence | Professional Reviewer 找矛盾 | **EvidenceAggregator** 按 stance 聚合 + 冲突标记 |

### v3.1 边界修正（严格遵守）
- ✅ 动态并行（Send）归 Phase 3，不在 Phase 2
- ✅ Phase 3 用纯 asyncio 实现 DAGEngine（不依赖 LangGraph 运行时，更可控可测）
- ✅ Planner 规则兜底 + 可注入 Flash LLM（依赖注入，可测试）

---

## 二、新增文件清单

```
python_service/app/
├── engine/
│   ├── __init__.py
│   └── dag_engine.py            # ★ DAGEngine 动态并行 (替代固定 Send)
├── services/
│   ├── planner_service.py       # ★ PlannerService 动态规划 (替代 build_topology)
│   └── evidence_store.py        # ★ EvidenceAggregator stance 维度聚合
python_service/tests/
├── test_phase3_orchestration.py  # Phase 3 测试 (23 项)
└── run_phase3_standalone.py      # 独立运行器 (19 项)
```

---

## 三、关键设计

### 1. DAGEngine（§4.2.5）— 运行时动态并行
```
build_parallel_branches(plan) → list[list[AgentSpec]]
  按 depends_on 拓扑分层 (Kahn):
    同层无依赖 → 一组并行分支 (运行时决定分支数, 非硬编码)
    跨层 → 串行 (等依赖完成)

run(plan, snapshot) → list[AgentResult]
  分层并行 (asyncio.gather + 并发上限 Semaphore)
  跨层串行
  短路检测 (数据严重不足 → 下游 skipped, §4.2 条件路由)
  单 Agent 失败降级 (不阻塞)

rerun(plan, snapshot, agent_ids) → list[AgentResult]
  重跑指定 Agent (供 Phase 4 Reflection 回溯, §4.4)
```
- **纯 asyncio**，不依赖 LangGraph 运行时（更可控/可测）
- 循环依赖兜底破解（不死循环）
- 复用 Phase 2 `create_agent` 工厂 + `BaseAgent.run`

### 2. PlannerService（§4.1）— 动态规划 Orchestrator
```
plan(symbol, question, market) → ExecutionPlan
  1. _profile: 股票画像 (市场/资产类型/数据可用性, 非原始数据)
  2. plan_generator: 默认规则兜底, 可注入 Flash LLM
  3. ToolRegistry.resolve: data_type → 候选工具 (按优先级)
  4. _validate_and_patch: 至少 1 Agent + quote/history 预取
  5. _prefetch: 预取意图 (实际预取留 DataRouter 衔接)
```
**决策示例（§4.1）— 运行时动态选 Agent 数**：
| 股票特征 | 激活 Agent + SubAgent | Agent 数 |
|----------|----------------------|----------|
| A股科技股 | Technical[News,Industry] + Fundamental + Sentiment | 3 |
| 港股金融股 | Fundamental + Macro[Risk] + Sentiment | 3 |
| 美股成长股 | Technical[News] + Fundamental + Macro[Valuation] | 3 |
| 数据严重不足 | 仅 Technical | 1 |

### 3. EvidenceAggregator（§4.3）— stance 维度聚合（v3.1 修复）
```
aggregate(results) → AggregatedEvidence
  1. 按 claim 聚类 (默认 normalize 文本分组, 可注入 Flash 语义聚类)
  2. v3.1 修复: 按 stance 分 (不是 confidence):
       supporting   = stance ∈ {bullish, neutral}
       contradicting = stance == bearish
     低 confidence 只是证据弱, 不一定是反对
  3. consensus = supporting权重 / 总权重
  4. 冲突标记: 存在 contradicting + supporting → Conflict
  5. coverage: role → 覆盖度 (skipped=0/degraded=0.3/ok+证据高)
```

---

## 四、验收结果

### 测试
- **pytest** `test_phase3_orchestration.py`（`--noconftest`）：**23/23 通过**（3.12s）
- **独立运行器** `run_phase3_standalone.py`：**19/19 通过**
- **回归** Phase 1：26/26 ✅ ｜ Phase 2：21/21 ✅（零破坏）

### 开发指南 Phase 3 验收对照
| 验收项 | 状态 |
|--------|------|
| `planner_service.py`（Flash 出 plan，经 ToolRegistry 映射工具） | ✅ 规则兜底 + 可注入 LLM |
| 固定 Send → 动态 Send（运行时决定并行分支数） | ✅ DAGEngine.build_parallel_branches |
| `evidence_store.py` + Aggregator（stance 维度聚合） | ✅ v3.1 stance 修复 |
| 替换 `build_topology(level)` 为 Planner 驱动 | ✅ PlannerService（旧 build_topology 保留可用） |
| Planner 按股票特征动态选 Agent 数 | ✅ 测试 `test_planner_dynamic_agent_count` |
| 并行分支数运行时决定 | ✅ 测试 `test_dag_parallel_branches_no_deps` |
| LangGraph 条件路由死代码激活 | ✅ DAGEngine 短路检测（纯 asyncio 实现） |

---

## 五、与现有代码的衔接（非破坏性）

| 现有文件 | 衔接方式 |
|----------|----------|
| `discussion_service.build_topology`（固定模板） | → `PlannerService.plan` 动态规划（旧模板保留可用） |
| `discussion_service` LangGraph StateGraph | → `DAGEngine`（asyncio，更可控） |
| `discussion_service` 轮间条件路由 | → `DAGEngine._is_short_circuit` 短路检测 |
| Phase 2 `create_agent` 工厂 | DAGEngine 默认 agent_factory ✅ |
| Phase 2 `EvidenceBus.all_evidence` | EvidenceAggregator 输入源 ✅ |
| Phase 1 `ToolRegistry.resolve` | Planner 映射 data_fetch_manifest ✅ |
| Phase 1 `contracts.ExecutionPlan/DAGSpec` | Planner 产出 / DAGEngine 输入 ✅ |

**渐进迁移路径**（灰度，旧流程零改动）：
1. 现有 `discussion_service` 继续工作（固定拓扑 + LangGraph 未删）。
2. 新流程：`plan = await planner_service.plan(...)` → `results = await dag_engine.run(plan, snapshot)` → `aggregated = evidence_aggregator.aggregate(results)`。
3. `build_topology(level)` 可逐步替换为 `PlannerService.plan`。
4. LangGraph 编排可逐步替换为 `DAGEngine`。

---

## 六、后续 Phase 衔接点

| Phase | 衔接点 | 本次已铺垫 |
|-------|--------|-----------|
| Phase 4 | Reflection Agent + Model 分层 | `DAGEngine.rerun`（回溯重跑）；`EvidenceAggregator.stance_distribution`（判冲突）；`EvidenceBus.stance_summary`；`contracts.CritiqueResult`（Phase 1） |
| Phase 5 | Memory + Checkpoint | `ExecutionPlan` 可序列化；`DAGEngine` 状态可快照（pause/resume 扩展点） |

**完整流水线已打通**（Phase 1+2+3）：
```
PlannerService.plan() → ExecutionPlan
  → DAGEngine.run(plan, snapshot) → list[AgentResult]
    (每个 Agent: BaseAgent.run → ContextBuilder + Handoff/SubAgent + 结构化输出 + EvidenceBus)
  → EvidenceAggregator.aggregate(results) → AggregatedEvidence
  → (Phase 4: ReflectionAgent.critique → 可 rerun)
  → (Phase 6: Decision → FinalDecision)
```

---

**文档版本**：Phase 3 实施概览 · 2026-07-09
**下次评审**：Phase 4 启动前
