"""DecisionAgent — 决策层 (Phase 4, §6, ⑥ Decision Layer).

开发指南 §6 Phase4:
  "Chief Strategist 输入改 Evidence+Critique"
  ⑥ Decision Layer · Chief Strategist (Pro)
    基于 AggregatedEvidence + CritiqueResult → FinalDecision

设计:
  - 输入: AggregatedEvidence (Phase 3 聚合) + CritiqueResult (Phase 4 反思) + AgentResult[]
  - 输出: FinalDecision (最终评分/立场/行动/风险/置信)
  - 依赖注入 decision_generator: 默认规则, 可注入 Pro LLM.
  - 综合各 Agent score (按 confidence 加权) + stance 分布 + critique.can_finalize.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..schemas.contracts import (
    AggregatedEvidence, CritiqueResult, AgentResult, RiskItem,
)

logger = logging.getLogger(__name__)


@dataclass
class FinalDecision:
    """⑥ → ⑦ 最终决策 (Decision Layer 产出, Presentation Layer 输入)."""
    symbol: str = ""
    final_score: float = 0.5          # 0-1 综合评分
    stance: str = "neutral"           # bullish / bearish / neutral
    action: str = "hold"              # buy / hold / sell / watch
    confidence: float = 0.5           # 0-1 (critique 不可 finalize 时降级)
    summary: str = ""                 # 决策摘要
    risks: list[RiskItem] = field(default_factory=list)
    key_claims: list[str] = field(default_factory=list)  # 关键结论 (引用 Evidence)
    can_act: bool = True              # critique.can_finalize ? True : False (降级为观察)
    rationale: str = ""               # 决策依据


class DecisionAgent:
    """Chief Strategist: 基于 Evidence + Critique → FinalDecision.

    用法:
      decision = DecisionAgent()
      fd = await decision.decide(aggregated, critique, results, symbol="AAPL")
    """

    def __init__(self, decision_generator: Optional[Callable] = None):
        self._decision_generator = decision_generator

    async def decide(
        self,
        aggregated: AggregatedEvidence,
        critique: CritiqueResult,
        results: list[AgentResult],
        symbol: str = "",
    ) -> FinalDecision:
        """生成最终决策."""
        if self._decision_generator is not None:
            try:
                return await self._decision_generator(aggregated, critique, results, symbol)
            except Exception as e:
                logger.warning("[Decision] generator 失败, 退回规则: %s", e)
        return self._rule_based_decide(aggregated, critique, results, symbol)

    def _rule_based_decide(
        self,
        aggregated: AggregatedEvidence,
        critique: CritiqueResult,
        results: list[AgentResult],
        symbol: str,
    ) -> FinalDecision:
        """规则决策: 加权 score + stance 分布 + critique 状态."""
        # 1. 综合 score (按 confidence 加权)
        valid = [r for r in results if r.status == "ok" and r.confidence > 0]
        if valid:
            total_w = sum(r.confidence for r in valid)
            final_score = sum(r.score * r.confidence for r in valid) / total_w if total_w else 0.5
            avg_conf = total_w / len(valid)
        else:
            final_score = 0.5
            avg_conf = 0.3

        # 2. stance: stance_distribution 中最多
        dist = EvidenceAggregator_stance_distribution(aggregated)
        stance = max(dist, key=dist.get) if any(dist.values()) else "neutral"

        # 3. action: score 阈值
        if final_score >= 0.65:
            action = "buy"
        elif final_score <= 0.4:
            action = "sell"
        else:
            action = "hold"

        # 4. confidence: critique 不可 finalize → 降级
        can_act = critique.can_finalize
        confidence = avg_conf if can_act else avg_conf * 0.6
        if not can_act:
            action = "watch"  # 未定稿 → 仅观察

        # 5. 汇总风险
        risks: list[RiskItem] = []
        for r in results:
            risks.extend(r.risk)
        # 去重 (按 description)
        seen = set()
        unique_risks = []
        for rk in risks:
            if rk.description not in seen:
                seen.add(rk.description)
                unique_risks.append(rk)

        # 6. 关键结论 (高 confidence 的 claim)
        key_claims = []
        for ac in aggregated.claims:
            if ac.consensus >= 0.7:
                key_claims.append(f"[{ac.consensus:.1f}] {ac.claim}")

        # 7. 摘要 + 依据
        issue_n = len(critique.issues)
        conflict_n = len(aggregated.conflicts)
        summary = (
            f"综合评分 {final_score:.2f} ({stance}), 行动={action}. "
            f"证据 {sum(len(c.supporting) + len(c.contradicting) for c in aggregated.claims)} 条, "
            f"冲突 {conflict_n} 个, 反思问题 {issue_n} 个."
        )
        rationale = (
            f"基于 {len(valid)} 个 Agent 加权评分; critique.can_finalize={can_act}; "
            f"coverage 平均 {sum(aggregated.coverage.values())/len(aggregated.coverage):.2f}"
            if aggregated.coverage else f"基于 {len(valid)} 个 Agent; can_finalize={can_act}"
        )

        return FinalDecision(
            symbol=symbol,
            final_score=round(final_score, 4),
            stance=stance,
            action=action,
            confidence=round(confidence, 4),
            summary=summary,
            risks=unique_risks,
            key_claims=key_claims,
            can_act=can_act,
            rationale=rationale,
        )


def EvidenceAggregator_stance_distribution(aggregated: AggregatedEvidence) -> dict[str, int]:
    """复用 Phase 3 stance_distribution (避免循环导入)."""
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    for ac in aggregated.claims:
        for e in ac.supporting:
            counts[e.stance] = counts.get(e.stance, 0) + 1
        for e in ac.contradicting:
            counts[e.stance] = counts.get(e.stance, 0) + 1
    return counts


# 进程级默认实例
decision_agent = DecisionAgent()
