"""工具前置条件校验 (Phase 1, §4.6.1 / §4.6.3 L3 层).

开发指南 §4.6.1 PRECONDITIONS:
  - markets: 工具仅支持特定市场 (如 financial_data 不支持港股)
  - requires: 必填参数 (如 macro_query 需要 symbol)
  - requires_approval: 仅 emergency 调用 (如 deep_scrape)

开发指南 §4.6.3 无效调用场景与拦截:
  ┌──────────────────────────────────┬───────────────────────────────────────┐
  │ 港股 symbol 调 A股专用工具        │ precondition markets 校验             │
  │ 缺少 symbol 调 macro_query        │ precondition requires 校验            │
  │ LLM 反复请求相同数据              │ L2 缓存命中 (shared_cache)            │
  │ snapshot 已有数据仍调 tool         │ Agent 工具列表标记 snapshot_available │
  │ deep_scrape 被频繁调用            │ requires_approval=True                │
  │ 工具返回空/garbage                │ result.is_valid 校验 → fallback       │
  └──────────────────────────────────┴───────────────────────────────────────┘

设计: 校验返回 (ok, reason). 失败时记录无效调用日志 (可关, TOOL_INVALID_CALL_LOG).
"""

from __future__ import annotations

import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 市场标识归一化 (兼容 MarketType.value 与中文)
_MARKET_ALIASES = {
    "A-SHARE": "A股", "A_SHARE": "A股", "A股": "A股", "ASH": "A股", "A": "A股",
    "HK-SHARE": "港股", "HK_SHARE": "港股", "港股": "港股", "HK": "港股",
    "US-SHARE": "美股", "US_SHARE": "美股", "美股": "美股", "US": "美股",
    "UNKNOWN": "", "": "",
}


def normalize_market(market: str) -> str:
    """归一化市场标识为中文标准 (A股/港股/美股/空)."""
    if not market:
        return ""
    return _MARKET_ALIASES.get(market.strip().upper().replace("-", "_"), market)


# ── 前置条件定义 (开发指南 §4.6.1) ──────────────────────────────────────────
# 每个工具的能力门控: 支持哪些市场 / 必填哪些参数 / 是否需审批.
PRECONDITIONS: dict[str, dict] = {
    # financial_data 仅支持 A股/美股 (港股财务数据接口不可用)
    "financial_data": {
        "markets": ["A股", "美股"],
        "requires": ["symbol"],
    },
    # finance_query / business_query 需要 symbol 或 query
    "finance_query": {"requires_any": ["symbol", "query"]},
    "business_query": {"requires_any": ["symbol", "query"]},
    "valuation_query": {"requires": ["symbol"]},
    # macro_query 需要 symbol (开发指南示例)
    "macro_query": {"requires": ["symbol"]},
    # 抓取类需审批 (仅 emergency, web_search 失败后)
    "deep_scrape": {
        "requires": ["url"],
        "requires_approval": True,
    },
    # 实时行情: 全市场支持, 但需 symbol
    "fetch_realtime_quote": {"requires": ["symbol"]},
    "fetch_history": {"requires": ["symbol"]},
}


def validate_precondition(
    tool_id: str,
    params: dict,
    market: str = "",
    *,
    approval_granted: bool = False,
) -> tuple[bool, str]:
    """调用前校验: 市场匹配 / 参数完整 / 能力门控.

    Returns:
        (True, "")  — 校验通过
        (False, reason) — 拦截, reason 说明原因
    """
    pre = PRECONDITIONS.get(tool_id)
    if not pre:
        return True, ""  # 无前置条件定义 → 放行

    m = normalize_market(market)

    # 1. 市场匹配
    if "markets" in pre and m:
        if m not in pre["markets"]:
            reason = f"{tool_id} 不支持市场 {m} (仅 {pre['markets']})"
            _log_invalid(tool_id, params, reason)
            return False, reason

    # 2. 必填参数 (全部)
    if "requires" in pre:
        for req in pre["requires"]:
            val = params.get(req)
            if val is None or (isinstance(val, str) and not val.strip()):
                reason = f"{tool_id} 缺少必填参数 {req}"
                _log_invalid(tool_id, params, reason)
                return False, reason

    # 3. 必填参数 (任一即可)
    if "requires_any" in pre:
        if not any(params.get(r) for r in pre["requires_any"]):
            reason = f"{tool_id} 至少需要参数之一 {pre['requires_any']}"
            _log_invalid(tool_id, params, reason)
            return False, reason

    # 4. 审批门控
    if pre.get("requires_approval") and not approval_granted:
        reason = f"{tool_id} 需要审批 (仅 emergency 场景, web_search 失败后)"
        _log_invalid(tool_id, params, reason)
        return False, reason

    return True, ""


def _log_invalid(tool_id: str, params: dict, reason: str) -> None:
    """记录无效调用 (可关, TOOL_INVALID_CALL_LOG=true)."""
    if os.getenv("TOOL_INVALID_CALL_LOG", "true").lower() == "true":
        # 不记录敏感参数全文, 只记录 key
        keys = list(params.keys())
        logger.warning("[Precondition] 拦截无效调用 tool=%s params_keys=%s reason=%s",
                       tool_id, keys, reason)


def is_valid_result(data: Any) -> bool:
    """校验工具返回是否有效 (非空/garbage 拦截).

    开发指南 §4.6.3: "工具返回空/garbage → result.is_valid 校验, 失败则降级".
    """
    if data is None:
        return False
    if isinstance(data, str):
        s = data.strip()
        if not s:
            return False
        # 明显错误标记
        low = s.lower()
        if low in ("error", "null", "none", "nan", "n/a", "[]", "{}"):
            return False
        if low.startswith(("error:", "exception:", "traceback")):
            return False
        return True
    if isinstance(data, (list, dict)):
        # 空集合视为无效 (调用成功但无数据)
        return len(data) > 0
    return True
