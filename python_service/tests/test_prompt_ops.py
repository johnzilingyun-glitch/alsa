"""P1-1: PromptOps — version registry and run metrics.

Every prompt must have:
- version_id, name, template_hash, status lifecycle (draft→canary→active→deprecated)
- PromptRun tracking: model, tokens, latency, schema validation result

The registry must prevent serving deprecated prompts and track which
version was used for any given analysis.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import hashlib
import pytest
from python_service.app.prompting.version_registry import (
    PromptVersionRegistry,
    PromptStatus,
)


class TestPromptVersionRegistry:
    """Test prompt version lifecycle and retrieval."""

    def test_register_prompt_version(self):
        registry = PromptVersionRegistry()
        template = "You are a {role}. Analyze {symbol} based on evidence."
        version = registry.register(
            name="chief_strategist",
            role_scope="Chief Strategist",
            template=template,
        )
        assert version.prompt_version_id is not None
        assert version.name == "chief_strategist"
        assert version.status == PromptStatus.DRAFT
        assert version.template_hash == hashlib.sha256(template.encode()).hexdigest()

    def test_activate_version(self):
        registry = PromptVersionRegistry()
        v1 = registry.register(name="analyst", role_scope="Fundamental Analyst", template="v1 template")
        registry.activate(v1.prompt_version_id)
        active = registry.get_active("analyst")
        assert active is not None
        assert active.prompt_version_id == v1.prompt_version_id
        assert active.status == PromptStatus.ACTIVE

    def test_only_one_active_per_name(self):
        """Activating a new version auto-deprecates the previous active."""
        registry = PromptVersionRegistry()
        v1 = registry.register(name="analyst", role_scope="test", template="v1")
        registry.activate(v1.prompt_version_id)
        v2 = registry.register(name="analyst", role_scope="test", template="v2")
        registry.activate(v2.prompt_version_id)

        active = registry.get_active("analyst")
        assert active.prompt_version_id == v2.prompt_version_id
        # v1 should be deprecated
        v1_now = registry.get_version(v1.prompt_version_id)
        assert v1_now.status == PromptStatus.DEPRECATED

    def test_deprecated_not_served(self):
        """get_active must never return deprecated versions."""
        registry = PromptVersionRegistry()
        v1 = registry.register(name="tech", role_scope="test", template="old")
        registry.activate(v1.prompt_version_id)
        registry.deprecate(v1.prompt_version_id)
        assert registry.get_active("tech") is None

    def test_canary_promotion(self):
        """Version can go draft → canary → active."""
        registry = PromptVersionRegistry()
        v = registry.register(name="risk", role_scope="CRO", template="risk template")
        registry.promote_to_canary(v.prompt_version_id)
        assert registry.get_version(v.prompt_version_id).status == PromptStatus.CANARY
        registry.activate(v.prompt_version_id)
        assert registry.get_version(v.prompt_version_id).status == PromptStatus.ACTIVE


class TestPromptRunTracking:
    """Test that every LLM call records a PromptRun with metrics."""

    def test_record_prompt_run(self):
        registry = PromptVersionRegistry()
        v = registry.register(name="analyst", role_scope="test", template="tpl")
        registry.activate(v.prompt_version_id)

        run = registry.record_run(
            prompt_version_id=v.prompt_version_id,
            model="deepseek-v4",
            provider="deepseek",
            input_tokens=2500,
            output_tokens=1800,
            latency_ms=3200,
            tool_calls=3,
            schema_validation_passed=True,
        )
        assert run.run_id is not None
        assert run.prompt_version_id == v.prompt_version_id
        assert run.model == "deepseek-v4"
        assert run.latency_ms == 3200
        assert run.tool_calls == 3

    def test_list_runs_for_version(self):
        registry = PromptVersionRegistry()
        v = registry.register(name="x", role_scope="y", template="z")

        registry.record_run(prompt_version_id=v.prompt_version_id, model="m1",
                            provider="p", input_tokens=100, output_tokens=50,
                            latency_ms=500, tool_calls=0, schema_validation_passed=True)
        registry.record_run(prompt_version_id=v.prompt_version_id, model="m1",
                            provider="p", input_tokens=200, output_tokens=100,
                            latency_ms=700, tool_calls=1, schema_validation_passed=False)

        runs = registry.list_runs(v.prompt_version_id)
        assert len(runs) == 2
        assert runs[1].schema_validation_passed is False

    def test_run_metrics_aggregation(self):
        """Can compute average latency and success rate for a version."""
        registry = PromptVersionRegistry()
        v = registry.register(name="agg", role_scope="t", template="t")

        for lat, passed in [(1000, True), (2000, True), (3000, False)]:
            registry.record_run(prompt_version_id=v.prompt_version_id, model="m",
                                provider="p", input_tokens=100, output_tokens=50,
                                latency_ms=lat, tool_calls=0, schema_validation_passed=passed)

        stats = registry.get_version_stats(v.prompt_version_id)
        assert stats["avg_latency_ms"] == 2000.0
        assert stats["schema_pass_rate"] == pytest.approx(2 / 3)
        assert stats["total_runs"] == 3
