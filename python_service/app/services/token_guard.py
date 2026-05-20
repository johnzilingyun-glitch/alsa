"""
Token Guard — Defensive middleware to prevent local tools from returning excessive data to LLM.

Architecture:
  1. Per-tool hard limits (MAX chars/rows) that cannot be overridden by LLM parameters
  2. Global per-round token budget enforcement across all tool calls
  3. Structured output compression (field whitelist + text truncation)
  4. Emergency circuit breaker when cumulative tool output exceeds budget

Usage:
  from .token_guard import token_guard, GuardConfig

  # Decorate tool execution:
  result = token_guard.enforce(tool_name, raw_output)

  # Or use per-tool configs:
  @token_guard.limit(max_chars=3000, max_rows=5)
  async def my_tool(...):
      ...
"""

import json
from dataclasses import dataclass, field
from typing import Optional


# ────────────── CONFIGURATION ──────────────

@dataclass
class ToolLimit:
    """Per-tool hard limits. LLM cannot override these."""
    max_chars: int = 4000          # Hard character cap for tool output
    max_rows: int = 10             # Max data rows/items returned
    max_field_chars: int = 200     # Max chars per text field (summaries, content)
    max_fields_per_row: int = 8    # Max key-value pairs per data row


@dataclass
class GuardConfig:
    """Global token guard configuration."""
    # Per-round budget (all tool calls in one round combined)
    round_budget_chars: int = 25000       # ~6000 tokens total per round
    # Per-tool defaults (overridable per tool)
    default_limit: ToolLimit = field(default_factory=ToolLimit)
    # Tool-specific overrides
    tool_limits: dict = field(default_factory=dict)
    # Emergency breaker: if single tool output exceeds this, hard truncate
    emergency_max_chars: int = 8000       # Absolute max for any single tool


# Default configuration tuned for DeepSeek (128k context, ~$1/M input tokens)
DEFAULT_CONFIG = GuardConfig(
    round_budget_chars=25000,
    default_limit=ToolLimit(max_chars=4000, max_rows=10, max_field_chars=200),
    tool_limits={
        # Search tools: compact, many results but short
        "web_search":          ToolLimit(max_chars=3000, max_rows=5, max_field_chars=300),
        "news_search":         ToolLimit(max_chars=4000, max_rows=8, max_field_chars=300),
        "announcement_search": ToolLimit(max_chars=3000, max_rows=8, max_field_chars=250),
        "report_search":       ToolLimit(max_chars=3500, max_rows=8, max_field_chars=300),
        # Deep scrape: single page, needs more room
        "deep_scrape":         ToolLimit(max_chars=5000, max_rows=1, max_field_chars=5000),
        # Financial data: structured, can be large with multiple sections
        "financial_data":      ToolLimit(max_chars=5000, max_rows=6, max_field_chars=500),
        # Knowledge base: concise
        "knowledge_search":    ToolLimit(max_chars=2500, max_rows=10, max_field_chars=300),
        # Iwencai query tools: structured data
        "macro_query":         ToolLimit(max_chars=3000, max_rows=10, max_field_chars=200),
        "business_query":      ToolLimit(max_chars=3000, max_rows=10, max_field_chars=200),
        "finance_query":       ToolLimit(max_chars=3000, max_rows=10, max_field_chars=200),
        "management_query":    ToolLimit(max_chars=3000, max_rows=10, max_field_chars=200),
        # Computation tools: predictable size, generous limit
        "dcf_calculator":      ToolLimit(max_chars=3000, max_rows=20, max_field_chars=500),
        "position_sizer":      ToolLimit(max_chars=2000, max_rows=10, max_field_chars=500),
        "kelly_calculator":    ToolLimit(max_chars=1500, max_rows=5, max_field_chars=500),
        "beat_miss_scorer":    ToolLimit(max_chars=2500, max_rows=15, max_field_chars=500),
        "comps_valuation":     ToolLimit(max_chars=3000, max_rows=15, max_field_chars=500),
        "pillar_scorer":       ToolLimit(max_chars=2500, max_rows=15, max_field_chars=500),
        "dupont_decomposition": ToolLimit(max_chars=2000, max_rows=10, max_field_chars=500),
        "minervini_stage":     ToolLimit(max_chars=2500, max_rows=15, max_field_chars=500),
        "earnings_quality_audit": ToolLimit(max_chars=2500, max_rows=10, max_field_chars=500),
        "drawdown_scenario":   ToolLimit(max_chars=3000, max_rows=15, max_field_chars=500),
        "risk_reward":         ToolLimit(max_chars=1500, max_rows=5, max_field_chars=500),
        "stop_loss_validator": ToolLimit(max_chars=2000, max_rows=10, max_field_chars=500),
        "cagr_calculator":     ToolLimit(max_chars=1500, max_rows=5, max_field_chars=500),
    }
)


# ────────────── TOKEN GUARD ENGINE ──────────────

class TokenGuard:
    """Enforces token budget and hard limits on tool outputs."""

    def __init__(self, config: Optional[GuardConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self._round_chars_used = 0
        self._round_tool_count = 0

    def reset_round(self):
        """Reset per-round budget tracking. Call at start of each tool-calling round."""
        self._round_chars_used = 0
        self._round_tool_count = 0

    @property
    def round_budget_remaining(self) -> int:
        return max(0, self.config.round_budget_chars - self._round_chars_used)

    @property
    def round_stats(self) -> dict:
        return {
            "tools_called": self._round_tool_count,
            "chars_used": self._round_chars_used,
            "chars_remaining": self.round_budget_remaining,
            "budget_pct": round(self._round_chars_used / self.config.round_budget_chars * 100, 1),
        }

    def get_limit(self, tool_name: str) -> ToolLimit:
        """Get the hard limit config for a specific tool."""
        return self.config.tool_limits.get(tool_name, self.config.default_limit)

    def enforce(self, tool_name: str, raw_output: str) -> str:
        """
        Apply defensive enforcement to a tool's raw output.
        
        1. Hard truncate if exceeds per-tool max_chars
        2. Hard truncate if exceeds remaining round budget
        3. Emergency breaker if exceeds absolute max
        4. Track cumulative usage
        
        Returns: potentially truncated output string
        """
        if not raw_output:
            return raw_output

        limit = self.get_limit(tool_name)
        original_len = len(raw_output)
        output = raw_output

        # Step 1: Per-tool hard char limit
        effective_max = min(limit.max_chars, self.config.emergency_max_chars)

        # Step 2: Round budget constraint (allow at least 1000 chars for any tool)
        budget_max = max(1000, self.round_budget_remaining)
        effective_max = min(effective_max, budget_max)

        # Step 3: Truncate if needed
        if len(output) > effective_max:
            # Smart truncation: try to cut at a line boundary
            truncated = output[:effective_max]
            last_newline = truncated.rfind('\n', effective_max - 200)
            if last_newline > effective_max * 0.8:
                truncated = truncated[:last_newline]
            
            output = truncated + f"\n\n... [truncated: {original_len} → {len(truncated)} chars, tool budget limit]"

        # Step 4: Track usage
        self._round_chars_used += len(output)
        self._round_tool_count += 1

        # Log if truncation happened
        if len(output) < original_len:
            savings_pct = round((1 - len(output) / original_len) * 100, 1)
            print(f"  [TokenGuard] {tool_name}: {original_len} → {len(output)} chars (-{savings_pct}%) | Round: {self.round_stats['budget_pct']}% used")

        return output

    def enforce_params(self, tool_name: str, params: dict) -> dict:
        """
        Defensively override parameters that control data volume.
        Call BEFORE executing the tool to clamp limit/count params.
        
        Returns: sanitized params dict
        """
        limit = self.get_limit(tool_name)
        
        # Clamp any limit-like parameters
        limit_keys = ["limit", "max_results", "top_k", "count", "num_results", "page_size"]
        for key in limit_keys:
            if key in params:
                original = params[key]
                if isinstance(original, (int, float)):
                    clamped = min(int(original), limit.max_rows)
                    if clamped != original:
                        print(f"  [TokenGuard] {tool_name}: clamped {key} from {original} → {clamped}")
                    params[key] = clamped
        
        return params


# ────────────── UTILITY: Compact JSON serialization ──────────────

def compact_json(data, ensure_ascii=False) -> str:
    """Serialize to minimal JSON — no extra whitespace, maximizes token efficiency."""
    return json.dumps(data, ensure_ascii=ensure_ascii, separators=(',', ':'))


def slim_dict(d: dict, whitelist: list, max_field_chars: int = 200) -> dict:
    """
    Extract only whitelisted fields from a dict, truncating text values.
    
    Args:
        d: Source dictionary
        whitelist: List of allowed field names
        max_field_chars: Max characters per string field
    """
    result = {}
    for key in whitelist:
        if key in d:
            val = d[key]
            if isinstance(val, str) and len(val) > max_field_chars:
                val = val[:max_field_chars] + "…"
            result[key] = val
    return result


def slim_list(items: list, max_items: int, whitelist: list = None, max_field_chars: int = 200) -> list:
    """
    Slice a list to max_items and optionally whitelist fields per item.
    
    Args:
        items: Source list
        max_items: Hard cap on number of items
        whitelist: If provided, filter dict items to these fields only
        max_field_chars: Max characters per string field
    """
    sliced = items[:max_items]
    if whitelist:
        return [slim_dict(item, whitelist, max_field_chars) for item in sliced if isinstance(item, dict)]
    return sliced


# ────────────── SINGLETON ──────────────

token_guard = TokenGuard()
