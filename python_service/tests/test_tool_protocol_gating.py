"""Regression tests for the text-tool-protocol gating fix (2026-09-01).

Background bug: the project default model is minimax/minimax-m3:free
(OpenRouter). In discussion_service._call_expert the gating was:

    has_search_tools  = "gemini" in model.lower()
    use_native_tools   = "deepseek" in model.lower()
    tool_descriptions generated only when `has_search_tools and not
    use_native_tools` (i.e. only Gemini), while Gemini takes the
    llm_gateway.generate_content native-grounding branch and never enters
    the text tool loop. MiniMax DID enter agent_orchestrator's text tool
    loop but its prompt carried no tool list / TOOL CALL FORMAT → round 0
    produced no tool_call tags → the loop exited immediately ([ToolLoop]
    Round always 0). Mirror bug in sector._run_scan: use_tools =
    "deepseek" in model.lower() → MiniMax scans ran tool-less while the
    prompt demanded MUST web_search.

Fix under test:
  1. discussion path: `use_text_tool_protocol = not has_search_tools and
     not use_native_tools` — text-loop models get format_tool_descriptions()
     injected (SEARCH TOOL STATUS "已启用" + tool list + TOOL CALL FORMAT);
     Gemini/DeepSeek behavior unchanged.
  2. sector._run_scan: same capability detection + tool-doc injection into
     the scan context for text-loop models.
  3. serenity single-round topology: the lone node now WAITS (bounded) for
     the background search task instead of checking search_task.done()
     before the search can ever have produced results.
  4. critic_agent / self_reflection_agent no longer pass the unsupported
     `max_tokens` kwarg to LLMGateway.generate_content (TypeError was
     swallowed by the surrounding except → permanent degraded branch).
"""
import asyncio
import time
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.discussion_service import DiscussionService
from python_service.app.api import sector as sector_api

# High-confidence JSON payload: keeps the smart verification pipeline from
# triggering self-reflection / extra LLM calls in the mocked flow.
EXPERT_REPLY = (
    '{"core_thesis": "化肥板块景气度向上，钾肥价格处于上行周期。", '
    '"confidence": 0.85, "rating": "Buy", "risks": [], "key_metrics_extracted": []}'
)

SECTOR_SNAPSHOT = {
    "name": "化肥",
    "type": "sector",
    "timestamp": "2026-09-01T12:00:00",
}

MINIMAX_MODEL = "minimax/minimax-m3:free"
GEMINI_MODEL = "gemini-3.1-pro-preview"
DEEPSEEK_MODEL = "deepseek-v4-pro"


def _discussion_mock_stack(tool_prompts, direct_prompts):
    """Mocks for running run_discussion fully offline.

    tool_prompts  — every prompt sent to agent_orchestrator.generate_with_tools
                    (the transport text-loop models actually take).
    direct_prompts — every prompt sent to llm_gateway.generate_content
                    (the Gemini native-grounding transport).
    """
    async def fake_generate_content(prompt, *args, **kwargs):
        direct_prompts.append(prompt)
        return EXPERT_REPLY

    async def fake_generate_with_tools(prompt, *args, **kwargs):
        tool_prompts.append(prompt)
        return EXPERT_REPLY

    return [
        patch(
            "app.services.discussion_service.llm_gateway.generate_content",
            AsyncMock(side_effect=fake_generate_content),
        ),
        patch(
            "app.services.agent_orchestrator.agent_orchestrator.generate_with_tools",
            AsyncMock(side_effect=fake_generate_with_tools),
        ),
        patch(
            "app.services.search_toolkit.search_toolkit.batch_search",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.services.macro_service.macro_service.get_latest_fx",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.services.macro_service.macro_service.get_commodity_prices",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.services.macro_service.macro_service.get_brent_oil_price",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.services.macro_service.macro_service.get_macro_indicators",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.services.agent_memory.agent_memory.recall",
            AsyncMock(return_value=SimpleNamespace(entries=[])),
        ),
        patch(
            "app.services.agent_memory.agent_memory.store",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.services.self_reflection_agent.self_reflection_agent.reflect",
            AsyncMock(return_value={}),
        ),
    ]


def _apply_stack(patchers):
    stack = ExitStack()
    for p in patchers:
        stack.enter_context(p)
    return stack


async def _run_serenity_discussion(model):
    """Run the single-expert serenity_alpha flow offline; return prompts."""
    ds = DiscussionService()
    tool_prompts, direct_prompts = [], []
    with _apply_stack(_discussion_mock_stack(tool_prompts, direct_prompts)):
        results = await ds.run_discussion(
            symbol="化肥",
            name="化肥",
            snapshot=dict(SECTOR_SNAPSHOT),
            level="serenity_alpha",
            market="sector",
            model=model,
        )
    return results, tool_prompts, direct_prompts


# ---------- 1. Discussion path: text-tool-protocol prompt injection ----------

@pytest.mark.asyncio
async def test_minimax_prompt_contains_text_tool_protocol():
    """THE bug: MiniMax (text tool loop) must receive the tool list, TOOL CALL
    FORMAT and the "已启用" status inside its prompt — previously the prompt
    had none of them, so the loop could never emit tool_call tags."""
    results, tool_prompts, direct_prompts = await _run_serenity_discussion(MINIMAX_MODEL)

    assert len(tool_prompts) >= 1, "MiniMax must go through generate_with_tools"
    assert not direct_prompts, "MiniMax must NOT take the Gemini native-grounding branch"

    prompt = tool_prompts[0]
    # "已启用" status section
    assert "搜索工具状态: 工具调用已启用" in prompt
    # Full tool list
    assert "# 可用工具" in prompt
    assert "## web_search" in prompt
    # Text protocol call syntax
    assert "# 工具调用格式" in prompt
    assert "tool: web_search" in prompt
    # The expert really ran (not a System abort)
    assert results and results[0].get("role") == "Serenity Alpha Analyst"


@pytest.mark.asyncio
async def test_gemini_path_unchanged_native_grounding():
    """Gemini keeps the native-grounding branch (generate_content, NOT the
    text tool loop) and its prompt structure is preserved — including the
    tool documentation it has always carried (pre-existing behavior)."""
    results, tool_prompts, direct_prompts = await _run_serenity_discussion(GEMINI_MODEL)

    assert len(direct_prompts) >= 1, "Gemini must keep llm_gateway.generate_content"
    assert not tool_prompts, "Gemini must NOT enter the text tool loop"

    prompt = direct_prompts[0]
    # Unchanged prompt structure (regression guard)
    assert "搜索工具状态: 工具调用已启用" in prompt
    assert "# 可用工具" in prompt


@pytest.mark.asyncio
async def test_deepseek_path_unchanged_no_text_protocol_docs():
    """DeepSeek keeps the native-function-calling transport and must NOT
    receive the text-protocol documentation (behavior unchanged)."""
    results, tool_prompts, direct_prompts = await _run_serenity_discussion(DEEPSEEK_MODEL)

    assert len(tool_prompts) >= 1, "DeepSeek keeps generate_with_tools (native FC inside)"
    assert not direct_prompts

    prompt = tool_prompts[0]
    # 注意: "--- [MANDATORY] SEARCH TOOL STATUS ---" 头部行在模板中位于
    # {% if %} 块之外、所有模型都会渲染(空节)——这是既有行为，不算回归；
    # 这里断言的是节【内容】不注入文本协议文档。
    assert "# 可用工具" not in prompt
    assert "# 工具调用格式" not in prompt
    assert "工具调用已启用" not in prompt


# ---------- 2. Sector scan path: _run_scan gating alignment ----------

SCAN_RESULT = "扫描结论：今日无突出板块。\n1. 化肥：钾肥价格上行\n"


def _scan_mock_factory():
    """session_factory mock whose context manager yields a MagicMock session
    (session.exec(...).all() -> [])."""
    session = MagicMock()
    session.exec.return_value.all.return_value = []
    factory = MagicMock(return_value=session)
    factory.return_value.__enter__.return_value = session
    factory.return_value.__exit__.return_value = False
    return factory


async def _run_scan_with(model):
    tool_mock = AsyncMock(return_value=SCAN_RESULT)
    direct_mock = AsyncMock(return_value=SCAN_RESULT)
    prompt_runtime_mock = MagicMock(
        return_value={"template": "扫描指令模板", "version": "v1"}
    )
    with patch(
        "python_service.app.services.agent_orchestrator.agent_orchestrator.generate_with_tools",
        tool_mock,
    ), patch(
        "python_service.app.services.llm_gateway.llm_gateway.generate_content",
        direct_mock,
    ), patch(
        "python_service.app.prompting.runtime.prompt_runtime.get_prompt",
        prompt_runtime_mock,
    ), patch(
        "python_service.app.db.database.session_factory",
        _scan_mock_factory(),
    ), patch(
        "python_service.app.api.sector._update_scan_job_redis",
        AsyncMock(),
    ):
        await sector_api._run_scan("scan_test001", model, "2026-09-01")
        # Drain the fire-and-forget progress-update tasks.
        await asyncio.sleep(0)
    return tool_mock, direct_mock


@pytest.mark.asyncio
async def test_run_scan_minimax_enables_text_tool_loop():
    """MiniMax scans must now run through the text tool loop AND the scan
    context must embed the text-protocol tool documentation (previously
    use_tools was deepseek-only and the prompt demanded web_search with no
    tools available)."""
    tool_mock, direct_mock = await _run_scan_with(MINIMAX_MODEL)

    assert tool_mock.await_count == 1
    assert direct_mock.await_count == 0

    prompt = tool_mock.call_args.args[0]
    assert "搜索工具状态: 工具调用已启用" in prompt
    assert "# 可用工具" in prompt
    assert "# 工具调用格式" in prompt
    assert "## web_search" in prompt
    assert "web_search" in prompt


@pytest.mark.asyncio
async def test_run_scan_gemini_keeps_native_grounding():
    """Gemini scans keep the llm_gateway.generate_content branch with NO
    text-protocol docs appended (behavior unchanged)."""
    tool_mock, direct_mock = await _run_scan_with(GEMINI_MODEL)

    assert direct_mock.await_count == 1
    assert tool_mock.await_count == 0

    prompt = direct_mock.call_args.args[0]
    assert "# 可用工具" not in prompt
    assert "# 工具调用格式" not in prompt


@pytest.mark.asyncio
async def test_run_scan_deepseek_keeps_native_function_calling():
    """DeepSeek scans keep the generate_with_tools branch (native FC inside)
    without text-protocol docs (behavior unchanged)."""
    tool_mock, direct_mock = await _run_scan_with(DEEPSEEK_MODEL)

    assert tool_mock.await_count == 1
    assert direct_mock.await_count == 0

    prompt = tool_mock.call_args.args[0]
    assert "# 可用工具" not in prompt
    assert "# 工具调用格式" not in prompt


# ---------- 3. Serenity single-round topology: background search timing ----------

@pytest.mark.asyncio
async def test_single_round_topology_waits_for_background_search():
    """The lone node of a single-round topology must WAIT for the background
    search instead of checking search_task.done() before it can ever be True.
    A 0.3s search must therefore land in the expert's prompt."""
    ds = DiscussionService()
    tool_prompts, direct_prompts = [], []
    search_delay = 0.3
    marker = "TIMING PROBE LATEST NEWS"

    async def slow_batch_search(symbol, name, snapshot, **kwargs):
        await asyncio.sleep(search_delay)
        return {
            "latest_news": [
                {"title": marker, "content": "钾肥价格上行", "source": "test"}
            ]
        }

    patchers = _discussion_mock_stack(tool_prompts, direct_prompts)
    # Replace the instant batch_search mock with the slow one.
    patchers[2] = patch(
        "app.services.search_toolkit.search_toolkit.batch_search",
        AsyncMock(side_effect=slow_batch_search),
    )

    start = time.monotonic()
    with _apply_stack(patchers):
        results = await ds.run_discussion(
            symbol="化肥",
            name="化肥",
            snapshot=dict(SECTOR_SNAPSHOT),
            level="serenity_alpha",
            market="sector",
            model=MINIMAX_MODEL,
        )
    elapsed = time.monotonic() - start

    # The node actually waited for the search (not elapsed-0 pass-through).
    assert elapsed >= search_delay
    # The search result reached the expert prompt (enrichment injection).
    assert tool_prompts and any(marker in p for p in tool_prompts)
    assert results and results[0].get("role") == "Serenity Alpha Analyst"


@pytest.mark.asyncio
async def test_single_round_topology_search_timeout_does_not_block():
    """If the background search exceeds the node-level wait budget, the
    discussion must still proceed (empty search results, non-blocking)."""
    ds = DiscussionService()
    tool_prompts, direct_prompts = [], []
    marker = "TIMING PROBE LATEST NEWS"

    async def very_slow_batch_search(symbol, name, snapshot, **kwargs):
        await asyncio.sleep(5.0)
        return {"latest_news": [{"title": marker, "content": "x", "source": "test"}]}

    patchers = _discussion_mock_stack(tool_prompts, direct_prompts)
    patchers[2] = patch(
        "app.services.search_toolkit.search_toolkit.batch_search",
        AsyncMock(side_effect=very_slow_batch_search),
    )
    # Shrink the node wait budget so the test runs fast.
    wait_budget_patch = patch(
        "app.services.discussion_service._NODE_SEARCH_WAIT_SECONDS", 0.15
    )

    start = time.monotonic()
    with _apply_stack(patchers), wait_budget_patch:
        results = await ds.run_discussion(
            symbol="化肥",
            name="化肥",
            snapshot=dict(SECTOR_SNAPSHOT),
            level="serenity_alpha",
            market="sector",
            model=MINIMAX_MODEL,
        )
    elapsed = time.monotonic() - start

    # Proceeded without the search results and without blocking for 5s.
    assert elapsed < 3.0
    assert tool_prompts and not any(marker in p for p in tool_prompts)
    assert results and results[0].get("role") == "Serenity Alpha Analyst"
    # Let the orphaned background task finish so pytest doesn't warn.
    await asyncio.sleep(0.05)
    await asyncio.sleep(0)


# ---------- 4. search_toolkit.batch_search time budget ----------

@pytest.mark.asyncio
async def test_batch_search_time_budget_returns_partial_results():
    """With a time budget, batch_search stops launching new categories once
    the budget is exhausted and returns the completed ones (instead of being
    killed wholesale by the outer timeout)."""
    from app.services.search_toolkit import (
        SearchToolkit,
        SEARCH_CATEGORIES,
        A_SHARE_EXTRA_CATEGORIES,
    )

    async def fake_search(query, max_results=3):
        await asyncio.sleep(0.04)
        return [{"title": "t", "content": "c", "source": "s"}]

    toolkit = SearchToolkit()
    toolkit._rate_limit_delay = 0  # strip rate limiting for determinism
    total_categories = len(SEARCH_CATEGORIES) + len(A_SHARE_EXTRA_CATEGORIES)

    with patch(
        "app.services.search_toolkit.search_service.search",
        AsyncMock(side_effect=fake_search),
    ):
        # Budget exhausted mid-way → partial results.
        partial = await toolkit.batch_search(
            "600519", "贵州茅台", None, time_budget=0.06
        )
        # No budget → all categories (old behavior preserved). Different
        # symbol: batch_search caches per symbol for 10 minutes.
        full = await toolkit.batch_search("000792", "盐湖股份", None)

    assert 0 < len(partial) < total_categories
    assert len(full) == total_categories


# ---------- 5. critic_agent / self_reflection_agent gateway kwargs ----------

CRITIC_JSON = (
    '{"consensus_points": [], "major_disagreements": [], "data_conflicts": [], '
    '"bias_assessment": {"overall_bias": "neutral", "bias_magnitude": "mild", '
    '"evidence": "-"}, "risk_flags": [], "missing_perspectives": [], '
    '"overall_score": 80, "confidence_level": "high", "recommendation": "ok"}'
)

REFLECTION_JSON = (
    '{"logic_gaps": [], "missing_info": [], "cognitive_biases": [], '
    '"unverified_assumptions": [], "data_contradictions": [], '
    '"confidence_score": 0.9, "improved_analysis": "ok"}'
)


@pytest.mark.asyncio
async def test_critic_agent_no_max_tokens_kwarg():
    """critique() must call LLMGateway.generate_content with only kwargs the
    gateway signature supports — the old max_tokens=2000 raised TypeError on
    every call and the surrounding except silently degraded the critique."""
    from app.services import critic_agent as critic_module

    captured = {}

    async def fake_generate_content(prompt, **kwargs):
        captured.update(kwargs)
        return CRITIC_JSON

    with patch.object(
        critic_module.llm_gateway, "generate_content",
        AsyncMock(side_effect=fake_generate_content),
    ):
        result = await critic_module.critic_agent.critique(
            analyses=[{"role": "A", "content": "看多"}],
            symbol="600519",
            name="贵州茅台",
            model=MINIMAX_MODEL,
        )

    assert "max_tokens" not in captured
    assert captured.get("temperature") == 0.2  # supported kwarg preserved
    assert result["symbol"] == "600519"
    assert result["critique"]["overall_score"] == 80


@pytest.mark.asyncio
async def test_self_reflection_agent_no_max_tokens_kwarg():
    """Same kwarg fix for reflect() (identical bug class found by the
    repo-wide max_tokens grep)."""
    from app.services import self_reflection_agent as sra_module

    captured = {}

    async def fake_generate_content(prompt, **kwargs):
        captured.update(kwargs)
        return REFLECTION_JSON

    with patch.object(
        sra_module.llm_gateway, "generate_content",
        AsyncMock(side_effect=fake_generate_content),
    ):
        result = await sra_module.self_reflection_agent.reflect(
            analysis="基本面稳健",
            expert_role="Fundamental Analyst",
            round_num=1,
            total_rounds=3,
            context={},
            model=MINIMAX_MODEL,
        )

    assert "max_tokens" not in captured
    assert captured.get("temperature") == 0.3
    assert result["reflection"]["confidence_score"] == 0.9
