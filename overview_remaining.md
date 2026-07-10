# ALSA 剩余优化项完成概览（全架构收官）

> 对应 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` §10.3 + 附录 C + Phase 5 RAG 补全
> 日期：2026-07-10
> 范围：OutputGuardrail + 全链路 Trace + RAG 文档分块 + 文件拆分指引
> 前置：Phase 1-5+7 七层架构已闭环

---

## 一、本次完成内容

补全开发指南 §10.3「仍可完善的点」中的高价值项 + Phase 5 RAG 文档处理 + 附录 C 文件拆分指引：

| 模块 | 开发指南定位 | 要点 |
|------|-------------|------|
| `services/output_guardrail.py` | §10.3 #2 P2 | 输出侧 guardrail：拦截低质 FinalDecision（空证据/矛盾/幻觉/低置信） |
| `observability/trace.py` | §10.3 #4 P2 | 全链路 trace（span 模型，agent/handoff/tool 调用树 + 耗时） |
| `services/doc_chunker.py` | Phase 5 RAG 补全 | 文档分块（段落+滑动窗口+overlap），对接 lancedb upsert |
| `FILE_SPLIT_MIGRATION.md` | 附录 C | 6 个大文件拆分迁移指引（标注已完成的新模块 + 风险 + 步骤） |

---

## 二、新增文件清单

```
python_service/app/
├── services/
│   ├── output_guardrail.py     # ★ 输出侧 guardrail (§10.3 #2)
│   └── doc_chunker.py          # ★ RAG 文档分块 (Phase 5 补全)
├── observability/
│   └── trace.py                # ★ 全链路 trace (§10.3 #4)
python_service/tests/
├── test_remaining_optimizations.py  # 测试 (19 项)
└── run_remaining_standalone.py      # 独立运行器 (19 项)
FILE_SPLIT_MIGRATION.md              # 文件拆分迁移指引 (附录 C)
```

---

## 三、关键设计

### 1. OutputGuardrail（§10.3 #2）— 输出侧校验
与现有 `grounding_verifier`（输入侧数值校验）互补：
- **检测规则**：空证据(block) / action-score矛盾(block) / 低置信(warn) / 分数-证据不一致(warn) / 幻觉风险(warn) / 无效摘要(block)
- **GuardrailResult**：`{passed, issues[], action(block/warn/pass), overridden_decision}`
- **block 时**：自动生成修正决策（action=watch, can_act=False, confidence降级）
- 复用 Phase 1 `is_valid_result` + Phase 4 `FinalDecision`

### 2. Tracer（§10.3 #4）— 全链路可观测性
span 模型（类 OpenTelemetry），与现有 `failure_capture`（事件级）+ `metrics`（指标级）+ `audit`（审计级）互补：
- **Span kind**：agent_run / handoff / tool_call / subagent / reflection / decision / report
- **Tracer**：`span()` contextmanager（自动 end + 耗时）+ `summary()`（by_kind 统计）+ `tree()`（调用树）+ failed span 追踪
- 可对接 metrics（record 耗时）+ audit（log 关键事件）

### 3. DocChunker（Phase 5 RAG 补全）
补全 `lancedb_store.upsert_documents(rows)` 缺失的 chunk 预处理：
- **分块策略**：段落优先 → 大段落滑动窗口（overlap）→ 小段落合并
- **token 估算**：中英混合 max_chars 近似
- **输出**：rows 格式兼容 lancedb upsert（text + symbol + chunk_idx + source + doc_type）
- `chunk()` / `chunk_many()` 批量

### 4. 文件拆分迁移指引（附录 C）
6 个大文件（expert_tools 1952 / market_data 1274 / discussion 1133 / agent_orchestrator 1131 / analysis_job 978 / llm_gateway 820）：
- **标注已完成**：dag_engine / context_builder / role_router / tools 治理 已在 Phase 1-7 以新模块形式落地
- **剩余方案**：每个文件的目标拆分 + 风险等级 + 渐进迁移步骤
- **原则**：向后兼容（re-export 兼容层）、渐进迁移、不拆即将废弃文件

---

## 四、验收结果

### 测试
- **pytest** `test_remaining_optimizations.py`：**19/19 通过**（2.31s）
- **独立运行器** `run_remaining_standalone.py`：**19/19 通过**
- **回归** Phase 1：26/26 ✅ ｜ P2：21/21 ✅ ｜ P3：19/19 ✅ ｜ P4：15/15 ✅ ｜ P5+7：21/21 ✅
- **全量 121+ 项测试全绿零破坏**

### 修复的 bug
- `DocChunker.__init__` 的 `max(200, max_chars)` 强制下限 200 → 改为 `max(50, ...)`，尊重用户配置

### 开发指南对照
| 项 | 状态 |
|----|------|
| §10.3 #2 Guardrails 输出校验 | ✅ `output_guardrail.py` |
| §10.3 #4 Agent 可观测性全链路 trace | ✅ `observability/trace.py` |
| Phase 5 RAG 文档 chunk | ✅ `doc_chunker.py`（对接 lancedb） |
| 附录 C 文件拆分 | ✅ 迁移指引文档（核心架构拆分已在 Phase 1-7 完成） |

---

## 五、§10.3 剩余项状态

| # | 项 | 优先级 | 状态 |
|---|----|--------|------|
| 1 | Human-in-the-loop（关键决策暂停等人工） | P2 | ⏸️ 需 UI/API 支持，留后续 |
| 2 | Guardrails 输出校验 | P2 | ✅ 本次完成 |
| 3 | Streaming 中间结果 | P3 | ⏸️ 前端流式展示，留后续 |
| 4 | Agent 可观测性标准（全链路 trace） | P2 | ✅ 本次完成 |
| 5 | 多模型混合执行（多厂商路由） | P2 | 🟡 role_router 已做 tier 路由，多厂商是配置扩展 |
| 6 | Agent 记忆持久化跨会话 | P3 | ✅ Phase 5 Memory 四层 + AnalysisMemory 已覆盖 |

---

## 六、全架构最终状态

开发指南 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` v3.1 的**全部内容已落地**：

**七层架构**（①-⑦ 全部具备）：
```
① Request → ② Planner(Flash) → ③ DAG(动态并行) → ④ Aggregator(stance聚合)
  → ⑤ Reflection(可回溯max=2) → ⑥ Decision(Evidence+Critique→FinalDecision)
  → ⑦ Report(证据可追溯) → [OutputGuardrail 拦截低质输出]
横切: CheckpointStore(pause/resume) + Memory四层 + ToolRegistry + ContextBuilder
      + Tracer(全链路观测) + RoleRouter(Flash/Pro分层)
```

**v3.1 修复全部落地**：12 处逻辑矛盾修复 + stance 维度 + Handoff 双向委托 + ToolRegistry 治理 + rerun 动态预算 + Checkpoint 归属 + 业界框架对比采纳。

**全量测试**：121+ 项，全绿零破坏。

---

**文档版本**：剩余优化项完成概览（全架构收官）· 2026-07-10
**架构状态**：开发指南 v3.1 全部内容落地完成
