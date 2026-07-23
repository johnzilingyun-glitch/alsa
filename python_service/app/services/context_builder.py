"""ContextBuilder — 把原始数据压成最小高价值上下文 (Phase 1, §4.5).

开发指南 §4.5 v3.1 修复:
  1. "Never send raw data" → "默认不送 raw, 验证/反思时按需 recall"
  2. 接口分级: 核心接口(Phase1 可用) + 扩展接口(Phase2+ 注入)

核心接口 build_core() 不依赖 EvidenceBus / Memory, Phase1 即可用:
  - market_summary:  K线 → 趋势/MA/MACD/RSI/ATR  (复用 polars_indicators ✅)
  - fundamentals:    财报 → Summary + KeyTables
  - news:            Top5
  - recent_tool_context: 近2轮全文 + 旧轮摘要 + ref  (复用 Phase0 摘要思路 ✅)

扩展接口 build() 在 Phase2+ 注入 evidence, Phase5 注入 memory.
recall() 按需召回原始数据 (验证/反思时用, 非默认行为).

转换规则 (§4.5 关键表):
  ┌───────────────┬──────────────────────────────┬─────────┬──────────────┐
  │ 3000 K线       │ 趋势+MA+MACD+RSI+ATR         │ 否      │ polars ✅    │
  │ 100 新闻        │ Top5                          │ 否      │ 本模块新增    │
  │ 200 页财报      │ Summary+KeyTables             │ 否      │ 本模块新增    │
  │ 工具历史        │ 近2轮全文+旧轮摘要+ref        │ 否(recall时是) │ Phase0 ✅ │
  │ 其他 Agent 证据 │ 结构化 Evidence 列表          │ 否      │ EvidenceBus  │
  └───────────────┴──────────────────────────────┴─────────┴──────────────┘

预算感知: budget_tokens 小时优先保留 market_summary, 降级 news/fundamentals 细节.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 默认预算分级 (开发指南 §7.2)
_BUDGET_LARGE = 10000   # ≥10k: 全量
_BUDGET_MEDIUM = 6000   # 6-10k: 中量
# <6k: 精简 (仅 market_summary + question)


def _extractive_summary(text: str, max_chars: int = 600) -> str:
    """抽取式摘要: 保留表头 + 高信号行 (表格/数值/结构标记).

    复用 agent_orchestrator._summarize_tool_result 的思路, 自包含实现避免重依赖.
    全文仍在外置存储, 可经 recall() 回调.
    """
    if not text:
        return text
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    header = [l for l in lines[:2] if l.strip()]
    body = lines[2:] if len(lines) > 2 else []
    out = list(header)
    used = sum(len(l) for l in out)
    for ln in body:
        s = ln.strip()
        if not s:
            continue
        is_signal = ("|" in ln) or bool(re.search(r"\d", ln)) or s.startswith(("##", "- ", "• ", "* "))
        if not is_signal:
            continue
        if used + len(ln) + 1 > max_chars:
            break
        out.append(ln)
        used += len(ln) + 1
    return "\n".join(out)


class ContextBuilder:
    """把 Snapshot 原始数据压成最小高价值上下文.

    默认不送 raw, 按需 recall. 核心接口不依赖 EvidenceBus/Memory.
    """

    def __init__(self):
        # 外置存储引用 (recall 时用). 实际由 Snapshot.store 提供.
        self._store_ref: Optional[dict] = None

    # ════════════════════════════════════════════════════════════════════════
    # 核心接口 (Phase1 可用, 无 EvidenceBus/Memory 依赖)
    # ════════════════════════════════════════════════════════════════════════

    def build_core(self, question: str, snapshot: Any, budget_tokens: int = 8000) -> dict:
        """构建核心上下文 (不送 raw 数据).

        Returns dict:
          question, market_summary, fundamentals, news, recent_tool_context
        """
        ctx: dict = {
            "question": question,
            "market_summary": self._summarize_market(snapshot, budget_tokens),
        }
        # 预算分级: 中等以上才带 fundamentals/news 细节
        if budget_tokens >= _BUDGET_MEDIUM:
            ctx["fundamentals"] = self._key_tables(snapshot, budget_tokens)
        if budget_tokens >= _BUDGET_LARGE:
            ctx["news"] = self._top_n_news(snapshot, n=5)
        else:
            ctx["news"] = self._top_n_news(snapshot, n=3)
        ctx["recent_tool_context"] = self._recent_tool_summary(n=2)
        # 记录存储引用供 recall
        if hasattr(snapshot, "store"):
            self._store_ref = snapshot.store
        return ctx

    # ════════════════════════════════════════════════════════════════════════
    # 扩展接口 (Phase2+ 注入 evidence, Phase5 注入 memory)
    # ════════════════════════════════════════════════════════════════════════

    def build(
        self,
        question: str,
        snapshot: Any,
        evidence: Any = None,
        memory: Any = None,
        budget_tokens: int = 8000,
    ) -> dict:
        """构建完整上下文 (核心 + 扩展注入).

        Phase2+: evidence (EvidenceBus 证据) 注入
        Phase5:  memory (session.tail) 注入
        """
        ctx = self.build_core(question, snapshot, budget_tokens)
        if evidence:
            ctx["evidence"] = evidence
        if memory is not None and hasattr(memory, "session"):
            ctx["recent_context"] = memory.session.tail(5)
        return ctx

    def recall(self, data_ref: str) -> str:
        """按需召回原始数据 (验证/反思时用). 非默认行为.

        开发指南 §4.5: "默认不送 raw, 验证/反思时按需 recall".
        """
        if self._store_ref is not None:
            return self._store_ref.get(data_ref, "")
        return ""

    # ════════════════════════════════════════════════════════════════════════
    # 渲染为紧凑 Prompt 字符串
    # ════════════════════════════════════════════════════════════════════════

    def render(self, ctx: dict, max_chars: int = 4000) -> str:
        """把 build() 产出的 dict 渲染为紧凑的 prompt 片段."""
        parts = [f"## Question\n{ctx.get('question', '')}"]
        ms = ctx.get("market_summary")
        if ms:
            parts.append(f"## Market Summary\n{ms}")
        fund = ctx.get("fundamentals")
        if fund:
            parts.append(f"## Fundamentals\n{fund}")
        news = ctx.get("news")
        if news:
            parts.append("## News (Top)")
            parts.extend(f"- {n}" if isinstance(n, str) else f"- {n}" for n in news[:5])
        rtc = ctx.get("recent_tool_context")
        if rtc:
            parts.append(f"## Recent Tool Context\n{rtc}")
        ev = ctx.get("evidence")
        if ev:
            parts.append(f"## Evidence\n{ev}")
        text = "\n\n".join(parts)
        if len(text) > max_chars:
            text = _extractive_summary(text, max_chars)
        return text

    # ════════════════════════════════════════════════════════════════════════
    # 原始数据 → 压缩形态 的转换规则
    # ════════════════════════════════════════════════════════════════════════

    def _summarize_market(self, snapshot: Any, budget: int) -> str:
        """K线 → 趋势/MA/MACD/RSI/ATR (复用 polars_indicators.compute_indicator_frame)."""
        history = getattr(snapshot, "history", None)
        if history is None:
            return ""
        rows = history if isinstance(history, list) else []
        if not rows:
            return ""
        try:
            from ..quant.polars_indicators import compute_indicator_frame
            df = compute_indicator_frame(rows)
            if df is None or df.height == 0:
                return ""
            last = df.tail(1)
            # 抽取最近一行关键指标, 组装紧凑摘要
            def _val(col):
                try:
                    v = last.select(col).item()
                    return None if v is None else (round(float(v), 4) if isinstance(v, (int, float)) else v)
                except Exception:
                    return None
            close = _val("close")
            ma5, ma20, ma60 = _val("ma_5"), _val("ma_20"), _val("ma_60")
            ma50, ma150, ma200 = _val("ma_50"), _val("ma_150"), _val("ma_200")
            ma200_prev = None
            if df.height > 1:
                try:
                    ma200_prev = df.tail(2).select("ma_200").head(1).item()
                    if ma200_prev is not None:
                        ma200_prev = round(float(ma200_prev), 4)
                except Exception:
                    pass
            macd, macd_sig, macd_hist = _val("macd"), _val("macd_signal"), _val("macd_hist")
            rsi = _val("rsi_14") or _val("rsi")
            atr = _val("atr_14") or _val("atr")
            boll_up, boll_lo = _val("bollinger_upper"), _val("bollinger_lower")
            trend = self._trend_label(close, ma5, ma20, ma60)
            lines = [
                f"price={close} trend={trend}",
                f"MA5={ma5} MA20={ma20} MA60={ma60}",
            ]
            if ma50 is not None:
                lines.append(f"MA50={ma50} MA150={ma150} MA200={ma200} MA200_prev={ma200_prev}")
            if macd is not None:
                lines.append(f"MACD={macd} signal={macd_sig} hist={macd_hist}")
            if rsi is not None:
                lines.append(f"RSI14={rsi} {'超买' if rsi and rsi > 70 else '超卖' if rsi and rsi < 30 else ''}".strip())
            if atr is not None:
                lines.append(f"ATR={atr}")
            if boll_up is not None:
                lines.append(f"BOLL[{boll_lo}, {boll_up}]")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("[ContextBuilder] market summary 失败: %s", e)
            return ""

    @staticmethod
    def _trend_label(close, ma5, ma20, ma60) -> str:
        """根据均线排列判断趋势."""
        vals = [v for v in (close, ma5, ma20, ma60) if v is not None]
        if len(vals) < 3:
            return "unknown"
        if close and ma5 and ma20 and ma60:
            if close > ma5 > ma20 > ma60:
                return "强势多头"
            if close < ma5 < ma20 < ma60:
                return "弱势空头"
            if ma5 > ma20:
                return "短多"
            if ma5 < ma20:
                return "短空"
        return "震荡"

    def _key_tables(self, snapshot: Any, budget: int) -> str:
        """财报 → Summary + KeyTables (紧凑)."""
        fin = getattr(snapshot, "financials", None)
        if not fin or not isinstance(fin, dict):
            return ""
        # 取核心字段, 丢弃长文本
        core_keys = ["revenue", "net_profit", "roe", "gross_margin", "net_margin",
                     "grossMarginQoQ", "grossMarginYoY",
                     "pe", "pb", "ps", "debt_ratio", "eps", "market_cap",
                     "营业收入", "净利润", "净资产收益率", "毛利率", "净利率",
                     "市盈率", "市净率", "资产负债率"]
        lines = []
        for k in core_keys:
            if k in fin and fin[k] is not None:
                v = fin[k]
                if isinstance(v, (int, float)):
                    v = round(float(v), 4)
                lines.append(f"{k}={v}")
        # 若有嵌套 table, 取首表前 5 行
        for k, v in fin.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                lines.append(f"[{k}]")
                for row in v[:5]:
                    cells = [f"{rk}={rv}" for rk, rv in list(row.items())[:4]]
                    lines.append("  " + " ".join(cells))
                break
        return "\n".join(lines) if lines else ""

    def _top_n_news(self, snapshot: Any, n: int = 5) -> list:
        """新闻 → Top N (标题+日期)."""
        news = getattr(snapshot, "news", None)
        if not news or not isinstance(news, list):
            return []
        out = []
        for item in news[:n]:
            if isinstance(item, dict):
                title = item.get("title") or item.get("headline") or ""
                date = item.get("date") or item.get("time") or ""
                out.append(f"{date} {title}".strip())
            elif isinstance(item, str):
                out.append(item)
        return out

    def _recent_tool_summary(self, n: int = 2) -> str:
        """近 N 轮工具结果摘要 (复用 Phase0 外置存储 + 摘要).

        Phase1: 返回占位, 实际由 agent_orchestrator 的 tool_result_store 提供.
        Phase2+: BaseAgent 注入 recent tool store 后填充.
        """
        if self._store_ref is None:
            return ""
        # 取最近 n 条 ref 的摘要
        items = list(self._store_ref.items())[-n:] if self._store_ref else []
        if not items:
            return ""
        lines = []
        for ref, full in items:
            summary = _extractive_summary(full, max_chars=400)
            lines.append(f"[ref={ref}] {summary}")
        return "\n".join(lines)


# 进程级单例
context_builder = ContextBuilder()
