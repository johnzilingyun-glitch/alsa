# ALSA 文件拆分迁移指引（附录 C）

> 对应 `MULTI_AGENT_ARCHITECTURE_DEV_GUIDE.md` 附录 C
> 日期：2026-07-10
> 原则：增量非破坏，渐进迁移，保持向后兼容

---

## 一、现状总览

附录 C 列出 6 个超大文件，目标验收"每个文件 ≤ 250 行"：

| 文件 | 行数 | 拆分状态 |
|------|------|----------|
| `expert_tools.py` | 1952 | 🟡 部分完成（Tool 治理已抽到 `tools/`） |
| `market_data_service.py` | 1274 | 🔴 未拆分 |
| `discussion_service.py` | 1133 | 🟢 大部分已抽（dag_engine/context_builder） |
| `agent_orchestrator.py` | 1131 | 🟢 大部分已抽（context_builder/tool_loop） |
| `analysis_job_service.py` | 978 | 🔴 未拆分 |
| `llm_gateway.py` | 820 | 🟡 部分完成（role_router 已抽） |

---

## 二、已完成的拆分（Phase 1-7 以新模块形式落地）

开发指南附录 C 的拆分目标，相当一部分已在 Phase 1-7 中**以新增独立模块**形式实现（未删旧代码，保持向后兼容）：

| 附录 C 目标 | 已落地新模块 | 完成度 |
|-------------|-------------|--------|
| `discussion_service.py` → `dag_engine.py` + `topology.py` | `app/engine/dag_engine.py`（Phase 3）+ `planner_service.py` | ✅ |
| `discussion_service.py` → context 部分并入 `context_builder` | `app/services/context_builder.py`（Phase 1） | ✅ |
| `agent_orchestrator.py` → `tool_loop.py`(并入 base_agent) + `context_compressor.py`(并入 context_builder) | `app/agents/base_agent.py`（Phase 2）+ `context_builder.py` | ✅ |
| `expert_tools.py` → `tool_definitions.py` + `tool_executor.py` + `tool_cache.py` + 注册到 `registry.py` | `app/services/tools/{registry,shared_cache,preconditions,metrics}.py`（Phase 1） | ✅ 缓存/治理已抽 |
| `llm_gateway.py` → `provider_chain.py` + `rate_limiter.py` + `response_cache.py` + `role_router.py` | `app/services/role_router.py`（Phase 4） | 🟡 role_router 已抽，其余未抽 |

**结论**：附录 C 的核心架构拆分（编排/上下文/工具治理/模型路由）已通过 Phase 1-7 的新模块完成。剩余主要是**数据服务层**和**网关层**的实现拆分。

---

## 三、剩余拆分方案与风险

### 1. `market_data_service.py` (1274 行) → 数据服务拆分
**目标**：`quote_service.py` + `financial_service.py` + `history_service.py` + `symbol_resolver.py`

**风险**：🔴 高
- 被 `expert_tools.py` / `discussion_service.py` / 多个 API 路由引用
- 改导入路径需同步改所有引用方

**迁移步骤**：
1. 新建 `services/market_data/` 子包
2. 按职责拆分：quote（实时行情）/ financial（财报）/ history（K线）/ symbol_resolver（代码解析）
3. 在原 `market_data_service.py` 保留 re-export 兼容层（`from .market_data.quote import *`）
4. 逐个迁移引用方，最后删除兼容层

### 2. `analysis_job_service.py` (978 行) → 任务生命周期拆分
**目标**：`job_lifecycle.py` + `api_key_manager.py` + `result_serializer.py`

**风险**：🟡 中
- 被 API 路由层引用，但边界相对清晰

**迁移步骤**：
1. 抽取 API key 管理逻辑 → `api_key_manager.py`（独立职责，低风险）
2. 抽取结果序列化 → `result_serializer.py`
3. 剩余任务生命周期 → `job_lifecycle.py`

### 3. `expert_tools.py` (1952 行) → 工具定义/执行/财务工具拆分
**目标**：`tool_definitions.py` + `tool_executor.py` + `financial_tools.py`

**风险**：🔴 高
- `TOOL_DEFINITIONS` 被 `get_openai_tools` 引用，`tool_executor` 被全局使用
- Phase 1 已抽出 `tools/registry.py`（治理层），但工具定义和执行器仍在 expert_tools

**迁移步骤**：
1. `TOOL_DEFINITIONS` 常量 → `tools/tool_definitions.py`（纯数据，低风险）
2. `ToolExecutor` 类 → `tools/tool_executor.py`（保留 `tool_executor` 单例 re-export）
3. 财务工具方法（`_exec_financial_data` 等）→ `tools/financial_tools.py`
4. 原 `expert_tools.py` 保留 re-export 兼容层

### 4. `llm_gateway.py` (820 行) → 网关层拆分
**目标**：`provider_chain.py` + `rate_limiter.py` + `response_cache.py`（`role_router.py` 已完成）

**风险**：🟡 中
- `llm_gateway` 单例被全局引用，但内部逻辑边界较清晰

**迁移步骤**：
1. 限流逻辑 → `services/rate_limiter.py`（自适应速率限制，Phase 0 已实现）
2. 响应缓存 → `services/response_cache.py`
3. Provider 链（gemini/deepseek 切换）→ `services/provider_chain.py`
4. `llm_gateway.py` 保留 facade，组合上述模块

### 5. `discussion_service.py` (1133 行) / `agent_orchestrator.py` (1131 行)
**状态**：🟢 大部分逻辑已抽到 Phase 1-3 新模块（dag_engine / context_builder / base_agent）
**建议**：暂不拆分旧文件（仍在使用），等新编排流程（Planner+DAG+BaseAgent）完全接管后，旧文件整体废弃。这比拆分一个即将废弃的文件更合理。

---

## 四、迁移原则（关键）

1. **向后兼容优先**：拆分时保留 re-export 兼容层，确保现有 `from ... import ...` 不中断。
2. **渐进迁移**：一次拆一个职责，验证全量测试通过后再拆下一个。
3. **新代码用新模块**：新增功能直接写在新拆分模块，旧文件只做 re-export。
4. **不拆即将废弃的文件**：`discussion_service.py` / `agent_orchestrator.py` 的核心逻辑已抽到 Phase 1-3 新模块，等新编排流程接管后整体废弃，而非拆分。

---

## 五、建议执行顺序（按风险从低到高）

1. 🟢 **`expert_tools.py` 的 `TOOL_DEFINITIONS` 抽取**（纯数据常量，最低风险）
2. 🟡 **`llm_gateway.py` 的 rate_limiter 抽取**（边界清晰）
3. 🟡 **`analysis_job_service.py` 的 api_key_manager 抽取**（独立职责）
4. 🔴 **`market_data_service.py` 拆分**（高风险，最后做）
5. ⏸️ `discussion_service.py` / `agent_orchestrator.py` 等新流程接管后废弃

---

**文档版本**：文件拆分迁移指引 · 2026-07-10
**说明**：本指引为后续代码维护项，不影响架构功能。Phase 1-7 的架构拆分（编排/上下文/工具治理/模型路由/决策/反思/报告）已全部完成。
