"""ALSA Execution Engine (Phase 3).

开发指南 §3.1 ③ Execution Layer:
  DAG Engine + SubAgent 框架 (Handoff + Send 并行)

本包实现运行时动态并行 (替代 Phase 0 的固定拓扑 build_topology).
"""
