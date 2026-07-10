"""ReportBuilder — 报告生成 (Phase 7, ⑦ Presentation Layer).

开发指南 §1.1:
  ⑦ Presentation Layer · Report Builder (Evidence 引用)
  基于 FinalDecision + AggregatedEvidence → 生成报告, 证据可追溯 (claim + source).

设计:
  - 输入: FinalDecision (Phase 4) + AggregatedEvidence (Phase 3) + AgentResult[] + CritiqueResult(可选)
  - 输出: Report (markdown 字符串 + 结构化 dict)
  - 证据引用: 每个 claim 带 source[] + agent + stance + confidence (可追溯)
  - 复用现有 report_generator_service 的 HTML 渲染思路 (可作为其数据源)

报告结构:
  1. 摘要 (FinalDecision.summary)
  2. 评分 / 立场 / 行动建议 / 置信度
  3. 关键结论 (consensus≥0.7 的 claim, 带证据引用)
  4. 证据详情 (全部 claim: supporting/contradicting/consensus, source 可追溯)
  5. 风险清单
  6. 反思问题 (CritiqueResult.issues, 若有)
  7. 决策依据
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..schemas.contracts import (
    AggregatedEvidence, AggregatedClaim, AgentResult, CritiqueResult,
)
from ..agents.decision_agent import FinalDecision

logger = logging.getLogger(__name__)


class ReportBuilder:
    """⑦ Presentation Layer: FinalDecision + Evidence → Report.

    用法:
      rb = ReportBuilder()
      md = rb.build_markdown(final_decision, aggregated, results, critique)
      report = rb.build(final_decision, aggregated, results, critique)  # dict
    """

    def build(self, decision: FinalDecision,
              aggregated: AggregatedEvidence,
              results: list[AgentResult],
              critique: Optional[CritiqueResult] = None) -> dict:
        """生成结构化报告 dict (供前端/HTML 渲染)."""
        return {
            "symbol": decision.symbol,
            "summary": decision.summary,
            "score": decision.final_score,
            "stance": decision.stance,
            "action": decision.action,
            "confidence": decision.confidence,
            "can_act": decision.can_act,
            "key_claims": decision.key_claims,
            "evidence": self._evidence_section(aggregated),
            "risks": [self._risk_dict(r) for r in decision.risks],
            "issues": [self._issue_dict(i) for i in (critique.issues if critique else [])],
            "rationale": decision.rationale,
            "coverage": aggregated.coverage,
        }

    def build_markdown(self, decision: FinalDecision,
                       aggregated: AggregatedEvidence,
                       results: list[AgentResult],
                       critique: Optional[CritiqueResult] = None) -> str:
        """生成 Markdown 报告 (Evidence 引用可追溯)."""
        lines: list[str] = []
        sym = f" ({decision.symbol})" if decision.symbol else ""
        lines.append(f"# 投资分析报告{sym}")
        lines.append("")

        # 1. 摘要
        lines.append("## 摘要")
        lines.append(decision.summary or "(无摘要)")
        lines.append("")

        # 2. 评分 / 立场 / 行动
        lines.append("## 综合评估")
        lines.append(f"- **综合评分**: {decision.final_score:.2f} / 1.00")
        lines.append(f"- **立场**: {self._stance_cn(decision.stance)}")
        lines.append(f"- **行动建议**: {self._action_cn(decision.action)}")
        lines.append(f"- **置信度**: {decision.confidence:.2f}")
        actable = "可执行" if decision.can_act else "仅观察 (反思未定稿)"
        lines.append(f"- **可执行性**: {actable}")
        lines.append("")

        # 3. 关键结论
        if decision.key_claims:
            lines.append("## 关键结论")
            for c in decision.key_claims:
                lines.append(f"- {c}")
            lines.append("")

        # 4. 证据详情 (可追溯引用)
        lines.append("## 证据详情")
        if aggregated.claims:
            for i, ac in enumerate(aggregated.claims, 1):
                lines.append(f"### {i}. {ac.claim}")
                lines.append(f"- 一致性: {ac.consensus:.2f}")
                if ac.supporting:
                    lines.append(f"- 支持 ({len(ac.supporting)}):")
                    for e in ac.supporting:
                        lines.append(f"  - [{e.agent}|{e.stance}|conf={e.confidence:.1f}] {e.claim}  \n    source: {', '.join(e.source) or 'N/A'}")
                if ac.contradicting:
                    lines.append(f"- 反对 ({len(ac.contradicting)}):")
                    for e in ac.contradicting:
                        lines.append(f"  - [{e.agent}|{e.stance}|conf={e.confidence:.1f}] {e.claim}  \n    source: {', '.join(e.source) or 'N/A'}")
                lines.append("")
        else:
            lines.append("(无结构化证据)")
            lines.append("")

        # 5. 冲突标记
        if aggregated.conflicts:
            lines.append("## 证据冲突")
            for cf in aggregated.conflicts:
                lines.append(f"- **{cf.claim}**: {len(cf.supporting)} 支持 vs {len(cf.contradicting)} 反对")
            lines.append("")

        # 6. 风险
        if decision.risks:
            lines.append("## 风险清单")
            for r in decision.risks:
                lines.append(f"- [{r.severity}] {r.category}: {r.description}" + (f" (缓解: {r.mitigation})" if r.mitigation else ""))
            lines.append("")

        # 7. 反思问题
        if critique and critique.issues:
            lines.append("## 反思问题")
            for issue in critique.issues:
                lines.append(f"- [{issue.severity}] {issue.description}")
            lines.append("")

        # 8. 决策依据
        lines.append("## 决策依据")
        lines.append(decision.rationale or "(无)")
        lines.append("")

        return "\n".join(lines)

    # ── helpers ──────────────────────────────────────────────────────────

    def _evidence_section(self, aggregated: AggregatedEvidence) -> list[dict]:
        """证据详情 (可追溯)."""
        out = []
        for ac in aggregated.claims:
            out.append({
                "claim": ac.claim,
                "consensus": ac.consensus,
                "supporting": [
                    {"agent": e.agent, "stance": e.stance, "confidence": e.confidence,
                     "claim": e.claim, "source": e.source}
                    for e in ac.supporting
                ],
                "contradicting": [
                    {"agent": e.agent, "stance": e.stance, "confidence": e.confidence,
                     "claim": e.claim, "source": e.source}
                    for e in ac.contradicting
                ],
            })
        return out

    @staticmethod
    def _risk_dict(r) -> dict:
        return {"category": r.category, "description": r.description,
                "severity": r.severity, "mitigation": getattr(r, "mitigation", "")}

    @staticmethod
    def _issue_dict(i) -> dict:
        return {"severity": i.severity, "description": i.description, "agent_id": i.agent_id}

    @staticmethod
    def _stance_cn(stance: str) -> str:
        return {"bullish": "看多", "bearish": "看空", "neutral": "中性"}.get(stance, stance)

    @staticmethod
    def _action_cn(action: str) -> str:
        return {"buy": "买入", "sell": "卖出", "hold": "持有", "watch": "观察"}.get(action, action)


# 进程级默认实例
report_builder = ReportBuilder()
