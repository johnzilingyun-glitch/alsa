"""RoleRouter — role→model 路由 + rerun 动态预算 (Phase 4, §6 + §7.2).

开发指南 §6 Phase4:
  "llm_gateway role→model 路由 (Flash 整理 / Pro 推理)"
  - Planner     = Flash (整理/规划, 成本低)
  - Agent 推理   = Pro (技术面/基本面/宏观/情绪分析)
  - Reflection  = Pro (交叉验证/纠错)
  - Decision    = Pro (最终决策)

开发指南 §7.2 rerun 动态预算 (v3.1 修复):
  rerun 时预算上浮 2k 容纳冲突注入, 不再固定预算导致超限.
  ┌──────────────┬─────────┬────────────────┐
  │ Agent        │ 默认预算 │ rerun 预算 (+2k) │
  │ Technical    │ ≤ 8k     │ ≤ 10k           │
  │ Fundamental  │ ≤ 10k    │ ≤ 12k           │
  │ Reflection   │ ≤ 6k     │ ≤ 8k            │
  └──────────────┴─────────┴────────────────┘

设计: 纯配置 + 查询函数, 无重型依赖. 可被 llm_gateway / BaseAgent / ReflectionAgent 复用.
目标: Token 成本 ↓ >50% (Flash 整理 + Pro 仅推理).
"""

from __future__ import annotations

import os
from typing import Optional


# ── Model tier 定义 ─────────────────────────────────────────────────────────
# tier → 具体模型名 (可经环境变量覆盖). 与 llm_gateway.default_model 对齐.
_DEFAULT_FLASH_MODEL = os.getenv("FLASH_MODEL", "gemini-2.5-flash")
_DEFAULT_PRO_MODEL = os.getenv("PRO_MODEL", os.getenv("DEFAULT_LLM_MODEL", "deepseek-v4-pro"))

# role → tier (开发指南: Planner=Flash, Agent/Reflection/Decision=Pro)
ROLE_TIER_MAP: dict[str, str] = {
    # Flash tier: 整理/规划/摘要类 (成本低)
    "Planner": "flash",
    "News Analyst": "flash",        # 新闻提取 (整理类)
    "Industry Analyst": "flash",    # 行业对标 (整理类)
    # Pro tier: 推理类
    "Technical Analyst": "pro",
    "Fundamental Analyst": "pro",
    "Macro Analyst": "pro",
    "Sentiment Analyst": "pro",
    "Risk Quantifier": "pro",
    "Valuation Analyst": "pro",
    "Reflection": "pro",
    "Decision": "pro",
    "Chief Strategist": "pro",
}

# ── 预算定义 (§7.2) ─────────────────────────────────────────────────────────
# role → 默认预算 (tokens). rerun 时 +2k (动态预算, v3.1 修复).
ROLE_DEFAULT_BUDGET: dict[str, int] = {
    "Planner": 4000,                # Flash 规划, 小预算
    "Technical Analyst": 8000,
    "Fundamental Analyst": 10000,
    "Macro Analyst": 8000,
    "Sentiment Analyst": 6000,
    "News Analyst": 4000,
    "Industry Analyst": 4000,
    "Risk Quantifier": 6000,
    "Valuation Analyst": 6000,
    "Reflection": 6000,
    "Decision": 8000,
}
_DEFAULT_BUDGET = 8000
_RERUN_BONUS = int(os.getenv("RERUN_BUDGET_BONUS", "2000"))  # §7.2 +2k


def resolve_tier(role: str) -> str:
    """role → tier (flash / pro). 未知 role 默认 pro (安全)."""
    return ROLE_TIER_MAP.get(role, "pro")


def resolve_model(role: str, tier: Optional[str] = None) -> str:
    """role → 具体模型名 (供 llm_gateway 调用).

    Args:
        role: Agent 角色名
        tier: 显式指定 tier (覆盖 ROLE_TIER_MAP)
    """
    t = tier or resolve_tier(role)
    if t == "flash":
        return _DEFAULT_FLASH_MODEL
    return _DEFAULT_PRO_MODEL


def resolve_budget(role: str, is_rerun: bool = False) -> int:
    """role → token 预算.

    v3.1 §7.2: rerun 时 +2k 容纳冲突注入.
    """
    base = ROLE_DEFAULT_BUDGET.get(role, _DEFAULT_BUDGET)
    if is_rerun:
        return base + _RERUN_BONUS
    return base


def is_flash_role(role: str) -> bool:
    """是否 Flash tier (整理类, 成本低)."""
    return resolve_tier(role) == "flash"


def is_pro_role(role: str) -> bool:
    """是否 Pro tier (推理类)."""
    return resolve_tier(role) == "pro"


# ── 成本估算 (供 observability) ─────────────────────────────────────────────

def estimate_cost_saving(roles_used: list[str]) -> dict:
    """估算 Flash 分层带来的成本节省.

    假设 Flash 成本 ≈ Pro 的 1/10. 统计 Flash 角色占比 → 节省率.
    开发指南目标: Token 成本 ↓ >50%.
    """
    if not roles_used:
        return {"flash_count": 0, "pro_count": 0, "saving_rate": 0.0}
    flash_n = sum(1 for r in roles_used if is_flash_role(r))
    pro_n = len(roles_used) - flash_n
    # 简化: Flash 占比 × 0.9 (相对 Pro 的节省)
    saving = round(flash_n / len(roles_used) * 0.9, 4)
    return {
        "flash_count": flash_n,
        "pro_count": pro_n,
        "saving_rate": saving,
    }
