"""Tests for sector API model resolution (_resolve_model) and request validation.

Regression guard for the "启动扫描失败/启动分析失败" bug: _resolve_model only
knew the GEMINI/DEEPSEEK fallback chain while the project default LLM switched
to OpenRouter MiniMax M3 (free). When no model was explicitly requested and no
Gemini/DeepSeek key existed, sector scan / deep analysis startup failed with
INVALID_PARAM even though OPENROUTER_API_KEY was configured.

Expected fallback chain (mirrors llm_gateway._generate_content_inner, where
OpenRouter is tried FIRST for non-gemini models):
    explicit model > OPENROUTER key > GEMINI key > DEEPSEEK key > ValueError
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Add project root to path (same pattern as test_pipeline_routing.py)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from python_service.main import app  # noqa: E402
from python_service.app.api.sector import (  # noqa: E402
    SectorAnalyzeRequest,
    SerenityAnalyzeRequest,
    _resolve_model,
)

# Env vars that drive _resolve_model — tests must control them explicitly
# because llm_gateway/brain_manager call load_dotenv('.env.runtime') at import
# time, which can leak real API keys into the test process.
_LLM_ENV_KEYS = (
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
    "DEFAULT_LLM_MODEL",
    "GEMINI_MODEL",
    "DEEPSEEK_MODEL",
)


@pytest.fixture
def clean_llm_env(monkeypatch):
    """Remove every LLM-related env var so _resolve_model starts from a clean slate."""
    for key in _LLM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


# ---------- _resolve_model unit tests ----------

def test_explicit_model_passthrough(clean_llm_env):
    """An explicitly requested model always wins, even with no keys configured."""
    assert _resolve_model("my-custom-model") == "my-custom-model"


def test_openrouter_only_resolves_default_model(clean_llm_env):
    """Only OPENROUTER_API_KEY present -> OpenRouter default model (the bug fix)."""
    clean_llm_env.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert _resolve_model() == "minimax/minimax-m3:free"


def test_openrouter_default_follows_default_llm_model_env(clean_llm_env):
    """OpenRouter fallback resolves via DEFAULT_LLM_MODEL — same source as
    LLMGateway.default_model (app/services/llm_gateway.py)."""
    clean_llm_env.setenv("OPENROUTER_API_KEY", "sk-or-test")
    clean_llm_env.setenv("DEFAULT_LLM_MODEL", "qwen/qwen3-coder:free")
    assert _resolve_model() == "qwen/qwen3-coder:free"


def test_openrouter_empty_default_llm_model_falls_back_to_builtin_default(clean_llm_env):
    """DEFAULT_LLM_MODEL present but EMPTY must fall back to the builtin default,
    not resolve to "" — an empty model name would fail every provider after
    the job has already started (hardening: getenv default only catches a
    MISSING var, not a present-but-empty one)."""
    clean_llm_env.setenv("OPENROUTER_API_KEY", "sk-or-test")
    clean_llm_env.setenv("DEFAULT_LLM_MODEL", "")
    assert _resolve_model() == "minimax/minimax-m3:free"


def test_gemini_branch_preserved(clean_llm_env):
    """Only GEMINI_API_KEY present -> gemini default model (pre-existing branch)."""
    clean_llm_env.setenv("GEMINI_API_KEY", "gem-test")
    assert _resolve_model() == "gemini-3.5-flash"


def test_gemini_model_env_override_preserved(clean_llm_env):
    clean_llm_env.setenv("GEMINI_API_KEY", "gem-test")
    clean_llm_env.setenv("GEMINI_MODEL", "gemini-custom")
    assert _resolve_model() == "gemini-custom"


def test_deepseek_branch_preserved(clean_llm_env):
    """Only DEEPSEEK_API_KEY present -> deepseek default model (pre-existing branch)."""
    clean_llm_env.setenv("DEEPSEEK_API_KEY", "ds-test")
    assert _resolve_model() == "deepseek-v4-pro"


def test_gemini_preferred_over_deepseek_preserved(clean_llm_env):
    """GEMINI > DEEPSEEK relative ordering is unchanged from the original chain."""
    clean_llm_env.setenv("GEMINI_API_KEY", "gem-test")
    clean_llm_env.setenv("DEEPSEEK_API_KEY", "ds-test")
    assert _resolve_model() == "gemini-3.5-flash"


def test_openrouter_preferred_when_all_keys_present(clean_llm_env):
    """All three keys present -> OpenRouter default model. This matches
    llm_gateway._generate_content_inner, which tries OpenRouter FIRST for
    non-gemini models, keeping a single provider ordering across layers."""
    clean_llm_env.setenv("OPENROUTER_API_KEY", "sk-or-test")
    clean_llm_env.setenv("GEMINI_API_KEY", "gem-test")
    clean_llm_env.setenv("DEEPSEEK_API_KEY", "ds-test")
    assert _resolve_model() == "minimax/minimax-m3:free"


def test_no_keys_raises_value_error(clean_llm_env):
    """No provider key at all -> ValueError mentioning all three providers."""
    with pytest.raises(ValueError) as excinfo:
        _resolve_model()
    message = str(excinfo.value)
    assert "OpenRouter" in message
    assert "Gemini" in message
    assert "DeepSeek" in message


# ---------- Request model validation ----------

def test_sector_analyze_request_rejects_empty_sector_name():
    with pytest.raises(Exception):
        SectorAnalyzeRequest(sector_name="", model="m")


def test_sector_analyze_request_rejects_whitespace_only_sector_name():
    """Pure-whitespace sector_name (" ") must be rejected — min_length=1
    alone lets it through, creating a meaningless analysis job."""
    with pytest.raises(Exception):
        SectorAnalyzeRequest(sector_name=" ", model="m")


def test_serenity_request_rejects_whitespace_only_sector_name():
    """Same whitespace guard for the serenity request model."""
    with pytest.raises(Exception):
        SerenityAnalyzeRequest(sector_name=" ", model="m")


def test_sector_analyze_request_allows_padded_sector_name_unchanged():
    """Names that merely CONTAIN spaces (e.g. " 化肥 ") must stay valid AND
    keep their original value — pattern=\S uses re.search semantics, so it
    requires at least one non-whitespace char without stripping or rejecting
    padded names."""
    req = SectorAnalyzeRequest(sector_name=" 化肥 ", model="m")
    assert req.sector_name == " 化肥 "
    req = SerenityAnalyzeRequest(sector_name=" 化肥 ", model="m")
    assert req.sector_name == " 化肥 "


def test_serenity_request_allows_none_sector_name():
    """None must stay valid so the handler keeps its "A股市场" default."""
    req = SerenityAnalyzeRequest()
    assert req.sector_name is None
    req = SerenityAnalyzeRequest(sector_name=None, model="m")
    assert req.sector_name is None


def test_serenity_request_rejects_empty_sector_name():
    with pytest.raises(Exception):
        SerenityAnalyzeRequest(sector_name="", model="m")


# ---------- API-level tests (TestClient, API_TOKEN=mock-token bypasses auth) ----------

def test_analyze_endpoint_empty_sector_name_returns_422():
    """POST /api/sector/analyze with sector_name='' is rejected by Pydantic
    before any job is started."""
    client = TestClient(app)
    response = client.post(
        "/api/sector/analyze",
        json={"sector_name": "", "model": "minimax/minimax-m3:free", "force": True},
    )
    assert response.status_code == 422


def test_serenity_endpoint_empty_sector_name_returns_422():
    client = TestClient(app)
    response = client.post(
        "/api/sector/serenity-analyze",
        json={"sector_name": "", "model": "minimax/minimax-m3:free", "force": True},
    )
    assert response.status_code == 422


def test_analyze_endpoint_whitespace_sector_name_returns_422():
    """POST /api/sector/analyze with sector_name=' ' is rejected by Pydantic
    before any job is started (hardening for min_length-only validation)."""
    client = TestClient(app)
    response = client.post(
        "/api/sector/analyze",
        json={"sector_name": " ", "model": "minimax/minimax-m3:free", "force": True},
    )
    assert response.status_code == 422


def test_serenity_endpoint_whitespace_sector_name_returns_422():
    """POST /api/sector/serenity-analyze with sector_name=' ' is rejected
    before any job is started."""
    client = TestClient(app)
    response = client.post(
        "/api/sector/serenity-analyze",
        json={"sector_name": " ", "model": "minimax/minimax-m3:free", "force": True},
    )
    assert response.status_code == 422


def test_scan_endpoint_without_any_key_returns_invalid_param(clean_llm_env):
    """POST /api/sector/run with no model and no provider key returns the
    INVALID_PARAM error response instead of starting a job."""
    client = TestClient(app)
    response = client.post("/api/sector/run", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_PARAM"
    # Error message must now mention all three providers
    assert "OpenRouter" in data["error"]["message"]
