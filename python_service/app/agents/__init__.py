"""ALSA 多智能体 Execution Layer (Phase 2, §4.2).

开发指南 §4.2 SubAgent 框架 + Handoff 双向调用 (★ v3.1 核心新增).

本包把 Phase 0 的 `make_node` 闭包改造为独立 Agent 实例:
  - BaseAgent: 有状态 / 可降级 / 可 handoff 委托 / 可派生 SubAgent
  - Handoff:   双向委托 (OpenAI handoff 范式) + input_filter 治 context
  - EvidenceBus: 替换 history_states dict 的异步证据共享
  - SubAgent:  as_tool 嵌套 (OpenAI Agent.as_tool 范式, 不转移控制权)

v3.1 边界: Phase2 不做动态并行(留 Phase3), 保留固定拓扑但 Agent 实例化 + handoff.

与现有代码衔接 (非破坏):
  - discussion_service.make_node 闭包 → BaseAgent 子类实例 (渐进迁移)
  - history_states dict → EvidenceBus + handoff
  - agent_orchestrator.generate_with_tools → BaseAgent._reason_with_tools (复用)
  - 复用 Phase 1: schemas.contracts / context_builder / tools.registry
"""
