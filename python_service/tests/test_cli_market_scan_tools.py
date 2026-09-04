"""Tests for cli.run_market_scan_then_sector tool-call dispatch (bugfix).

Regression guard: run_market_scan_then_sector used to call
    llm_gateway.generate_with_tools(context, model=..., max_tool_rounds=20)
— a method that does NOT exist on LLMGateway — so the market-scan step
raised AttributeError (surfacing as "Market scan failed: ...") whenever
the resolved model was a DeepSeek model. The fix routes tool-capable
models through agent_orchestrator.generate_with_tools with the same
capability gating as the API scan path (app.api.sector):

  - Gemini             -> llm_gateway.generate_content (native grounding)
  - DeepSeek           -> agent_orchestrator.generate_with_tools (native FC)
  - MiniMax/OpenRouter -> agent_orchestrator.generate_with_tools (text tool
                          protocol: tool docs injected, tools_enabled=True)

All heavy dependencies (prompt runtime, LLM gateway, orchestrator, tool
docs, interactive prompt) are mocked — the tests only assert which entry
point is called and with which keyword arguments.
"""
import asyncio
import importlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service import cli  # noqa: E402

# 7-column recommendation-table rows, as produced by the scanner prompt:
# the CLI extracts sector names from the second column of these rows.
SCAN_RESULT = (
    "| ⭐1 | 半导体 | 强 | 高 | 政策+需求 | a | b |\n"
    "| ⭐2 | 新能车 | 中 | 中 | 销量回暖 | a | b |\n"
)


@pytest.fixture
def scan_mocks(monkeypatch):
    """Mock every external dependency of run_market_scan_then_sector.

    Patch points:
      - cli.load_config / cli.is_deprecated_model: module-level names in
        cli's namespace.
      - prompt_runtime, agent_orchestrator, llm_gateway, format_tool_descriptions:
        imported INSIDE the function via "from app... import ...", so the
        source modules must be patched. conftest aliases app.* ->
        python_service.app.* only for modules loaded at conftest runtime;
        force both names onto the same module object here.
      - click.prompt: the interactive sector-selection loop (0 = exit).
    """
    fake_orchestrator = MagicMock()
    fake_orchestrator.generate_with_tools = AsyncMock(return_value=SCAN_RESULT)

    fake_gateway = MagicMock()
    fake_gateway.generate_content = AsyncMock(return_value=SCAN_RESULT)

    monkeypatch.setattr(cli, "load_config", lambda: {})
    monkeypatch.setattr(cli, "is_deprecated_model", lambda m: False)

    pr_module = importlib.import_module("python_service.app.prompting.runtime")
    monkeypatch.setitem(sys.modules, "app.prompting.runtime", pr_module)
    fake_prompt_runtime = MagicMock()
    fake_prompt_runtime.get_prompt = MagicMock(return_value={"template": "scanner template"})
    monkeypatch.setattr(pr_module, "prompt_runtime", fake_prompt_runtime)

    ao_module = importlib.import_module("python_service.app.services.agent_orchestrator")
    monkeypatch.setitem(sys.modules, "app.services.agent_orchestrator", ao_module)
    monkeypatch.setattr(ao_module, "agent_orchestrator", fake_orchestrator)

    gw_module = importlib.import_module("python_service.app.services.llm_gateway")
    monkeypatch.setitem(sys.modules, "app.services.llm_gateway", gw_module)
    monkeypatch.setattr(gw_module, "llm_gateway", fake_gateway)

    et_module = importlib.import_module("python_service.app.services.expert_tools")
    monkeypatch.setitem(sys.modules, "app.services.expert_tools", et_module)
    monkeypatch.setattr(
        et_module,
        "format_tool_descriptions",
        lambda role=None, language="zh-CN": "[TEXT TOOL DOCS]",
    )

    # Exit the interactive sector-selection loop right after the scan.
    prompt_mock = MagicMock(return_value=0)
    monkeypatch.setattr(cli.click, "prompt", prompt_mock)

    return SimpleNamespace(
        orchestrator=fake_orchestrator,
        gateway=fake_gateway,
        prompt_runtime=fake_prompt_runtime,
        prompt=prompt_mock,
    )


def _run(model):
    return asyncio.run(cli.run_market_scan_then_sector(None, model))


def test_deepseek_scan_uses_orchestrator_native_fc(scan_mocks):
    """DeepSeek must go through agent_orchestrator.generate_with_tools with
    tools_enabled=False (native function calling inside) — NOT through the
    nonexistent llm_gateway.generate_with_tools (the original AttributeError)."""
    _run("deepseek-v4-pro")

    scan_mocks.orchestrator.generate_with_tools.assert_called_once()
    args, kwargs = scan_mocks.orchestrator.generate_with_tools.call_args
    assert args[0].startswith("\n--- SYSTEM DIRECTIVE ---")
    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["max_tool_rounds"] == 20
    assert kwargs["tools_enabled"] is False
    # No text-protocol tool docs injection for DeepSeek.
    assert "[TEXT TOOL DOCS]" not in args[0]
    scan_mocks.gateway.generate_content.assert_not_called()


def test_minimax_scan_uses_text_tool_protocol(scan_mocks):
    """Non-Gemini non-DeepSeek models (MiniMax / OpenRouter) must use the
    text tool protocol: tool docs injected into the prompt and
    tools_enabled=True. The old gate `use_tools = "deepseek" in model` sent
    them down the tool-less generate_content branch despite the SYSTEM
    DIRECTIVE demanding web_search."""
    _run("minimax/minimax-m3:free")

    scan_mocks.orchestrator.generate_with_tools.assert_called_once()
    args, kwargs = scan_mocks.orchestrator.generate_with_tools.call_args
    assert kwargs["model"] == "minimax/minimax-m3:free"
    assert kwargs["max_tool_rounds"] == 20
    assert kwargs["tools_enabled"] is True
    assert "[TEXT TOOL DOCS]" in args[0]
    assert "SEARCH TOOL STATUS" in args[0]
    scan_mocks.gateway.generate_content.assert_not_called()


def test_gemini_scan_uses_plain_generate_content(scan_mocks):
    """Gemini models keep the plain generate_content path (native grounding
    inside llm_gateway); no orchestrator involvement."""
    _run("gemini-3.1-pro-preview")

    scan_mocks.gateway.generate_content.assert_called_once()
    args, kwargs = scan_mocks.gateway.generate_content.call_args
    assert args[0].startswith("\n--- SYSTEM DIRECTIVE ---")
    assert kwargs["model"] == "gemini-3.1-pro-preview"
    assert "[TEXT TOOL DOCS]" not in args[0]
    scan_mocks.orchestrator.generate_with_tools.assert_not_called()


def test_scan_result_is_consumed_and_sectors_extracted(scan_mocks):
    """The scan result is consumed as plain text: sector names are extracted
    from the 7-column recommendation table and offered for interactive
    selection (choice 0 exits before the deep sector flow runs)."""
    _run("deepseek-v4-pro")

    # The numbered-selection prompt fired (sectors were extracted from the
    # mocked scan result); the mocked answer 0 exits the flow cleanly.
    scan_mocks.prompt.assert_called_once()
    assert "输入编号选择" in scan_mocks.prompt.call_args.args[0]
