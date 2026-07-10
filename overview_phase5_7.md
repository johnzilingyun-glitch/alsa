# ALSA 多智能体架构 Phase 5+7 优化概览（收官）

> 对应开发指南 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` v3.1 §4.2.6 / §6 Phase 5 / §1.1 ⑦
> 日期：2026-07-10
> 范围：Checkpoint Store（pause/resume）+ Memory 四层 + Report Builder（⑦ Presentation）
> 前置：Phase 1-4 已完成（七层 ②③④⑤⑥ 五层核心落地）

---

## 一、本次做了什么

补全七层架构剩余的 **CheckpointStore（pause/resume）**、**Memory 四层**、**ReportBuilder（⑦ Presentation）**，完成开发指南全部 Phase 落地：

| 模块 | 开发指南定位 | 要点 |
|------|-------------|------|
| `services/checkpoint_store.py` | §4.2.6 Phase5 pause/resume | 可序列化 ExecutionPlan/AgentState/AgentResult/FinalDecision，内存级 + JSON 持久化 |
| `services/memory_store.py` | §6 Phase5 Memory 四层 | Session/Analysis/Project/User 分层，Analysis 复用 AgentMemory 向量检索 |
| `agents/report_builder.py` | §1.1 ⑦ Presentation | FinalDecision + AggregatedEvidence → Markdown 报告，证据可追溯（claim+source） |

### v3.1 严格遵守
- ✅ §4.2.6 pause/resume 归 Phase5（Phase2 仅 degrade）
- ✅ §6 Memory 拆 Session/Analysis/Project/User
- ✅ ⑦ Report Builder 基于 Evidence 引用（claim + source 可追溯）

---

## 二、新增文件清单

```
python_service/app/
├── services/
│   ├── checkpoint_store.py     # ★ CheckpointStore pause/resume (§4.2.6)
│   └── memory_store.py         # ★ Memory 四层 Session/Analysis/Project/User (§6)
├── agents/
│   └── report_builder.py       # ★ ReportBuilder ⑦ Presentation (Evidence 引用)
python_service/tests/
├── test_phase5_7_memory_report.py  # 测试 (21 项)
└── run_phase5_7_standalone.py      # 独立运行器 (21 项)
```

---

## 三、关键设计

### 1. CheckpointStore（§4.2.6）— pause/resume
```
save(key, state)      # 暂停点保存 (内存级 + 可选 JSON 落盘)
resume(key) → state   # 恢复 (优先内存, 其次持久化)
list_checkpoints(job_id) / delete / clear
```
- **支持类型**：ExecutionPlan / AgentState / AgentResult / FinalDecision / AggregatedEvidence / CritiqueResult + 任意 dataclass（`_TYPE_REGISTRY` 注册表 + asdict 序列化）
- **两级存储**：内存级（对象引用，最快 resume）+ 持久化级（JSON，跨进程恢复）
- 可作为 LangGraph BaseCheckpointSaver 后端（Phase5+ 衔接）

### 2. MemoryStore（§6）— 四层 Memory
| 层 | 生命周期 | 实现 | 用途 |
|----|----------|------|------|
| Session | 会话级 | 进程内 dict | EvidenceBus 快照 / ExecutionPlan / 临时状态 |
| Analysis | 跨会话 | 复用 AgentMemory（向量检索） | 某 symbol 分析历史 |
| Project | 项目级 | JSON 持久化 | 项目配置/偏好/约定 |
| User | 用户级 | JSON 持久化 | 用户偏好/习惯（跨项目） |

- 统一接口：`put(layer, key, value)` / `get` / `query(prefix)` / `delete`
- `snapshot_session(job_id, plan, evidence_bus, checkpoint_store)`：会话快照可落 CheckpointStore
- `aremember_analysis` / `arecall_analysis`：异步对接 AgentMemory.store/recall（向量语义检索）

### 3. ReportBuilder（⑦ Presentation）— Evidence 引用
```
build_markdown(decision, aggregated, results, critique) → str   # Markdown 报告
build(decision, aggregated, results, critique) → dict           # 结构化 (供 HTML 渲染)
```
**报告结构**（证据可追溯）：
1. 摘要（FinalDecision.summary）
2. 综合评估（评分/立场/行动/置信度/可执行性）
3. 关键结论（consensus≥0.7 的 claim）
4. **证据详情**（每个 claim：supporting/contradicting + agent + stance + confidence + **source 可追溯**）
5. 证据冲突标记
6. 风险清单
7. 反思问题（CritiqueResult.issues）
8. 决策依据

---

## 四、验收结果

### 测试
- **pytest** `test_phase5_7_memory_report.py`（`--noconftest`）：**21/21 通过**（0.25s）
- **独立运行器** `run_phase5_7_standalone.py`：**21/21 通过**
- **回归** Phase 1：26/26 ✅ ｜ Phase 2：21/21 ✅ ｜ Phase 3：19/19 ✅ ｜ Phase 4：15/15 ✅（零破坏）

### 开发指南 Phase 5+7 验收对照
| 验收项 | 状态 |
|--------|------|
| Checkpoint Store（pause/resume） | ✅ `checkpoint_store.py` |
| Memory 拆 Session/Analysis/Project/User | ✅ `memory_store.py` |
| ⑦ Report Builder（Evidence 引用） | ✅ `report_builder.py`（claim+source 可追溯） |
| 可 pause/resume | ✅ 测试 `test_checkpoint_save_resume_memory` + 持久化 roundtrip |
| 证据可追溯 | ✅ 测试 `test_report_markdown_evidence_traceable`（source/agent/stance） |

> Phase 5 的「RAG 文档 chunk + 向量化」复用现有 `vector/lancedb_store.py`（LanceResearchStore 已支持 upsert/search），本次 Memory 四层的 Analysis 层已对接 AgentMemory（其底层即 LanceDB），不再重复实现。
> 「超大文件拆分」（附录 C）属独立重构任务，不影响架构功能，留作后续代码维护项。

---

## 五、与现有代码的衔接（非破坏性）

| 现有文件 | 衔接方式 |
|----------|----------|
| `agent_memory.AgentMemory`（recall/store） | MemoryStore.Analysis 层异步对接（aremember/arecall） ✅ |
| `vector/lancedb_store.LanceResearchStore` | AgentMemory 底层向量存储（RAG 基础已具备） ✅ |
| `report_generator_service.ReportGeneratorService` | ReportBuilder 提供结构化 dict 数据源，可由其渲染 HTML |
| Phase 4 `FinalDecision` | ReportBuilder 输入 ✅ |
| Phase 3 `AggregatedEvidence` | ReportBuilder 证据引用源 ✅ |
| Phase 2 `EvidenceBus.snapshot` | MemoryStore.snapshot_session 输入 ✅ |

---

## 六、七层架构完整流水线（Phase 1-5+7 全部落地）

```
① Request    Symbol Resolve + Intent Parse
   │
   ▼
② Planning   PlannerService.plan() → ExecutionPlan           (Flash 规划, Phase3)
   │          ├─ ToolRegistry.resolve 映射工具 (Phase1)
   │          └─ 预取意图
   ▼
③ Execution  DAGEngine.run(plan, snapshot) → list[AgentResult] (动态并行, Phase3)
   │            └─ BaseAgent.run → ContextBuilder(Phase1) + Handoff/SubAgent(Phase2)
   │                              + 结构化输出(Phase2) + EvidenceBus(Phase2)
   ▼
④ Evidence   EvidenceAggregator.aggregate(results) → AggregatedEvidence  (stance 聚合, Phase3)
   │
   ▼
⑤ Reflection ReflectionAgent.critique(aggregated, results) → CritiqueResult  (可回溯 max=2, Phase4)
   │            └─ 可触发 DAGEngine.rerun 回溯
   ▼
⑥ Decision   DecisionAgent.decide(aggregated, critique, results) → FinalDecision  (Phase4)
   │            └─ role_router: Flash 整理 / Pro 推理 (Token ↓>50%)
   ▼
⑦ Presentation ReportBuilder.build_markdown(decision, aggregated, results, critique) → Report  (Phase7)
                └─ 证据可追溯 (claim + source)

横切: CheckpointStore(pause/resume, Phase5) │ Memory四层(Phase5) │ ToolRegistry(Phase1)
```

**开发指南全部 Phase（1-5+7）落地完成**。七层架构 ①-⑦ 全部具备（①Request 复用现有 symbol resolve）。

---

## 七、全量测试汇总

| Phase | 测试数 | 状态 |
|-------|--------|------|
| Phase 1（Tool 治理 + ContextBuilder + 契约） | 26 | ✅ |
| Phase 2（SubAgent + Handoff + EvidenceBus） | 21 | ✅ |
| Phase 3（Planner + DAG + Aggregator） | 23 (pytest) / 19 (standalone) | ✅ |
| Phase 4（Reflection + RoleRouter + Decision） | 16 (pytest) / 15 (standalone) | ✅ |
| Phase 5+7（Checkpoint + Memory + Report） | 21 | ✅ |
| **合计** | **107+ 项测试** | **全绿零破坏** |

---

**文档版本**：Phase 5+7 实施概览（收官）· 2026-07-10
**架构状态**：开发指南 v3.1 全部 Phase 落地完成，七层多智能体架构闭环
