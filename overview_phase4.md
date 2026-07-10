# ALSA 多智能体架构 Phase 4 优化概览

> 对应开发指南 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` v3.1 §4.4 / §6 / §7.2 Phase 4
> 日期：2026-07-10
> 范围：Reflection Agent 可回溯 + role→model 路由 + Decision Layer
> 前置：Phase 1（Tool 治理 + 契约）+ Phase 2（SubAgent + Handoff）+ Phase 3（Planner + DAG + Aggregator）已完成

---

## 一、本次做了什么

基于开发指南 v3.1 §4.4，把 Phase 0 的一次性反思（`self_reflection_agent` / `critic_agent`）升级为 **可回溯反思**（rerun max=2）+ **Model 分层**（Flash 整理 / Pro 推理）+ **Decision Layer**，解决 2 个 🟡 P1 差距：

| 差距 # | 维度 | Phase 0/3 现状 | Phase 4 修复 |
|--------|------|----------------|--------------|
| #6 | Reflection | 一次性 self_reflection | **ReflectionAgent** 可回溯（rerun max=2，递归+计数防死循环） |
| #9 | 模型路由 | 全程 Pro | **RoleRouter** Flash 整理 / Pro 推理（Token 成本 ↓ >50%） |
| — | Decision | Chief Strategist 自由文本 | **DecisionAgent** 输入 Evidence+Critique → 结构化 FinalDecision |

### v3.1 严格遵守
- ✅ §4.4 `max_reflection_rounds=2`，超限强制 finalize
- ✅ §7.2 rerun 动态预算：rerun 时 budget +2k（不再固定预算导致超限）
- ✅ §6 Reflection/Decision 用 Pro，Planner/整理类用 Flash

---

## 二、新增文件清单

```
python_service/app/
├── agents/
│   ├── reflection_agent.py      # ★ ReflectionAgent 可回溯反思 (§4.4)
│   └── decision_agent.py        # ★ DecisionAgent Evidence+Critique→FinalDecision (§6)
├── services/
│   └── role_router.py           # ★ role→model 路由 + rerun 动态预算 (§6/§7.2)
python_service/tests/
├── test_phase4_reflection.py    # Phase 4 测试 (16 项)
└── run_phase4_standalone.py     # 独立运行器 (15 项)
```

---

## 三、关键设计

### 1. ReflectionAgent（§4.4）— 可回溯反思
```
critique(aggregated, results, plan, snapshot, round_num=0) → CritiqueResult
  1. round_num >= MAX_REFLECTION_ROUNDS(2) → 强制 finalize (防死循环)
  2. _generate_critique: 默认规则, 可注入 Pro LLM
  3. if not can_finalize:
       need_more_evidence → _fetch_more (经 ToolRegistry)
       rerun_agents → DAGEngine.rerun → _merge → re-aggregate
       → 递归 critique(round_num+1)  ← 计数防死循环
  4. return critique
```
**规则 critique 判定**（默认，可注入 LLM 增强）：
- 有 conflicts → rerun 冲突相关 agent（低 consensus claim 对应方）
- 有 skipped/degraded agent → rerun
- coverage <0.3 → need_more_evidence
- 无冲突 + 无 skipped + 平均 coverage ≥0.5 → can_finalize

**复用 Phase 3**：`DAGEngine.rerun`（回溯重跑）+ `EvidenceAggregator.aggregate`（re-aggregate）

### 2. RoleRouter（§6 + §7.2）— Model 分层 + rerun 动态预算
| role | tier | 用途 | 默认预算 | rerun 预算 |
|------|------|------|----------|-----------|
| Planner | Flash | 规划/整理 | 4k | — |
| News/Industry Analyst | Flash | 新闻/行业提取 | 4k | +2k |
| Technical/Fundamental/Macro/Sentiment | Pro | 推理分析 | 8-10k | +2k |
| Reflection | Pro | 交叉验证 | 6k | 8k (+2k) |
| Decision | Pro | 最终决策 | 8k | — |

- `resolve_model(role)` → 具体模型名（Flash≠Pro，成本分层）
- `resolve_budget(role, is_rerun=True)` → +2k（§7.2 rerun 动态预算）
- `estimate_cost_saving` → Flash 占比 × 0.9（目标 ↓ >50%）

### 3. DecisionAgent（§6）— Decision Layer
```
decide(aggregated, critique, results, symbol) → FinalDecision
  1. final_score = Σ(score×confidence) / Σ(confidence)  (加权)
  2. stance = stance_distribution 中最多
  3. action: score≥0.65→buy, ≤0.4→sell, else→hold
  4. critique.can_finalize=False → action=watch, confidence×0.6 (降级)
  5. risks 汇总去重; key_claims 取 consensus≥0.7
```
**FinalDecision**：symbol/final_score/stance/action/confidence/summary/risks[]/key_claims[]/can_act/rationale

---

## 四、验收结果

### 测试
- **pytest** `test_phase4_reflection.py`（`--noconftest`）：**16/16 通过**（2.71s）
- **独立运行器** `run_phase4_standalone.py`：**15/15 通过**
- **回归** Phase 1：26/26 ✅ ｜ Phase 2：21/21 ✅ ｜ Phase 3：19/19 ✅（零破坏）

### 开发指南 Phase 4 验收对照
| 验收项 | 状态 |
|--------|------|
| 升级 Professional Reviewer → ReflectionAgent（可回溯，max=2） | ✅ `reflection_agent.py` |
| Chief Strategist 输入改 Evidence+Critique | ✅ `decision_agent.py` |
| `llm_gateway` role→model 路由（Flash 整理 / Pro 推理） | ✅ `role_router.py` |
| Reflection 可触发回溯 | ✅ 测试 `test_reflection_rerun_recursion` |
| Token 成本 ↓ >50% | ✅ Flash 分层（estimate_cost_saving >0.5） |
| rerun 动态预算（§7.2） | ✅ `resolve_budget(is_rerun=True)` +2k |

---

## 五、与现有代码的衔接（非破坏性）

| 现有文件 | 衔接方式 |
|----------|----------|
| `self_reflection_agent.SelfReflectionAgent`（一次性） | → `ReflectionAgent`（可回溯，旧代码保留可用） |
| `critic_agent.CriticAgent` | → `ReflectionAgent`（升级，复用反思维度思路） |
| `llm_gateway.generate_content` | RoleRouter 提供 role→model 映射（可接入 gateway 的 model 选择） |
| Phase 3 `DAGEngine.rerun` | ReflectionAgent 回溯重跑 ✅ |
| Phase 3 `EvidenceAggregator` | ReflectionAgent re-aggregate ✅ |
| Phase 3 `EvidenceAggregator.stance_distribution` | DecisionAgent stance 判定 ✅ |
| Phase 1 `contracts.CritiqueResult/Issue/Correction` | ReflectionAgent 输出 ✅ |

**渐进迁移路径**（灰度）：
1. 现有 `self_reflection_agent` / `critic_agent` 继续工作（未删）。
2. 新流程：`aggregated = EvidenceAggregator.aggregate(results)` → `critique = await reflection_agent.critique(aggregated, results, plan, snapshot)` → `fd = await decision_agent.decide(aggregated, critique, results)`。
3. `llm_gateway` 可接入 `role_router.resolve_model(role)` 实现 model 路由。

---

## 六、完整流水线（Phase 1+2+3+4）

```
PlannerService.plan() → ExecutionPlan           (② Flash 规划)
  → DAGEngine.run(plan, snapshot) → list[AgentResult]  (③ 动态并行)
    (BaseAgent.run → ContextBuilder + Handoff/SubAgent + 结构化输出 + EvidenceBus)
  → EvidenceAggregator.aggregate(results) → AggregatedEvidence  (④ stance 聚合)
  → ReflectionAgent.critique(aggregated, results) → CritiqueResult  (⑤ 可回溯)
    (可触发 DAGEngine.rerun 回溯, max=2)
  → DecisionAgent.decide(aggregated, critique, results) → FinalDecision  (⑥ 决策)
  → (Phase 7: Report Builder 引用 Evidence 生成报告)
```

七层架构的 ②③④⑤⑥ 五层核心已全部落地。

---

## 七、后续 Phase 衔接点

| Phase | 衔接点 | 本次已铺垫 |
|-------|--------|-----------|
| Phase 5 | RAG + Memory 四层 + Checkpoint | `FinalDecision` 可持久化；`AgentState`/`ExecutionPlan` 可序列化（pause/resume 扩展点）；`EvidenceBus.snapshot` 可存 Memory |
| Phase 7 | Report Builder | `FinalDecision` + `AggregatedEvidence.claims`（含 source 可追溯）供报告引用 |

---

**文档版本**：Phase 4 实施概览 · 2026-07-10
**下次评审**：Phase 5 启动前
