"""Tests for the Professional Reviewer → EvolveR feedback loop.

Covers:
1. Structured marker parsing ([🟡 Rf_STALE], [🔴 WACC_BLACKBOX], ...)
2. process_feedback explicit-role routing + professional reviewer genome init
3. The reviewer feedback hook (fire-and-forget, exception-safe)
4. Per-role evolution throttling with the pending feedback queue
5. LLM-failure degradation (402 quota) — feedback retained, genome untouched
6. Fitness propagation from prediction accuracy into Gene.fitness
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services import prediction_service as ps
from app.services import reviewer_feedback_service as rfs
from app.services.brain_manager import (
    BrainManager,
    DEFAULT_GENOMES,
    EVOLUTION_MIN_INTERVAL_SECONDS,
)
from app.services.gep_models import EvolutionaryState, Gene, Genome


@contextmanager
def tmp_genome_file():
    """Isolate BrainManager genome persistence on a temp file.

    Every BrainManager instance constructed AND every persisting call made
    inside the context writes to the temp path, so the production
    data/brain/evolved_genome.json is never touched by the tests.
    """
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)  # start with no file → default state
    try:
        with patch("app.services.brain_manager.EVOLVED_GENOME_FILE", path):
            yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


def write_state_file(path: str, genomes: dict) -> None:
    """Persist a minimal EvolutionaryState with the given role→content map."""
    state = EvolutionaryState()
    for role, content in genomes.items():
        gene = Gene(content=content)
        state.genomes[role] = Genome(role=role, population=[gene], alpha_id=gene.id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(state.model_dump_json(indent=2))


def reviewer_discussion() -> list:
    """A discussion payload containing reviewer audit markers."""
    return [
        {"role": "Technical Analyst", "content": "趋势向上，MACD 金叉，无标记内容。"},
        {"role": "Professional Reviewer", "content": (
            "审计发现：\n"
            "[🟡 Rf_STALE] 前序专家使用 Rf=2.4% 与实时 1.73% 偏差过大，需修正 COE。\n"
            "补充说明第二行。\n"
            "[🔴 WACC_BLACKBOX] CAO 未披露 Beta 与 ERP 构成。\n"
            "[🟢 MODEL_OK] EPS/FCF 口径一致。"
        )},
    ]


class TestMarkerParsing(unittest.TestCase):
    """Structured audit marker extraction from discussion messages."""

    def test_multi_marker_extraction_with_severity_and_details(self):
        markers = rfs.parse_reviewer_markers(reviewer_discussion())
        self.assertEqual(
            [m["marker"] for m in markers],
            ["Rf_STALE", "WACC_BLACKBOX", "MODEL_OK"],
        )
        self.assertEqual(
            [m["severity"] for m in markers],
            ["warning", "critical", "ok"],
        )
        # Detail stops at end of line (second line is body text, not excerpt)
        self.assertIn("偏差过大", markers[0]["detail"])
        self.assertNotIn("补充说明第二行", markers[0]["detail"])
        self.assertIn("ERP", markers[1]["detail"])

    def test_detail_stops_at_next_marker_on_same_line(self):
        content = "[🟡 Rf_STALE] 原模型 Rf 过期 [🔴 PEG_MISMATCH] 口径混用"
        markers = rfs.parse_reviewer_markers(
            [{"role": "Professional Reviewer", "content": content}]
        )
        self.assertEqual([m["marker"] for m in markers], ["Rf_STALE", "PEG_MISMATCH"])
        self.assertEqual(markers[0]["detail"], "原模型 Rf 过期")
        self.assertEqual(markers[1]["detail"], "口径混用")

    def test_marker_with_inline_suffix_still_extracts_name(self):
        content = "[🟡 Rf_STALE → 已修正] 原因说明；[🔴 FATAL: 数据口径错配] 详情"
        markers = rfs.parse_reviewer_markers(
            [{"role": "Professional Reviewer", "content": content}]
        )
        self.assertEqual([m["marker"] for m in markers], ["Rf_STALE", "FATAL"])
        self.assertEqual(markers[0]["severity"], "warning")
        self.assertEqual(markers[1]["severity"], "critical")

    def test_plain_text_without_markers(self):
        messages = [{"role": "Professional Reviewer", "content": "整体逻辑一致，无重大问题。"}]
        self.assertEqual(rfs.parse_reviewer_markers(messages), [])

    def test_markers_from_non_reviewer_roles_are_ignored(self):
        messages = [
            {"role": "Chief Strategist", "content": "[🔴 WACC_BLACKBOX] not the reviewer"},
            {"role": "Professional Reviewer", "content": "no markers here"},
        ]
        self.assertEqual(rfs.parse_reviewer_markers(messages), [])

    def test_dict_content_is_normalized(self):
        messages = [
            {"role": "Professional Reviewer", "content": {"finding": "[🟡 Rf_STALE] dict payload"}}
        ]
        markers = rfs.parse_reviewer_markers(messages)
        self.assertEqual([m["marker"] for m in markers], ["Rf_STALE"])

    def test_empty_and_none_inputs(self):
        self.assertEqual(rfs.parse_reviewer_markers([]), [])
        self.assertEqual(rfs.parse_reviewer_markers(None), [])
        self.assertEqual(rfs.parse_reviewer_markers([{"role": "Professional Reviewer"}]), [])

    def test_long_detail_is_truncated(self):
        content = "[🔴 WACC_BLACKBOX] " + "很长的说明" * 100
        markers = rfs.parse_reviewer_markers(
            [{"role": "Professional Reviewer", "content": content}]
        )
        self.assertLessEqual(len(markers[0]["detail"]), rfs._SNIPPET_MAX_CHARS + 1)
        self.assertTrue(markers[0]["detail"].endswith("…"))


class TestExplicitRoleRouting(unittest.TestCase):
    """process_feedback must honor the explicit role key."""

    def test_explicit_role_wins_over_context_keywords(self):
        with tmp_genome_file():
            mgr = BrainManager()
            captured = {}

            def fake_mutate(genome, fb):
                captured["role"] = genome.role
                return None  # skip actual LLM evolution

            with patch.object(mgr, "_mutate", side_effect=fake_mutate):
                mgr.process_feedback({
                    "role": "Professional Reviewer",
                    "feedback": "评审质量需要提升",
                    # context alone would route to "technical analyst"
                    "context": "technical analysis of AAPL",
                })
        self.assertEqual(captured["role"], "professional reviewer")

    def test_explicit_role_with_empty_context_does_not_fall_to_global(self):
        # Regression for the old bug: empty context + ignored role → global
        with tmp_genome_file():
            mgr = BrainManager()
            captured = {}

            def fake_mutate(genome, fb):
                captured["role"] = genome.role
                return None

            with patch.object(mgr, "_mutate", side_effect=fake_mutate):
                mgr.process_feedback({
                    "role": "Professional Reviewer",
                    "feedback": "[🟡 Rf_STALE] test",
                    "context": "",
                })
        self.assertEqual(captured["role"], "professional reviewer")

    def test_missing_reviewer_genome_is_initialized(self):
        # Production legacy state has no professional reviewer genome
        with tmp_genome_file() as path:
            write_state_file(path, {"global": "legacy global content"})
            mgr = BrainManager()
            self.assertNotIn("professional reviewer", mgr.state.genomes)

            with patch.object(mgr, "_mutate", return_value=None) as mock_mutate:
                mgr.process_feedback({
                    "role": "Professional Reviewer",
                    "feedback": "[🟡 Rf_STALE] initialize me",
                    "context": "",
                })

            # Genome initialized with the canonical default instructions
            self.assertIn("professional reviewer", mgr.state.genomes)
            genome = mgr.state.genomes["professional reviewer"]
            self.assertIsNotNone(genome.alpha)
            self.assertEqual(genome.alpha.content, DEFAULT_GENOMES["professional reviewer"])
            # The mutation ran against the reviewer genome
            mock_mutate.assert_called_once()
            self.assertEqual(mock_mutate.call_args[0][0].role, "professional reviewer")

    def test_full_evolution_with_explicit_role_persists_alpha(self):
        with tmp_genome_file() as path:
            mgr = BrainManager()
            created = {}
            original_mutate = mgr._mutate

            def tracking_mutate(genome, fb):
                gene = original_mutate(genome, fb)
                created["gene"] = gene
                created["role"] = genome.role
                return gene

            with patch.object(mgr, "_call_llm", return_value="evolved reviewer instructions"), \
                 patch.object(mgr, "_mutate", side_effect=tracking_mutate), \
                 patch.object(mgr, "_select", side_effect=lambda g, fb: created["gene"].id):
                mgr.process_feedback({
                    "role": "Professional Reviewer",
                    "feedback": "[🔴 WACC_BLACKBOX] test marker",
                    "context": "",
                })

            genome = mgr.state.genomes["professional reviewer"]
            self.assertEqual(created["role"], "professional reviewer")
            self.assertEqual(genome.alpha.content, "evolved reviewer instructions")
            self.assertIn("[🔴 WACC_BLACKBOX] test marker", genome.alpha.feedback_logs)
            # Pending queue cleared after successful evolution
            self.assertEqual(mgr._pending_feedback.get("professional reviewer"), [])
            # State persisted to the isolated temp file
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(
                data["genomes"]["professional reviewer"]["alpha_id"], genome.alpha_id
            )

    def test_reviewer_keywords_in_context_route_without_explicit_role(self):
        for context in (
            "professional reviewer audit of 600519",
            "WACC_BLACKBOX detected in report",
            "评审发现 Rf 数据过期",
        ):
            with tmp_genome_file():
                mgr = BrainManager()
                captured = {}

                def fake_mutate(genome, fb):
                    captured["role"] = genome.role
                    return None

                with patch.object(mgr, "_mutate", side_effect=fake_mutate):
                    mgr.process_feedback({"feedback": "test", "context": context})
                self.assertEqual(
                    captured["role"], "professional reviewer",
                    f"context '{context}' should route to professional reviewer",
                )


class TestReviewerFeedbackHook(unittest.TestCase):
    """The analysis-job → EvolveR bridge (exception-safe, fire-and-forget)."""

    def test_hook_calls_process_feedback_with_role_and_markers(self):
        with patch.object(rfs, "brain_manager") as mock_bm:
            ok = rfs.feed_reviewer_feedback_to_brain(
                "job_1", "600519", "A-Share", reviewer_discussion(), as_of="2026-09-01"
            )
        self.assertTrue(ok)
        mock_bm.process_feedback.assert_called_once()
        payload = mock_bm.process_feedback.call_args[0][0]
        self.assertEqual(payload["role"], "professional reviewer")
        self.assertIn("Rf_STALE", payload["feedback"])
        self.assertIn("WACC_BLACKBOX", payload["feedback"])
        self.assertIn("MODEL_OK", payload["feedback"])
        self.assertIn("critical=1", payload["feedback"])
        self.assertIn("warning=1", payload["feedback"])
        self.assertIn("600519", payload["context"])
        self.assertIn("job_1", payload["context"])

    def test_hook_swallows_process_feedback_exceptions(self):
        with patch.object(rfs, "brain_manager") as mock_bm:
            mock_bm.process_feedback.side_effect = RuntimeError("LLM 402 quota exhausted")
            # Must not raise — the main pipeline stays unaffected
            ok = rfs.feed_reviewer_feedback_to_brain(
                "job_2", "600519", "A-Share", reviewer_discussion()
            )
        self.assertFalse(ok)

    def test_hook_without_markers_does_not_invoke_brain(self):
        with patch.object(rfs, "brain_manager") as mock_bm:
            ok = rfs.feed_reviewer_feedback_to_brain(
                "job_3", "600519", "A-Share",
                [{"role": "Professional Reviewer", "content": "无结构化标记"}],
            )
        self.assertFalse(ok)
        mock_bm.process_feedback.assert_not_called()

    def test_hook_handles_none_messages(self):
        with patch.object(rfs, "brain_manager") as mock_bm:
            ok = rfs.feed_reviewer_feedback_to_brain("job_4", "600519", "A-Share", None)
        self.assertFalse(ok)
        mock_bm.process_feedback.assert_not_called()

    def test_async_hook_runs_off_thread_and_never_raises(self):
        with patch.object(rfs, "brain_manager") as mock_bm:
            mock_bm.process_feedback.side_effect = RuntimeError("boom")
            t = rfs.feed_reviewer_feedback_to_brain_async(
                "job_5", "600519", "A-Share", reviewer_discussion()
            )
            self.assertIsNotNone(t)
            t.join(timeout=5)
            self.assertFalse(t.is_alive())
            mock_bm.process_feedback.assert_called_once()


class TestEvolutionThrottle(unittest.TestCase):
    """Per-role evolution throttling with pending queue merge."""

    def test_second_feedback_within_interval_is_queued_not_evolved(self):
        with tmp_genome_file():
            mgr = BrainManager()
            mutate_calls = []

            def fake_mutate(genome, fb):
                mutate_calls.append(fb)
                return None

            with patch.object(mgr, "_mutate", side_effect=fake_mutate):
                mgr.process_feedback({"role": "Professional Reviewer", "feedback": "fb-1", "context": ""})
                mgr.process_feedback({"role": "Professional Reviewer", "feedback": "fb-2", "context": ""})

            # Only the first feedback triggered mutation; the second was throttled
            self.assertEqual(len(mutate_calls), 1)
            self.assertEqual(mutate_calls[0], "fb-1")
            # Both feedbacks retained in the pending queue
            self.assertEqual(
                mgr._pending_feedback["professional reviewer"], ["fb-1", "fb-2"]
            )

    def test_pending_feedback_merged_on_next_evolution(self):
        with tmp_genome_file():
            mgr = BrainManager()
            mutate_calls = []

            def fake_mutate(genome, fb):
                mutate_calls.append(fb)
                return None

            import time as _time
            with patch.object(mgr, "_mutate", side_effect=fake_mutate):
                mgr.process_feedback({"role": "Professional Reviewer", "feedback": "fb-1", "context": ""})
                # Fast-forward past the throttle window
                mgr._last_evolution_at["professional reviewer"] = (
                    _time.time() - EVOLUTION_MIN_INTERVAL_SECONDS - 1
                )
                mgr.process_feedback({"role": "Professional Reviewer", "feedback": "fb-2", "context": ""})

            self.assertEqual(len(mutate_calls), 2)
            # The second attempt merged both pending items into one payload
            self.assertIn("fb-1", mutate_calls[1])
            self.assertIn("fb-2", mutate_calls[1])

    def test_throttle_is_per_role(self):
        with tmp_genome_file():
            mgr = BrainManager()
            roles_evolved = []

            def fake_mutate(genome, fb):
                roles_evolved.append(genome.role)
                return None

            with patch.object(mgr, "_mutate", side_effect=fake_mutate):
                mgr.process_feedback({"role": "Professional Reviewer", "feedback": "a", "context": ""})
                mgr.process_feedback({"role": "Technical Analyst", "feedback": "b", "context": ""})

            # Different roles are throttled independently
            self.assertEqual(roles_evolved, ["professional reviewer", "technical analyst"])


class TestLLMFailureDegradation(unittest.TestCase):
    """402-quota style failures must not raise or pollute the genome."""

    def test_llm_unavailable_keeps_genome_pristine_and_feedback_pending(self):
        with tmp_genome_file() as path:
            mgr = BrainManager()
            before = mgr.state.genomes["professional reviewer"].model_dump()

            with patch.object(mgr, "_call_llm", return_value=None) as mock_llm:
                # DeepSeek and Gemini both unavailable → must not raise
                mgr.process_feedback({
                    "role": "Professional Reviewer",
                    "feedback": "[🟡 Rf_STALE] stale risk-free rate",
                    "context": "",
                })

            after = mgr.state.genomes["professional reviewer"]
            # Genome not polluted: population/alpha/fitness unchanged
            self.assertEqual(after.model_dump(), before)
            # Feedback retained in pending for the next window
            self.assertEqual(len(mgr._pending_feedback["professional reviewer"]), 1)
            self.assertIn("Rf_STALE", mgr._pending_feedback["professional reviewer"][0])
            # Nothing persisted to disk (no half-written state)
            self.assertFalse(os.path.exists(path))
            mock_llm.assert_called()

    def test_mutate_exception_is_degraded_to_noop(self):
        with tmp_genome_file():
            mgr = BrainManager()
            before = mgr.state.genomes["professional reviewer"].model_dump()

            with patch.object(mgr, "_mutate", side_effect=RuntimeError("provider exploded")):
                mgr.process_feedback({
                    "role": "Professional Reviewer",
                    "feedback": "[🔴 WACC_BLACKBOX] boom",
                    "context": "",
                })

            self.assertEqual(mgr.state.genomes["professional reviewer"].model_dump(), before)
            self.assertEqual(len(mgr._pending_feedback["professional reviewer"]), 1)


class TestFitnessPropagation(unittest.TestCase):
    """Prediction accuracy → Gene.fitness."""

    def test_apply_global_fitness_writes_every_alpha_and_clamps(self):
        with tmp_genome_file():
            mgr = BrainManager()
            result = mgr.apply_global_fitness(0.72)
            self.assertTrue(result["professional reviewer"])
            self.assertTrue(result["global"])
            self.assertAlmostEqual(mgr.state.genomes["professional reviewer"].alpha.fitness, 0.72)
            self.assertAlmostEqual(mgr.state.genomes["global"].alpha.fitness, 0.72)
            # Clamp to [0, 1]
            mgr.apply_global_fitness(1.7)
            self.assertEqual(mgr.state.genomes["global"].alpha.fitness, 1.0)
            mgr.apply_global_fitness(-0.5)
            self.assertEqual(mgr.state.genomes["global"].alpha.fitness, 0.0)

    def test_update_role_fitness_maps_display_names(self):
        with tmp_genome_file():
            mgr = BrainManager()
            ok = mgr.update_role_fitness("Professional Reviewer", 0.5)
            self.assertTrue(ok)
            self.assertAlmostEqual(mgr.state.genomes["professional reviewer"].alpha.fitness, 0.5)

    def test_update_role_fitness_unknown_role(self):
        with tmp_genome_file():
            mgr = BrainManager()
            self.assertFalse(mgr.update_role_fitness("nonexistent_role_xyz", 0.5))

    def test_prediction_service_refreshes_brain_fitness(self):
        mock_records = [
            MagicMock(accuracy_score=80.0),
            MagicMock(accuracy_score=60.0),
            MagicMock(accuracy_score=100.0),
            MagicMock(accuracy_score=None),  # skipped
        ]
        session = MagicMock()
        session.exec.return_value.all.return_value = mock_records

        with patch.object(ps, "session_factory", return_value=session), \
             patch("app.services.brain_manager.brain_manager") as mock_bm:
            mock_bm.apply_global_fitness.return_value = {
                "global": True, "professional reviewer": True,
            }
            result = asyncio.run(ps.PredictionService._update_brain_fitness(window=50))

        mock_bm.apply_global_fitness.assert_called_once_with(0.8)
        session.close.assert_called()
        self.assertEqual(result["samples"], 3)
        self.assertAlmostEqual(result["fitness"], 0.8)
        self.assertGreater(result["genomes_updated"], 0)

    def test_prediction_service_no_evaluated_records_is_noop(self):
        session = MagicMock()
        session.exec.return_value.all.return_value = []

        with patch.object(ps, "session_factory", return_value=session), \
             patch("app.services.brain_manager.brain_manager") as mock_bm:
            result = asyncio.run(ps.PredictionService._update_brain_fitness(window=50))

        mock_bm.apply_global_fitness.assert_not_called()
        self.assertIsNone(result)

    def test_prediction_service_brain_failure_never_raises(self):
        session = MagicMock()
        session.exec.return_value.all.return_value = [MagicMock(accuracy_score=90.0)]

        with patch.object(ps, "session_factory", return_value=session), \
             patch("app.services.brain_manager.brain_manager") as mock_bm:
            mock_bm.apply_global_fitness.side_effect = RuntimeError("qdrant/llm down")
            # Must degrade to warning, not raise
            result = asyncio.run(ps.PredictionService._update_brain_fitness(window=50))

        self.assertIsNone(result)


class TestRoleTargetPriceExtraction(unittest.TestCase):
    """Per-expert price-target extraction feeding role-attributed predictions.

    AnalysisJobService._extract_role_target_prices 是研讨消息 → PredictionRecord(role)
    的桥：只有量化了目标价的专家才进入 per-role 准确率环。
    """

    @classmethod
    def setUpClass(cls):
        from app.services.analysis_job_service import AnalysisJobService
        # 经由类访问 staticmethod（直接赋函数到测试类会让实例访问绑 self）。
        cls.svc_cls = AnalysisJobService

    def _extract(self, msgs, price):
        return self.svc_cls._extract_role_target_prices(msgs, price)

    def test_extracts_targets_per_role(self):
        msgs = [
            {"role": "Technical Analyst", "content": "MACD 金叉，目标价 25.6 元，止损 22"},
            {"role": "Bull Researcher", "content": "12个月目标价为32.5，概率60%"},
            {"role": "Bear Researcher", "content": "worst-case target price of 15.2"},
        ]
        self.assertEqual(
            self._extract(msgs, 100.0),
            {"Technical Analyst": 25.6, "Bull Researcher": 32.5, "Bear Researcher": 15.2},
        )

    def test_consensus_and_system_roles_excluded(self):
        msgs = [
            {"role": "Chief Strategist", "content": "targetPrice 28"},  # 共识口径单独落库
            {"role": "System", "content": "目标价 999"},
            {"role": "", "content": "目标价 50"},
        ]
        self.assertEqual(self._extract(msgs, 100.0), {})

    def test_implausible_price_outside_band_rejected(self):
        # 8/100 = 0.08x，超出 0.1x–10x 合理性带 → 不入库（防随机数字污染）。
        msgs = [{"role": "Value Investing Sage", "content": "内在价值约 120，目标价 8"}]
        self.assertEqual(self._extract(msgs, 100.0), {})

    def test_later_message_overrides_earlier_stance(self):
        msgs = [
            {"role": "Technical Analyst", "content": "目标价 25.6"},
            {"role": "Technical Analyst", "content": "修正：目标价 27.0"},
        ]
        self.assertEqual(self._extract(msgs, 100.0), {"Technical Analyst": 27.0})

    def test_messages_without_targets_skipped(self):
        msgs = [
            {"role": "Risk Manager", "content": "本报告无明确价格预测"},
            {"role": "Soros-style Financial Philosopher", "content": ""},
        ]
        self.assertEqual(self._extract(msgs, 100.0), {})

    def test_non_positive_current_price_is_noop(self):
        msgs = [{"role": "Technical Analyst", "content": "目标价 25.6"}]
        self.assertEqual(self._extract(msgs, 0.0), {})


class TestPerRoleFitnessAggregation(unittest.TestCase):
    """PredictionService 准确率环按 role 聚合写入对应 Gene.fitness。"""

    def test_role_records_route_to_role_genomes(self):
        mock_records = [
            MagicMock(accuracy_score=80.0, role=None),   # 共识预测 → 全局池
            MagicMock(accuracy_score=60.0, role=None),
            MagicMock(accuracy_score=90.0, role="Technical Analyst"),
            MagicMock(accuracy_score=50.0, role="Technical Analyst"),
            MagicMock(accuracy_score=None, role="Bull Researcher"),  # 无分跳过
        ]
        session = MagicMock()
        session.exec.return_value.all.return_value = mock_records

        with patch.object(ps, "session_factory", return_value=session), \
             patch("app.services.brain_manager.brain_manager") as mock_bm:
            mock_bm.apply_global_fitness.return_value = {"global": True, "technical analyst": True}
            mock_bm.update_role_fitness.return_value = True
            result = asyncio.run(ps.PredictionService._update_brain_fitness(window=50))

        # 全局池均值 (80+60)/2 = 70 → 0.7 写全部 genome
        mock_bm.apply_global_fitness.assert_called_once_with(0.7)
        # Technical Analyst 均值 (90+50)/2 = 70 → 0.7 只写该角色 genome
        mock_bm.update_role_fitness.assert_called_once_with("Technical Analyst", 0.7)
        self.assertEqual(result["samples"], 2)
        self.assertAlmostEqual(result["fitness"], 0.7)
        self.assertEqual(
            result["roles"],
            {"Technical Analyst": {"fitness": 0.7, "samples": 2}},
        )

    def test_role_only_records_skip_global_write(self):
        # 只有专家预测、无共识记录：不触发 apply_global_fitness。
        mock_records = [MagicMock(accuracy_score=90.0, role="Professional Reviewer")]
        session = MagicMock()
        session.exec.return_value.all.return_value = mock_records

        with patch.object(ps, "session_factory", return_value=session), \
             patch("app.services.brain_manager.brain_manager") as mock_bm:
            mock_bm.update_role_fitness.return_value = True
            result = asyncio.run(ps.PredictionService._update_brain_fitness(window=50))

        mock_bm.apply_global_fitness.assert_not_called()
        mock_bm.update_role_fitness.assert_called_once_with("Professional Reviewer", 0.9)
        self.assertIsNone(result["fitness"])
        self.assertEqual(result["samples"], 0)
        self.assertEqual(result["roles"]["Professional Reviewer"]["samples"], 1)

    def test_unmapped_role_degrades_to_noop(self):
        # 无对应 genome 的角色：update_role_fitness 返回 False → 不进结果。
        mock_records = [MagicMock(accuracy_score=90.0, role="nonexistent_role_xyz")]
        session = MagicMock()
        session.exec.return_value.all.return_value = mock_records

        with patch.object(ps, "session_factory", return_value=session), \
             patch("app.services.brain_manager.brain_manager") as mock_bm:
            mock_bm.update_role_fitness.return_value = False
            result = asyncio.run(ps.PredictionService._update_brain_fitness(window=50))

        mock_bm.apply_global_fitness.assert_not_called()
        self.assertIsNone(result)

    def test_legacy_records_without_role_stay_global(self):
        # 存量行/无 role 属性的记录 → 全局池（保持旧行为，绝不丢并信号）。
        mock_records = [MagicMock(accuracy_score=90.0)]  # role 为 MagicMock → 非字符串
        session = MagicMock()
        session.exec.return_value.all.return_value = mock_records

        with patch.object(ps, "session_factory", return_value=session), \
             patch("app.services.brain_manager.brain_manager") as mock_bm:
            mock_bm.apply_global_fitness.return_value = {"global": True}
            result = asyncio.run(ps.PredictionService._update_brain_fitness(window=50))

        mock_bm.apply_global_fitness.assert_called_once_with(0.9)
        mock_bm.update_role_fitness.assert_not_called()
        self.assertEqual(result["samples"], 1)
        self.assertEqual(result["roles"], {})


if __name__ == "__main__":
    unittest.main()
