"""Unified trading-action taxonomy shared by signal extraction consumers.

``normalize_action`` maps free-form LLM recommendation strings (English broker
ratings, Chinese ratings, mixed-case garbage) onto the canonical four-value
action space used across the platform:

    buy | sell | hold | watch

Consumers:
* ``analysis_job_service`` — AnalysisRun.summary_verdict derivation and the
  ``tradingPlan.action`` field extracted from ``<structured_data>``.
* ``report_generator_service`` — recommendation normalization for report UI
  data (wrapped into the BUY/SELL/HOLD display convention).

Lookup order
------------
1. Leading-negation guard → ``watch``
2. Exact match (casefold + strip) → that group
3. Containment match (word boundaries for EN, substring for CJK) → the single
   group hit; multiple conflicting groups → ``watch`` (ambiguous)
4. Default → ``watch``

Limitations (documented on purpose):
* Only PREFIX negation is handled (``不建议买入`` / ``Not Buy`` → watch).
  Mid-sentence negation such as ``买入，但短期不急`` still resolves to buy —
  the extraction layer treats recommendations as short rating labels, so this
  is accepted residual risk.
* The single CJK char ``空`` (required by the sell dictionary) can false-positive
  on strings like ``航空``/``时空``; rating labels rarely contain those tokens.
"""

from __future__ import annotations

import re
from typing import Optional

BUY = "buy"
SELL = "sell"
HOLD = "hold"
WATCH = "watch"

ActionType = str  # one of BUY / SELL / HOLD / WATCH

# --- Exact dictionaries (compared after strip + casefold) --------------------
_EXACT_ACTIONS: dict[str, set[str]] = {
    BUY: {
        "buy", "strong buy", "accumulate", "add",
        "买入", "增持", "加仓", "做多", "长多", "超配",
    },
    SELL: {
        "sell", "strong sell", "reduce", "avoid",
        "卖出", "减持", "清仓", "做空", "看空", "避险", "回避", "低配",
    },
    HOLD: {
        "hold", "neutral", "watch",
        "持有", "观望", "中性",
    },
}

# --- Containment dictionaries -------------------------------------------------
# English tokens use word boundaries so e.g. "buyback" does not match "buy".
_CONTAINS_EN: dict[str, list[re.Pattern[str]]] = {
    BUY: [
        re.compile(r"\bbuy(?:s|ing)?\b"),
        re.compile(r"\boverweight\b"),
        re.compile(r"\baccumulat\w*"),
    ],
    SELL: [
        re.compile(r"\bsell(?:s|ing)?\b"),
        re.compile(r"\bunderweight\b"),
        re.compile(r"\bavoid\w*"),
        re.compile(r"\breduce\b"),
    ],
    HOLD: [
        re.compile(r"\bhold\w*"),
        re.compile(r"\bneutral\b"),
        re.compile(r"\bwatch\w*"),
    ],
}

# CJK tokens use substring containment.
_CONTAINS_ZH: dict[str, list[str]] = {
    BUY: ["买入", "增持", "加仓", "做多", "长多"],
    SELL: ["卖出", "减持", "看空", "做空", "清仓", "避险", "空"],
    HOLD: ["持有", "观望", "中性"],
}

# Prefix negation → conservative watch, so "不建议买入"/"Not Buy" can never
# become a directional signal.
_NEGATION_PREFIX_ZH: tuple[str, ...] = ("不", "非", "别", "勿", "莫", "避免", "暂缓")
_NEGATION_PREFIX_EN = re.compile(r"^(?:not|don'?t|do\s+not|never)\b")


def _starts_with_negation(normalized: str) -> bool:
    if normalized.startswith(_NEGATION_PREFIX_ZH):
        return True
    return bool(_NEGATION_PREFIX_EN.search(normalized))


def normalize_action(text: Optional[str]) -> ActionType:
    """Normalize a free-form recommendation string to buy/sell/hold/watch."""
    if text is None:
        return WATCH
    normalized = str(text).strip().casefold()
    if not normalized:
        return WATCH
    if _starts_with_negation(normalized):
        return WATCH

    for action, words in _EXACT_ACTIONS.items():
        if normalized in words:
            return action

    hits: set[str] = set()
    for action, patterns in _CONTAINS_EN.items():
        if any(p.search(normalized) for p in patterns):
            hits.add(action)
    for action, words in _CONTAINS_ZH.items():
        if any(w in normalized for w in words):
            hits.add(action)

    if len(hits) == 1:
        return next(iter(hits))
    # No hit, or conflicting groups (e.g. "buy or sell") → conservative watch.
    return WATCH
