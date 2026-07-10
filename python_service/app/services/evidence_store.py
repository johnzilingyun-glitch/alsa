"""EvidenceStore + Aggregator — 证据聚合 (Phase 3, §4.3, v3.1 修复).

开发指南 §4.3 v3.1 逻辑错误修复:
  不再用 confidence <= 0.6 判 contradicting, 改用 stance 维度.
  - supporting   = stance ∈ {bullish, neutral}
  - contradicting = stance == bearish
  低 confidence 只是证据弱, 不一定是反对.

流程:
  收集 evidence[] → 按 claim 聚类 → 按 stance 分支持/反对 → consensus → 冲突标记
  → AggregatedEvidence {claims, conflicts, coverage}

设计:
  - 默认规则聚类 (normalize claim 文本分组), 可注入 LLM 语义聚类.
  - 复用 EvidenceBus.all_evidence / AgentResult.evidence.
  - 纯 stdlib + contracts, 可测试不依赖 LLM.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Callable, Optional

from ..schemas.contracts import (
    AgentResult, Evidence, AggregatedEvidence, AggregatedClaim, Conflict,
)

logger = logging.getLogger(__name__)


def _normalize_claim(claim: str) -> str:
    """归一化 claim 文本用于聚类 (去标点/小写/折叠空格)."""
    if not claim:
        return ""
    s = claim.strip().lower()
    # 去标点 (保留中文/字母数字)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class EvidenceAggregator:
    """聚合证据, 按 claim + stance 维度组织, 标记冲突.

    用法:
      agg = EvidenceAggregator()
      aggregated = agg.aggregate(agent_results)
      # aggregated.claims / aggregated.conflicts / aggregated.coverage
    """

    def __init__(self, clusterer: Optional[Callable] = None):
        # 可注入 LLM 语义聚类器; 默认规则聚类
        self._clusterer = clusterer

    def aggregate(self, results: list[AgentResult]) -> AggregatedEvidence:
        """聚合 Agent 输出的证据 → AggregatedEvidence."""
        all_evidence = [e for r in results for e in r.evidence]
        if not all_evidence:
            return AggregatedEvidence(claims=[], conflicts=[], coverage=self._coverage(results))

        # 1. 按 claim 聚类
        clusters = self._cluster_claims(all_evidence)

        aggregated: list[AggregatedClaim] = []
        conflicts: list[Conflict] = []
        for claim, evs in clusters.items():
            # v3.1 修复: 按 stance 判支持/反对 (不是 confidence)
            supporting = [e for e in evs if e.stance in ("bullish", "neutral")]
            contradicting = [e for e in evs if e.stance == "bearish"]
            consensus = self._compute_consensus(supporting, contradicting)
            ac = AggregatedClaim(
                claim=claim, supporting=supporting,
                contradicting=contradicting, consensus=consensus,
            )
            aggregated.append(ac)
            # 存在 contradicting → 标记冲突
            if contradicting and supporting:
                conflicts.append(Conflict(
                    claim=claim, supporting=supporting, contradicting=contradicting,
                ))

        coverage = self._coverage(results)
        return AggregatedEvidence(claims=aggregated, conflicts=conflicts, coverage=coverage)

    # ════════════════════════════════════════════════════════════════════════
    # 聚类
    # ════════════════════════════════════════════════════════════════════════

    def _cluster_claims(self, evidence: list[Evidence]) -> dict[str, list[Evidence]]:
        """按 claim 聚类.

        默认: normalize claim 文本分组.
        可注入 clusterer(evidence) -> dict[claim, list[Evidence]] 做语义聚类 (Flash).
        """
        if self._clusterer is not None:
            try:
                return self._clusterer(evidence)
            except Exception as e:
                logger.warning("[Aggregator] clusterer 失败, 退回规则: %s", e)
        # 规则聚类: 按 normalize 后的 claim 分组, 用原始 claim 中最长的作 key
        groups: dict[str, list[Evidence]] = {}
        key_map: dict[str, str] = {}
        for e in evidence:
            nk = _normalize_claim(e.claim)
            if not nk:
                nk = "(unlabeled)"
            if nk not in groups:
                groups[nk] = []
                key_map[nk] = e.claim
            groups[nk].append(e)
        # 用原始 claim 作 key (更可读)
        return {key_map[k]: v for k, v in groups.items()}

    # ════════════════════════════════════════════════════════════════════════
    # 一致性 / 冲突
    # ════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _compute_consensus(supporting: list[Evidence],
                           contradicting: list[Evidence]) -> float:
        """一致性分数 0-1.

        加权: 按 confidence 加权, supporting 占比.
        1.0 = 全部支持; 0.0 = 全部反对; 0.5 = 势均.
        """
        s_weight = sum(e.confidence for e in supporting)
        c_weight = sum(e.confidence for e in contradicting)
        total = s_weight + c_weight
        if total == 0:
            return 0.5
        return round(s_weight / total, 4)

    @staticmethod
    def _coverage(results: list[AgentResult]) -> dict[str, float]:
        """每个 role 的证据覆盖度 (有证据的 role 权重高).

        开发指南 §3.2 coverage: dict[str, float].
        """
        out: dict[str, float] = {}
        for r in results:
            if r.status == "skipped":
                out[r.role] = 0.0
            elif r.status == "degraded":
                out[r.role] = 0.3
            elif not r.evidence:
                out[r.role] = 0.2  # 有输出但无结构化证据
            else:
                # 证据数 + 平均置信度
                avg_conf = sum(e.confidence for e in r.evidence) / len(r.evidence)
                out[r.role] = round(min(1.0, 0.4 + 0.6 * avg_conf), 4)
        return out

    # ════════════════════════════════════════════════════════════════════════
    # 诊断
    # ════════════════════════════════════════════════════════════════════════

    @staticmethod
    def stance_distribution(aggregated: AggregatedEvidence) -> dict[str, int]:
        """统计聚合后的 stance 分布 (供 Reflection 决策)."""
        counts = {"bullish": 0, "bearish": 0, "neutral": 0}
        for ac in aggregated.claims:
            for e in ac.supporting:
                counts[e.stance] = counts.get(e.stance, 0) + 1
            for e in ac.contradicting:
                counts[e.stance] = counts.get(e.stance, 0) + 1
        return counts


# 进程级默认实例
evidence_aggregator = EvidenceAggregator()
