"""PlannerService — 动态规划 Orchestrator (Phase 3, §4.1).

开发指南 §4.1:
  Planner 不只前置规划, 还可在执行中根据进展动态调整 (Magentic-One 范式).
  Flash 出 plan (输入是 stock_profile + 元数据, 非原始数据) → ToolRegistry 映射工具
  → 规则兜底 → 预取数据写 snapshot.

决策示例 (§4.1):
  A股科技股  → Technical[News,Industry] + Fundamental + Sentiment
  港股金融股  → Fundamental + Macro[Risk] + Sentiment
  美股成长股  → Technical + Fundamental + Macro[Valuation]
  数据严重不足 → 仅 Technical (尽力)

v3.1 §6 Phase3: 替换 build_topology(level) 为 Planner 驱动.

设计:
  - 依赖注入 plan_generator: 默认规则兜底 (_rule_based_plan), 可注入 Flash LLM.
  - data_fetch_manifest 经 ToolRegistry.resolve 映射到候选工具.
  - 预取: 标记需要的数据 (实际预取留 DataRouter 衔接, Phase3 先占位).
  - 纯 stdlib + contracts, 可测试不依赖 LLM.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from datetime import datetime

from ..schemas.contracts import (
    ExecutionPlan, AgentSpec, SubAgentSpec, DAGSpec, DataFetchTask, ToolSpec,
)
from ..services.tools.registry import tool_registry

logger = logging.getLogger(__name__)


def detect_market(symbol: str) -> str:
    """归一化市场 (复用 data_providers.base.detect_market 思路, 但无重型依赖)."""
    s = (symbol or "").strip().upper()
    if not s:
        return "Unknown"
    if s.endswith((".SH", ".SS", ".SZ")):
        return "A-Share"
    if s.endswith(".HK"):
        return "HK-Share"
    if s.startswith("^") or s.isalpha():
        return "US-Share"
    # 纯数字
    digits = s.replace(".", "").replace("-", "")
    if digits.isdigit():
        if len(digits) == 6:
            return "A-Share"
        if 4 <= len(digits) <= 5:
            return "HK-Share"
    return "US-Share"


class PlannerService:
    """Orchestrator: 动态规划 + 预取. Flash 出 plan, ToolRegistry 映射工具, 规则兜底."""

    def __init__(self, plan_generator: Optional[Callable] = None,
                 registry=None):
        self._plan_generator = plan_generator  # 可注入 Flash LLM
        self.tools = registry or tool_registry

    async def plan(self, symbol: str, question: str = "",
                   market: str = "", **kwargs) -> ExecutionPlan:
        """生成执行计划: profile → plan → ToolRegistry 映射 → 校验补丁.

        Args:
            symbol: 股票代码
            question: 分析问题
            market: 市场 (空则自动检测)
        """
        mkt = market or detect_market(symbol)
        profile = self._profile(symbol, mkt, kwargs)

        # plan_generator (默认规则兜底, 可注入 Flash LLM)
        if self._plan_generator is not None:
            try:
                raw = await self._plan_generator(profile, question)
            except Exception as e:
                logger.warning("[Planner] plan_generator 失败, 退回规则: %s", e)
                raw = self._rule_based_plan(symbol, mkt, question, profile)
        else:
            raw = self._rule_based_plan(symbol, mkt, question, profile)

        # ToolRegistry 映射: data_type → 候选工具 (按优先级)
        for task in raw.data_fetch_manifest:
            if not task.tools:
                # resolve 返回 list[dict], 转为 ToolSpec 保持契约一致
                resolved = self.tools.resolve(task.data_type)
                task.tools = [ToolSpec(tool_id=r["tool_id"], priority=r["priority"])
                              for r in resolved]

        plan = self._validate_and_patch(raw, profile)
        # 预取 (Phase3 占位: 标记需要; 实际预取留 DataRouter 衔接)
        await self._prefetch(plan.data_fetch_manifest)
        return plan

    # ════════════════════════════════════════════════════════════════════════
    # 股票画像
    # ════════════════════════════════════════════════════════════════════════

    def _profile(self, symbol: str, market: str, kwargs: dict) -> dict:
        """生成股票画像 (供 Planner 决策, 非原始数据)."""
        asset_type = kwargs.get("asset_type", "equity")
        sector = kwargs.get("sector", "")
        data_availability = kwargs.get("data_availability", "normal")
        return {
            "symbol": symbol, "market": market, "asset_type": asset_type,
            "sector": sector, "data_availability": data_availability,
        }

    # ════════════════════════════════════════════════════════════════════════
    # 规则兜底 (开发指南 §4.1 决策示例)
    # ════════════════════════════════════════════════════════════════════════

    def _rule_based_plan(self, symbol: str, market: str, question: str,
                         profile: dict) -> ExecutionPlan:
        """规则生成 ExecutionPlan (默认, 不依赖 LLM).

        根据市场 + 资产类型 + 数据可用性动态选 Agent 数 + 预取数据.
        """
        agents: list[AgentSpec] = []
        fetch: list[DataFetchTask] = []
        plan_id = f"plan_{symbol}_{int(datetime.now().timestamp())}"

        # 通用预取: 行情 + K线
        fetch.append(DataFetchTask(data_type="realtime_quote", symbol=symbol))
        fetch.append(DataFetchTask(data_type="history_kline", symbol=symbol))

        data_avail = profile.get("data_availability", "normal")

        if data_avail == "insufficient":
            # 数据严重不足 → 仅 Technical (尽力)
            agents.append(self._spec("Technical Analyst", symbol, question,
                                     subs=["News Analyst"]))
            fetch.append(DataFetchTask(data_type="news", symbol=symbol))
        elif market == "A-Share":
            # A股科技股 → Technical[News,Industry] + Fundamental + Sentiment
            agents.append(self._spec("Technical Analyst", symbol, question,
                                     subs=["News Analyst", "Industry Analyst"],
                                     depends_on=[]))
            agents.append(self._spec("Fundamental Analyst", symbol, question, depends_on=[]))
            agents.append(self._spec("Sentiment Analyst", symbol, question, depends_on=[]))
            fetch.append(DataFetchTask(data_type="financial_stmt", symbol=symbol))
            fetch.append(DataFetchTask(data_type="news", symbol=symbol))
            fetch.append(DataFetchTask(data_type="industry_data", symbol=symbol))
        elif market == "HK-Share":
            # 港股金融股 → Fundamental + Macro[Risk] + Sentiment
            agents.append(self._spec("Fundamental Analyst", symbol, question, depends_on=[]))
            agents.append(self._spec("Macro Analyst", symbol, question,
                                     subs=["Risk Quantifier"], depends_on=[]))
            agents.append(self._spec("Sentiment Analyst", symbol, question, depends_on=[]))
            fetch.append(DataFetchTask(data_type="financial_stmt", symbol=symbol))
            fetch.append(DataFetchTask(data_type="news", symbol=symbol))
        else:
            # 美股成长股 → Technical + Fundamental + Macro[Valuation]
            agents.append(self._spec("Technical Analyst", symbol, question,
                                     subs=["News Analyst"], depends_on=[]))
            agents.append(self._spec("Fundamental Analyst", symbol, question, depends_on=[]))
            agents.append(self._spec("Macro Analyst", symbol, question,
                                     subs=["Valuation Analyst"], depends_on=[]))
            fetch.append(DataFetchTask(data_type="financial_stmt", symbol=symbol))
            fetch.append(DataFetchTask(data_type="news", symbol=symbol))

        # DAG: 第一层全部并行 (depends_on 空), 无串行依赖
        dag = DAGSpec(parallel_groups=[[a.agent_id for a in agents]])

        return ExecutionPlan(
            plan_id=plan_id, symbol=symbol, market=market,
            data_fetch_manifest=fetch, agent_manifest=agents,
            dag=dag, budget_tokens=30000,
        )

    @staticmethod
    def _spec(role: str, symbol: str, question: str,
              subs: list[str] = None, depends_on: list[str] = None) -> AgentSpec:
        """构造 AgentSpec."""
        sub_specs = [SubAgentSpec(subagent_id=f"{role}#{s}", role=s, as_tool=True)
                     for s in (subs or [])]
        return AgentSpec(
            agent_id=f"{role}@{symbol}",
            role=role, question=question or f"分析 {symbol}",
            subagents=sub_specs,
            depends_on=depends_on or [],
            budget_tokens=8000,
        )

    # ════════════════════════════════════════════════════════════════════════
    # 校验 + 补丁
    # ════════════════════════════════════════════════════════════════════════

    def _validate_and_patch(self, plan: ExecutionPlan, profile: dict) -> ExecutionPlan:
        """规则校验兜底: 确保至少 1 个 Agent, 预取至少 quote/history."""
        if not plan.agent_manifest:
            logger.warning("[Planner] plan 无 Agent, 补 Technical")
            plan.agent_manifest.append(self._spec(
                "Technical Analyst", plan.symbol, plan.question))
        has_quote = any(t.data_type == "realtime_quote" for t in plan.data_fetch_manifest)
        has_hist = any(t.data_type == "history_kline" for t in plan.data_fetch_manifest)
        if not has_quote:
            plan.data_fetch_manifest.append(DataFetchTask(data_type="realtime_quote", symbol=plan.symbol))
        if not has_hist:
            plan.data_fetch_manifest.append(DataFetchTask(data_type="history_kline", symbol=plan.symbol))
        if not plan.symbol:
            plan.symbol = profile.get("symbol", "UNKNOWN")
        if not plan.market:
            plan.market = profile.get("market", "Unknown")
        return plan

    async def _prefetch(self, manifest: list[DataFetchTask]) -> None:
        """预取数据写 snapshot (Phase3 占位: 标记需要).

        实际预取留 DataRouter 衔接; 此处仅记录意图, 不阻塞规划.
        v3.1 §4.6.2 L1 预取层: Planner 预取写入 snapshot, Agent 优先读.
        """
        logger.debug("[Planner] 预取意图: %s",
                     [(t.data_type, t.symbol) for t in manifest])


# 进程级默认实例
planner_service = PlannerService()
