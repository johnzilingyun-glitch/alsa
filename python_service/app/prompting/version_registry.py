"""PromptOps version registry — lifecycle management and run metrics.

Manages prompt versions through draft → canary → active → deprecated lifecycle.
Records every LLM invocation as a PromptRun with metrics for observability.
"""
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class PromptStatus(str, Enum):
    DRAFT = "draft"
    CANARY = "canary"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class PromptVersion:
    prompt_version_id: str
    name: str
    role_scope: str
    template_hash: str
    status: PromptStatus = PromptStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    template: str = ""


@dataclass
class PromptRun:
    run_id: str
    prompt_version_id: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    tool_calls: int
    schema_validation_passed: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PromptVersionRegistry:
    """In-memory prompt version registry (production would use DB)."""

    def __init__(self):
        self._versions: Dict[str, PromptVersion] = {}
        self._runs: List[PromptRun] = []

    def register(self, name: str, role_scope: str, template: str) -> PromptVersion:
        """Register a new prompt version in DRAFT status."""
        version_id = f"pv_{uuid.uuid4().hex[:12]}"
        template_hash = hashlib.sha256(template.encode()).hexdigest()
        version = PromptVersion(
            prompt_version_id=version_id,
            name=name,
            role_scope=role_scope,
            template_hash=template_hash,
            status=PromptStatus.DRAFT,
            template=template,
        )
        self._versions[version_id] = version
        return version

    def get_version(self, version_id: str) -> Optional[PromptVersion]:
        return self._versions.get(version_id)

    def get_active(self, name: str) -> Optional[PromptVersion]:
        """Get the currently active version for a given prompt name."""
        for v in self._versions.values():
            if v.name == name and v.status == PromptStatus.ACTIVE:
                return v
        return None

    def activate(self, version_id: str) -> None:
        """Promote version to ACTIVE, deprecating any previous active for same name."""
        version = self._versions.get(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found")

        # Deprecate current active for same name
        for v in self._versions.values():
            if v.name == version.name and v.status == PromptStatus.ACTIVE:
                v.status = PromptStatus.DEPRECATED

        version.status = PromptStatus.ACTIVE

    def promote_to_canary(self, version_id: str) -> None:
        """Move version from DRAFT to CANARY."""
        version = self._versions.get(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found")
        version.status = PromptStatus.CANARY

    def deprecate(self, version_id: str) -> None:
        """Explicitly deprecate a version."""
        version = self._versions.get(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found")
        version.status = PromptStatus.DEPRECATED

    def record_run(
        self,
        prompt_version_id: str,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        tool_calls: int,
        schema_validation_passed: bool,
    ) -> PromptRun:
        """Record a single LLM invocation with metrics."""
        run = PromptRun(
            run_id=f"pr_{uuid.uuid4().hex[:12]}",
            prompt_version_id=prompt_version_id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            schema_validation_passed=schema_validation_passed,
        )
        self._runs.append(run)
        return run

    def list_runs(self, prompt_version_id: str) -> List[PromptRun]:
        """List all runs for a specific prompt version."""
        return [r for r in self._runs if r.prompt_version_id == prompt_version_id]

    def get_version_stats(self, prompt_version_id: str) -> Dict[str, Any]:
        """Compute aggregate metrics for a prompt version."""
        runs = self.list_runs(prompt_version_id)
        if not runs:
            return {"total_runs": 0, "avg_latency_ms": 0.0, "schema_pass_rate": 0.0}

        total = len(runs)
        avg_latency = sum(r.latency_ms for r in runs) / total
        pass_count = sum(1 for r in runs if r.schema_validation_passed)

        return {
            "total_runs": total,
            "avg_latency_ms": avg_latency,
            "schema_pass_rate": pass_count / total,
            "total_input_tokens": sum(r.input_tokens for r in runs),
            "total_output_tokens": sum(r.output_tokens for r in runs),
            "avg_tool_calls": sum(r.tool_calls for r in runs) / total,
        }


# Global singleton instance
prompt_version_registry = PromptVersionRegistry()

