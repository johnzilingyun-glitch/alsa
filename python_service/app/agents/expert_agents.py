"""SubAgent as_tool 框架 + 具体角色 Agent (Phase 2, §4.2.1).

开发指南 §4.2.1 两级树结构:
  Technical Agent ──as_tool──► News SubAgent      (取新闻证据)
                  ──as_tool──► Industry SubAgent  (取行业证据)
  Macro Agent     ──as_tool──► Risk SubAgent      (风险评估)
                  ──as_tool──► Valuation SubAgent (估值)
  Technical Agent ──handoff──► Fundamental Agent  (发现需基本面印证时委托)

SubAgent as_tool (OpenAI Agent.as_tool 范式):
  父 Agent 调用时不转移控制权, 结果回灌父 Agent 上下文.
  BaseAgent.run_as_tool 已实现通用入口, 此处为聚焦角色的子类.

具体 Agent 子类 (替换 discussion_service 的角色 prompt):
  - TechnicalAgent  (+ News/Industry SubAgent, handoff→Fundamental)
  - FundamentalAgent
  - MacroAgent      (+ Risk/Valuation SubAgent)
  - SentimentAgent

每个子类覆盖 role_prompt 实现角色专属分析框架.
"""

from __future__ import annotations

from .base_agent import BaseAgent
from .handoff import make_handoff


# ════════════════════════════════════════════════════════════════════════
# SubAgent (as_tool, 不转移控制权)
# ════════════════════════════════════════════════════════════════════════

class NewsSubAgent(BaseAgent):
    """新闻证据 SubAgent (Technical 派生). 取新闻→提取可追溯证据."""

    role = "News Analyst"

    def role_prompt(self, question: str, ctx: dict) -> str:
        news = ctx.get("news", [])
        news_block = "\n".join(f"- {n}" for n in news) if news else "(无新闻数据)"
        return (
            f"# Role: News Analyst (SubAgent)\n"
            f"# Task\n{question}\n\n"
            f"# News\n{news_block}\n\n"
            f"# Instruction\n从上述新闻提取可追溯证据. 每条证据标注 stance(bullish/bearish/neutral) "
            f"和 confidence. 输出结构化 JSON."
        )


class IndustrySubAgent(BaseAgent):
    """行业对比 SubAgent (Technical 派生). 同业对标→行业证据."""

    role = "Industry Analyst"

    def role_prompt(self, question: str, ctx: dict) -> str:
        fund = ctx.get("fundamentals", "(无行业数据)")
        return (
            f"# Role: Industry Analyst (SubAgent)\n"
            f"# Task\n{question}\n\n"
            f"# Industry/Fundamentals\n{fund}\n\n"
            f"# Instruction\n做同业对标分析, 提取行业定位证据. 输出结构化 JSON."
        )


class RiskSubAgent(BaseAgent):
    """风险量化 SubAgent (Macro 派生). VaR/仓位/止损/尾部风险."""

    role = "Risk Quantifier"

    def role_prompt(self, question: str, ctx: dict) -> str:
        ms = ctx.get("market_summary", "(无行情)")
        return (
            f"# Role: Risk Quantifier (SubAgent)\n"
            f"# Task\n{question}\n\n"
            f"# Market\n{ms}\n\n"
            f"# Instruction\n量化风险: VaR/最大回撤/仓位建议/止损位/尾部风险. "
            f"输出结构化 JSON, risk[] 必填."
        )


class ValuationSubAgent(BaseAgent):
    """估值 SubAgent (Macro 派生). PE/PB/PS/EV 模型."""

    role = "Valuation Analyst"

    def role_prompt(self, question: str, ctx: dict) -> str:
        fund = ctx.get("fundamentals", "(无财务数据)")
        return (
            f"# Role: Valuation Analyst (SubAgent)\n"
            f"# Task\n{question}\n\n"
            f"# Financials\n{fund}\n\n"
            f"# Instruction\n多模型估值(PE/PB/PS/EV-EBITDA/DCF), 给出合理区间与当前偏离度. "
            f"输出结构化 JSON."
        )


# ════════════════════════════════════════════════════════════════════════
# 具体 Agent (替换 discussion_service 角色)
# ════════════════════════════════════════════════════════════════════════

class TechnicalAgent(BaseAgent):
    """技术面 Agent + News/Industry SubAgent, 可 handoff→Fundamental.

    对应 discussion_service 的 "Technical Analyst".
    """

    role = "Technical Analyst"

    def default_subagents(self) -> list[BaseAgent]:
        return [NewsSubAgent(agent_id="Technical#News"),
                IndustrySubAgent(agent_id="Technical#Industry")]

    def default_handoffs(self) -> list:
        # handoff → Fundamental Agent (发现需基本面印证时委托)
        return [make_handoff(
            target_role="Fundamental Analyst",
            input_filter="summary_only",
            tool_description="Handoff to Fundamental Analyst when technical signals need fundamental confirmation (e.g. breakout without earnings support).",
        )]

    def role_prompt(self, question: str, ctx: dict) -> str:
        ms = ctx.get("market_summary", "(无行情摘要)")
        ev = ctx.get("evidence", "")
        return (
            f"# Role: Technical Analyst\n"
            f"# Task\n{question}\n\n"
            f"# Market Summary (K线→趋势/MA/MACD/RSI/ATR)\n{ms}\n\n"
            + (f"# Other Agents' Evidence\n{ev}\n\n" if ev else "")
            + f"# Instruction\n基于技术指标分析趋势/支撑阻力/动量. "
            f"可调用 call_news_analyst / call_industry_analyst 取补充证据; "
            f"若技术信号需基本面印证, 调用 transfer_to_fundamental_analyst. "
            f"输出结构化 JSON."
        )


class FundamentalAgent(BaseAgent):
    """基本面 Agent. 对应 "Fundamental Analyst"."""

    role = "Fundamental Analyst"

    def role_prompt(self, question: str, ctx: dict) -> str:
        fund = ctx.get("fundamentals", "(无财务数据)")
        ev = ctx.get("evidence", "")
        return (
            f"# Role: Fundamental Analyst\n"
            f"# Task\n{question}\n\n"
            f"# Fundamentals (Summary+KeyTables)\n{fund}\n\n"
            + (f"# Other Agents' Evidence\n{ev}\n\n" if ev else "")
            + f"# Instruction\n分析营收/利润/ROE/现金流/负债质量, 评估基本面健康度. "
            f"输出结构化 JSON, evidence[] 含 stance."
        )


class MacroAgent(BaseAgent):
    """宏观 Agent + Risk/Valuation SubAgent. 对应 "Macro Analyst"."""

    role = "Macro Analyst"

    def default_subagents(self) -> list[BaseAgent]:
        return [RiskSubAgent(agent_id="Macro#Risk"),
                ValuationSubAgent(agent_id="Macro#Valuation")]

    def role_prompt(self, question: str, ctx: dict) -> str:
        ms = ctx.get("market_summary", "(无行情)")
        fund = ctx.get("fundamentals", "")
        ev = ctx.get("evidence", "")
        return (
            f"# Role: Macro Analyst\n"
            f"# Task\n{question}\n\n"
            f"# Market\n{ms}\n\n"
            + (f"# Fundamentals\n{fund}\n\n" if fund else "")
            + (f"# Other Agents' Evidence\n{ev}\n\n" if ev else "")
            + f"# Instruction\n宏观+估值+风险综合视角. "
            f"可调用 call_risk_quantifier / call_valuation_analyst. "
            f"输出结构化 JSON."
        )


class SentimentAgent(BaseAgent):
    """情绪面 Agent. 对应 "Sentiment Analyst"."""

    role = "Sentiment Analyst"

    def role_prompt(self, question: str, ctx: dict) -> str:
        news = ctx.get("news", [])
        news_block = "\n".join(f"- {n}" for n in news) if news else "(无新闻)"
        ev = ctx.get("evidence", "")
        return (
            f"# Role: Sentiment Analyst\n"
            f"# Task\n{question}\n\n"
            f"# News\n{news_block}\n\n"
            + (f"# Other Agents' Evidence\n{ev}\n\n" if ev else "")
            + f"# Instruction\n分析市场情绪/舆情/资金流向/多空力量. "
            f"输出结构化 JSON."
        )


# ── Agent 工厂 (供 Planner/编排用) ──────────────────────────────────────────

_AGENT_CLASSES = {
    "Technical Analyst": TechnicalAgent,
    "Fundamental Analyst": FundamentalAgent,
    "Macro Analyst": MacroAgent,
    "Sentiment Analyst": SentimentAgent,
    "News Analyst": NewsSubAgent,
    "Industry Analyst": IndustrySubAgent,
    "Risk Quantifier": RiskSubAgent,
    "Valuation Analyst": ValuationSubAgent,
}


def create_agent(role: str, **kwargs) -> BaseAgent:
    """按角色名创建 Agent 实例. 未知角色返回 BaseAgent."""
    cls = _AGENT_CLASSES.get(role, BaseAgent)
    return cls(agent_id=kwargs.pop("agent_id", role), **kwargs)
