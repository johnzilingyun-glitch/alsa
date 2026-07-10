"""OutputGuardrail — 输出侧校验拦截 (§10.3 #2 P2, ★ 剩余优化项).

开发指南 §10.3 #2:
  "当前只有 grounding_verifier (输入侧), 可加 output_guardrail 拦截低质输出"

与 grounding_verifier 的分工:
  grounding_verifier (输入侧): 校验 LLM 输出的数值 claim 是否与 snapshot 一致
  output_guardrail (输出侧):  拦截低质 FinalDecision / AgentResult (幻觉/低置信/空证据/矛盾)

检测规则:
  1. 幻觉: key_claims/summary 断言无对应 Evidence 支持
  2. 低置信强制 finalize: can_finalize=True 但 confidence<0.4
  3. 空证据: FinalDecision 无证据支撑 (aggregated.claims 空)
  4. 分数-证据不一致: final_score 高但 consensus 低 / 证据少
  5. action-score 矛盾: score<0.4 但 action=buy, 或 score>0.65 但 action=sell

GuardrailResult.action:
  block: 拦截 (强制 action=watch, can_act=False)
  warn:  警告但放行
  pass:  通过

复用: Phase4 FinalDecision + Phase3 AggregatedEvidence + Phase1 is_valid_result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..schemas.contracts import AggregatedEvidence, CritiqueResult
from ..agents.decision_agent import FinalDecision
from ..services.tools.preconditions import is_valid_result

logger = logging.getLogger(__name__)


@dataclass
class GuardrailIssue:
    severity: str            # block / warn
    rule: str                # 规则名
    description: str


@dataclass
class GuardrailResult:
    passed: bool = True
    issues: list[GuardrailIssue] = field(default_factory=list)
    action: str = "pass"     # block / warn / pass
    # 拦截后的修正决策 (block 时覆盖原 decision)
    overridden_decision: Optional[FinalDecision] = None

    def add(self, severity: str, rule: str, desc: str) -> None:
        self.issues.append(GuardrailIssue(severity, rule, desc))
        if severity == "block":
            self.action = "block"
            self.passed = False
        elif severity == "warn" and self.action != "block":
            self.action = "warn"


class OutputGuardrail:
    """输出侧 guardrail: 拦截低质 FinalDecision.

    用法:
      guard = OutputGuardrail()
      result = guard.check(decision, aggregated, critique)
      if result.action == "block":
          final = result.overridden_decision  # 用修正后的决策
    """

    # 阈值 (可配置)
    LOW_CONFIDENCE_THRESHOLD = 0.4
    HIGH_SCORE_THRESHOLD = 0.65
    LOW_SCORE_THRESHOLD = 0.4
    MIN_EVIDENCE_COUNT = 1

    def check(self, decision: FinalDecision,
              aggregated: AggregatedEvidence,
              critique: Optional[CritiqueResult] = None) -> GuardrailResult:
        """校验 FinalDecision 输出质量."""
        result = GuardrailResult()

        # 1. 空证据检测
        total_ev = sum(len(c.supporting) + len(c.contradicting) for c in aggregated.claims)
        if total_ev < self.MIN_EVIDENCE_COUNT:
            result.add("block", "empty_evidence",
                       f"决策无证据支撑 (仅 {total_ev} 条证据)")

        # 2. 低置信强制 finalize
        if decision.confidence < self.LOW_CONFIDENCE_THRESHOLD and decision.can_act:
            result.add("warn", "low_confidence_act",
                       f"置信度低({decision.confidence:.2f})却标记可执行")

        # 3. 分数-证据不一致: 高分但 consensus 低
        if aggregated.claims:
            avg_consensus = sum(c.consensus for c in aggregated.claims) / len(aggregated.claims)
            if decision.final_score >= self.HIGH_SCORE_THRESHOLD and avg_consensus < 0.5:
                result.add("warn", "score_evidence_mismatch",
                           f"高分({decision.final_score:.2f})但证据一致性低({avg_consensus:.2f})")

        # 4. action-score 矛盾
        if decision.action == "buy" and decision.final_score < self.LOW_SCORE_THRESHOLD:
            result.add("block", "action_score_contradiction",
                       f"action=buy 但 score={decision.final_score:.2f} < {self.LOW_SCORE_THRESHOLD}")
        if decision.action == "sell" and decision.final_score > self.HIGH_SCORE_THRESHOLD:
            result.add("block", "action_score_contradiction",
                       f"action=sell 但 score={decision.final_score:.2f} > {self.HIGH_SCORE_THRESHOLD}")

        # 5. 幻觉: key_claims 中无对应 Evidence 的断言
        if decision.key_claims and aggregated.claims:
            ev_claims = set()
            for c in aggregated.claims:
                ev_claims.add(c.claim)
                for e in c.supporting + c.contradicting:
                    ev_claims.add(e.claim)
            # key_claims 是字符串 (可能含 [consensus] 前缀), 检查是否有任一证据 claim 子串匹配
            unsupported = []
            for kc in decision.key_claims:
                kc_text = kc.lower()
                if not any(ev.lower() in kc_text or kc_text in ev.lower() for ev in ev_claims):
                    unsupported.append(kc)
            if unsupported and len(unsupported) == len(decision.key_claims):
                # 全部 key_claims 无证据支撑 → 幻觉风险
                result.add("warn", "hallucination_risk",
                           f"key_claims 无证据支撑: {unsupported[:2]}")

        # 6. 基础有效性 (复用 Phase1 is_valid_result)
        if not is_valid_result(decision.summary or ""):
            result.add("block", "invalid_summary", "决策摘要为空或无效")

        # block → 生成修正决策
        if result.action == "block":
            result.overridden_decision = self._override(decision)
            logger.warning("[Guardrail] 拦截决策: %s", [i.rule for i in result.issues if i.severity == "block"])

        return result

    @staticmethod
    def _override(decision: FinalDecision) -> FinalDecision:
        """拦截后修正: 强制 action=watch, can_act=False, confidence 降级."""
        return FinalDecision(
            symbol=decision.symbol,
            final_score=decision.final_score,
            stance=decision.stance,
            action="watch",
            confidence=min(decision.confidence, 0.3),
            summary=f"[GUARDRAIL 拦截] {decision.summary}",
            risks=decision.risks,
            key_claims=decision.key_claims,
            can_act=False,
            rationale=f"被 output_guardrail 拦截: {decision.rationale}",
        )


# 进程级默认实例
output_guardrail = OutputGuardrail()
