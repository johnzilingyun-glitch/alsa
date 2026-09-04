"""Tests for cli.run_sector_flow model fallback chain (hardening).

Regression guard: run_sector_flow used to resolve the model as
    model or cfg.get("model") or cfg.get("gemini_model")
with no final fallback, so OpenRouter-only deployments (no model in
~/.alsa_config.json, no DEFAULT_LLM_MODEL) fell through to None. The stock
flow (run_stock_flow) already falls back to DEFAULT_LLM_MODEL / 
"deepseek-v4-pro"; this file pins the same behaviour for the sector flow.

All heavy dependencies (DB session factory, job repo, sector service,
report service) are mocked — the test only asserts which model string
reaches SectorAnalysisService.start_sector_job.
"""
import asyncio
import importlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service import cli  # noqa: E402


class _FakeJobStatus:
    def __init__(self):
        self.status = "completed"
        self.result_payload = None
        self.error_message = None


@pytest.fixture
def sector_flow_mocks(monkeypatch, tmp_path):
    """Mock every external dependency of run_sector_flow and return the fake service.

    Patch points (how run_sector_flow resolves them):
      - cli.build_session_factory / cli.JobRepository / cli.load_config:
        module-level names in cli's namespace.
      - app.services.sector_analysis_service.SectorAnalysisService and
        app.services.sector_report_service.SectorReportService:
        imported INSIDE the function, so the source modules must be patched.
    """
    fake_service = MagicMock()
    fake_service.start_sector_job = AsyncMock(return_value="sector_cli_test")
    fake_service.get_progress = AsyncMock(return_value={"message": "done"})
    fake_service.get_result = MagicMock(return_value={"final": "report"})

    fake_repo = MagicMock()
    fake_repo.get_by_id = MagicMock(return_value=_FakeJobStatus())

    fake_report = MagicMock()
    fake_report.generate_sector_report = AsyncMock(return_value=str(tmp_path / "out.html"))

    monkeypatch.setattr(cli, "build_session_factory", lambda url: "fake-factory")
    monkeypatch.setattr(cli, "JobRepository", lambda factory: fake_repo)
    monkeypatch.setattr(cli, "load_config", lambda: {})
    monkeypatch.setattr(cli, "is_deprecated_model", lambda m: False)

    # run_sector_flow imports these INSIDE the function via
    # "from app.services... import ...". conftest aliases app.* →
    # python_service.app.* only for modules loaded at conftest runtime, so the
    # function-level import may otherwise resolve to a DIFFERENT module object
    # than the one we patch. Force both names onto the same object.
    sas_module = importlib.import_module("python_service.app.services.sector_analysis_service")
    monkeypatch.setitem(sys.modules, "app.services.sector_analysis_service", sas_module)
    monkeypatch.setattr(sas_module, "SectorAnalysisService", lambda job_repo: fake_service)

    srs_module = importlib.import_module("python_service.app.services.sector_report_service")
    monkeypatch.setitem(sys.modules, "app.services.sector_report_service", srs_module)
    monkeypatch.setattr(srs_module, "SectorReportService", lambda: fake_report)

    return fake_service


def _run(sector_name="化肥", output_path=None, model=None):
    return asyncio.run(cli.run_sector_flow(sector_name, output_path, model))


def test_run_sector_flow_falls_back_to_builtin_default(sector_flow_mocks, monkeypatch):
    """No CLI model, no config model, no DEFAULT_LLM_MODEL env -> builtin
    default 'deepseek-v4-pro' (same fallback as the stock flow)."""
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
    _run()
    assert sector_flow_mocks.start_sector_job.call_args.kwargs["model"] == "deepseek-v4-pro"


def test_run_sector_flow_falls_back_to_default_llm_model_env(sector_flow_mocks, monkeypatch):
    """DEFAULT_LLM_MODEL env wins over the builtin default."""
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "qwen/qwen3-coder:free")
    _run()
    assert sector_flow_mocks.start_sector_job.call_args.kwargs["model"] == "qwen/qwen3-coder:free"


def test_run_sector_flow_config_model_beats_env(sector_flow_mocks, monkeypatch):
    """Config file model takes precedence over the DEFAULT_LLM_MODEL env."""
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "qwen/qwen3-coder:free")
    monkeypatch.setattr(cli, "load_config", lambda: {"model": "cfg-model"})
    _run()
    assert sector_flow_mocks.start_sector_job.call_args.kwargs["model"] == "cfg-model"


def test_run_sector_flow_explicit_model_wins(sector_flow_mocks, monkeypatch):
    """Explicit --model option beats config, gemini_model and env."""
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "qwen/qwen3-coder:free")
    monkeypatch.setattr(
        cli, "load_config", lambda: {"model": "cfg-model", "gemini_model": "cfg-gemini"}
    )
    _run(model="explicit-model")
    assert sector_flow_mocks.start_sector_job.call_args.kwargs["model"] == "explicit-model"
