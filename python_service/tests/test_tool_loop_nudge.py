"""Tests for the one-shot tool-use compliance nudge in the text tool loop.

Background: MiniMax M3 (free) follows the text tool protocol only
probabilistically — it reads the injected tool docs, references real tool
names, but replies with "must verify via finance_query / business_query"
disclaimers instead of emitting a tool-call block. generate_with_tools now
carries a one-shot nudge: when tools are enabled and a round produces no
tool call, the response is echoed back with a MANDATORY TOOL USE REMINDER
and the loop runs one more round (bounded by the existing iteration cap).

Covered:
  1. nudge converts a tool-free round into a real tool round
  2. non-compliance after the nudge is accepted after exactly one retry
  3. a first-round tool call never triggers the nudge
  4. tools_enabled=False keeps the legacy behavior
  5. the nudge respects the round cap (total iterations never grow)
  6. an unparseable tool block also triggers the nudge
  7. callers (sector scan / expert discussion) pass tools_enabled correctly
"""
import asyncio
import logging
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_orchestrator import agent_orchestrator, TOOL_NUDGE_TEXT
from app.services.discussion_service import DiscussionService
from python_service.app.api import sector as sector_api

# Text-protocol tool-call block markers (XML-style ASCII tags), assembled
# from codepoints so the literal tag text never appears verbatim in this
# source file (it confuses tool-call parsing when echoed).
TOOL_OPEN = "".join(chr(c) for c in (60, 116, 111, 111, 108, 95, 99, 97, 108, 108, 62))
TOOL_CLOSE = "".join(chr(c) for c in (60, 47, 116, 111, 111, 108, 95, 99, 97, 108, 108, 62))

MINIMAX_MODEL = "minimax/minimax-m3:free"
DEEPSEEK_MODEL = "deepseek-v4-pro"

TOOL_OBSERVATION = (
    "[Tool: news_search | Query: 化肥板块 钾肥价格]\n"
    "钾肥价格持续上行，盐湖股份 000792 半年报超预期，营收同比增长 12%；\n"
    "亚钾国际 000893 老挝扩产顺利，产能爬坡至 300 万吨/年，行业景气度确认。"
)


def _tool_call_block(tool="news_search", reason="获取化肥板块最新量价数据", query="化肥板块 钾肥价格"):
    """A well-formed text-protocol tool call (parse_tool_calls must accept it)."""
    return (
        f"{TOOL_OPEN}\n"
        f"tool: {tool}\n"
        f"reason: {reason}\n"
        f"query: {query}\n"
        f"{TOOL_CLOSE}"
    )


def _loop_mocks(llm_responses):
    """Patch the loop's two I/O points; record every prompt sent to the LLM.

    An LLM round beyond the scripted responses raises AssertionError — this
    turns "nudge caused an unexpected extra round" into a hard test failure
    instead of an IndexError.
    """
    prompts = []

    async def fake_generate_content(prompt, *args, **kwargs):
        prompts.append(prompt)
        if len(prompts) > len(llm_responses):
            raise AssertionError(
                f"unexpected extra LLM round #{len(prompts)} (scripted: {len(llm_responses)})"
            )
        return llm_responses[len(prompts) - 1]

    llm_mock = AsyncMock(side_effect=fake_generate_content)
    exec_mock = AsyncMock(return_value=[TOOL_OBSERVATION])
    return llm_mock, exec_mock, prompts


async def _run_loop(responses, *, max_tool_rounds=5, tools_enabled=True):
    llm_mock, exec_mock, prompts = _loop_mocks(responses)
    with patch(
        "app.services.agent_orchestrator.llm_gateway.generate_content", llm_mock
    ), patch(
        "app.services.agent_orchestrator.tool_executor.execute_all", exec_mock
    ):
        result = await agent_orchestrator.generate_with_tools(
            "分析化肥板块景气度",
            model=MINIMAX_MODEL,  # text-protocol path (not gemini/deepseek)
            max_tool_rounds=max_tool_rounds,
            tools_enabled=tools_enabled,
        )
    return result, llm_mock, exec_mock, prompts


# ---------- 1. nudge converts a tool-free round into a real tool round ----------

@pytest.mark.asyncio
async def test_nudge_recovers_tool_call_after_tool_free_round():
    """Round 1 replies with the observed 'must verify via finance_query'
    disclaimer (no tool block) -> the nudge is appended -> round 2 emits a
    real tool call -> tool executed -> round 3 delivers the final grounded
    answer."""
    disclaimer = (
        "由于搜索工具未返回公司层面数据，D 节代表性公司仅为方向性标注，"
        "必须通过 finance_query / business_query 工具逐一核实。"
    )
    final = "基于工具结果：化肥板块钾肥价格上行，代表性标的为盐湖股份与亚钾国际。"
    result, llm_mock, exec_mock, prompts = await _run_loop(
        [disclaimer, _tool_call_block(), final]
    )

    # 3 LLM rounds: tool-free -> nudged -> tool call -> final
    assert llm_mock.await_count == 3
    # The second request echoes the disclaimer back and carries the nudge
    assert "--- ASSISTANT PARTIAL RESPONSE ---" in prompts[1]
    assert disclaimer in prompts[1]
    assert "--- MANDATORY TOOL USE REMINDER ---" in prompts[1]
    assert TOOL_NUDGE_TEXT in prompts[1]
    assert "TOOL CALL FORMAT" in prompts[1]
    # The third request carries the tool observation
    assert "--- TOOL RESULTS ---" in prompts[2]
    assert TOOL_OBSERVATION in prompts[2]
    # The tool was really executed
    assert exec_mock.await_count == 1
    executed_calls = exec_mock.call_args.args[0]
    assert executed_calls[0]["tool"] == "news_search"
    assert executed_calls[0]["query"] == "化肥板块 钾肥价格"
    # The loop completed normally and returned the final grounded answer
    assert final in result


# ---------- 2. non-compliance accepted after exactly one retry ----------

@pytest.mark.asyncio
async def test_nudge_not_complied_accepts_final_after_one_retry(caplog):
    """If the model still refuses after the nudge, the loop accepts the
    second answer after exactly 2 LLM rounds (nudge budget = 1, never a 3rd
    round) and logs the non-compliance."""
    refusal_1 = "免责声明：必须通过 finance_query 工具核实，本轮不调用。"
    refusal_2 = "仍然拒绝：无公司层面数据，全部待核实。"
    with caplog.at_level(logging.INFO):
        result, llm_mock, exec_mock, prompts = await _run_loop([refusal_1, refusal_2])

    # Exactly 2 LLM rounds — the nudge budget is 1, never a 3rd round
    assert llm_mock.await_count == 2
    assert exec_mock.await_count == 0
    assert "--- MANDATORY TOOL USE REMINDER ---" in prompts[1]
    assert TOOL_NUDGE_TEXT in prompts[1]
    # The post-nudge answer is accepted as final
    assert result == refusal_2
    assert "[ToolLoop] Model did not comply after nudge" in caplog.text


# ---------- 3. first-round tool call never nudges ----------

@pytest.mark.asyncio
async def test_first_round_tool_call_skips_nudge_entirely():
    """A model that complies immediately must never see the nudge in any
    request."""
    final = "最终回答：化肥板块景气向上。"
    result, llm_mock, exec_mock, prompts = await _run_loop(
        [_tool_call_block(), final]
    )

    assert llm_mock.await_count == 2
    assert exec_mock.await_count == 1
    assert final in result
    for p in prompts:
        assert "--- MANDATORY TOOL USE REMINDER ---" not in p
        assert TOOL_NUDGE_TEXT not in p


# ---------- 4. tools_enabled=False keeps legacy behavior ----------

@pytest.mark.asyncio
async def test_tools_disabled_never_nudges():
    """With tools disabled the loop keeps the legacy behavior: a tool-free
    first round is accepted immediately (no nudge, single LLM round)."""
    answer = "无工具调用即可作答（工具未启用场景）。"
    result, llm_mock, exec_mock, prompts = await _run_loop(
        [answer], tools_enabled=False
    )

    assert llm_mock.await_count == 1
    assert exec_mock.await_count == 0
    assert result == answer
    assert "--- MANDATORY TOOL USE REMINDER ---" not in prompts[0]


# ---------- 5. round-cap safety ----------

@pytest.mark.asyncio
async def test_nudge_respects_round_cap():
    """The nudge consumes an iteration inside range(max_tool_rounds + 1):
    with max_tool_rounds=1 the loop runs round 0 (nudged) + round 1 (the
    force-completion round — no second nudge) and stops at 2 LLM rounds."""
    result, llm_mock, exec_mock, prompts = await _run_loop(
        ["第一轮无调用。", "第二轮仍无调用。"], max_tool_rounds=1
    )
    assert llm_mock.await_count == 2
    assert result == "第二轮仍无调用。"


@pytest.mark.asyncio
async def test_zero_round_budget_never_nudges():
    """max_tool_rounds=0 -> the single round IS the force-completion round:
    no nudge, one LLM call, legacy behavior."""
    result, llm_mock, exec_mock, prompts = await _run_loop(
        ["唯一一轮直接作答。"], max_tool_rounds=0
    )
    assert llm_mock.await_count == 1
    assert result == "唯一一轮直接作答。"


# ---------- 6. unparseable tool block also nudges ----------

@pytest.mark.asyncio
async def test_unparseable_tool_tag_triggers_nudge():
    """A response that HAS the tool-block markers but fails to parse gets
    the same one-shot strict-format retry."""
    broken_block = (
        f"{TOOL_OPEN}\n格式坏掉的调用块（缺少 tool/reason/query 字段）\n{TOOL_CLOSE}"
    )
    final = "格式修正后的最终回答。"
    result, llm_mock, exec_mock, prompts = await _run_loop(
        [broken_block, _tool_call_block(), final]
    )

    assert llm_mock.await_count == 3
    assert "--- MANDATORY TOOL USE REMINDER ---" in prompts[1]
    assert TOOL_NUDGE_TEXT in prompts[1]
    assert exec_mock.await_count == 1
    assert final in result


# ---------- 7. caller wiring: sector scan ----------

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
        await sector_api._run_scan("scan_nudge001", model, "2026-09-01")
        # Drain the fire-and-forget progress-update tasks.
        await asyncio.sleep(0)
    return tool_mock, direct_mock


@pytest.mark.asyncio
async def test_sector_scan_passes_tools_enabled_for_text_protocol_models():
    """sector._run_scan must forward tools_enabled=True for MiniMax so the
    one-shot nudge can fire inside the text tool loop."""
    tool_mock, direct_mock = await _run_scan_with(MINIMAX_MODEL)
    assert tool_mock.await_count == 1
    assert direct_mock.await_count == 0
    assert tool_mock.call_args.kwargs.get("tools_enabled") is True


@pytest.mark.asyncio
async def test_sector_scan_deepseek_keeps_tools_enabled_false():
    """DeepSeek keeps the native-FC branch: tools_enabled stays False (the
    nudge must never fire there)."""
    tool_mock, direct_mock = await _run_scan_with(DEEPSEEK_MODEL)
    assert tool_mock.await_count == 1
    assert direct_mock.await_count == 0
    assert tool_mock.call_args.kwargs.get("tools_enabled") is False


# ---------- 8. caller wiring: expert discussion ----------

EXPERT_REPLY = (
    '{"core_thesis": "化肥板块景气度向上，钾肥价格处于上行周期。", '
    '"confidence": 0.85, "rating": "Buy", "risks": [], "key_metrics_extracted": []}'
)

SECTOR_SNAPSHOT = {
    "name": "化肥",
    "type": "sector",
    "timestamp": "2026-09-01T12:00:00",
}


async def _run_discussion_capturing(model):
    """Run the single-expert serenity_alpha flow offline, capturing the
    kwargs of every generate_with_tools call (same mock stack as
    test_tool_protocol_gating, with kwargs capture added)."""
    ds = DiscussionService()
    captured = []

    async def fake_generate_with_tools(prompt, *args, **kwargs):
        captured.append(kwargs)
        return EXPERT_REPLY

    async def fake_generate_content(prompt, *args, **kwargs):
        return EXPERT_REPLY

    patchers = [
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
    stack = ExitStack()
    for p in patchers:
        stack.enter_context(p)
    with stack:
        results = await ds.run_discussion(
            symbol="化肥",
            name="化肥",
            snapshot=dict(SECTOR_SNAPSHOT),
            level="serenity_alpha",
            market="sector",
            model=model,
        )
    return results, captured


@pytest.mark.asyncio
async def test_discussion_passes_tools_enabled_for_minimax():
    """discussion_service must forward tools_enabled=True for MiniMax (text
    protocol) so the nudge can fire."""
    results, captured = await _run_discussion_capturing(MINIMAX_MODEL)
    assert captured, "MiniMax must go through generate_with_tools"
    assert results and results[0].get("role") == "Serenity Alpha Analyst"
    assert all(c.get("tools_enabled") is True for c in captured)


@pytest.mark.asyncio
async def test_discussion_deepseek_keeps_tools_enabled_false():
    """DeepSeek keeps the native-FC transport: tools_enabled stays False
    (the nudge must never fire there)."""
    results, captured = await _run_discussion_capturing(DEEPSEEK_MODEL)
    assert captured, "DeepSeek keeps generate_with_tools (native FC inside)"
    assert all(c.get("tools_enabled") is False for c in captured)
