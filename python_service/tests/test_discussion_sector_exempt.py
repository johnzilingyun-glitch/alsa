"""
Regression tests for the sector/keyword exemption in run_discussion's
"unidentifiable stock" early-abort check.

Background (bug, 2026-08-29): commit f0a5573 added an early-abort check to
run_discussion to catch unidentifiable stocks (name == symbol, no price, no
OHLC coverage). Sector/keyword flows (Serenity Alpha "Analyst 专属研判")
legitimately pass the keyword as BOTH symbol and name and their lightweight
snapshots never carry price / data_quality — so every sector job was
misclassified as an unidentifiable stock and aborted before any expert ran
(e.g. job sector_e64fadb7, keyword "化肥" → "🚫 股票代码 化肥.us 无法识别").

The fix exempts sector flows (snapshot.type == "sector" or level in
{"sector", "serenity_alpha"}) from the check, and passes market="sector"
from _run_sector_job to avoid the misleading ".us" default.
"""
import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.discussion_service import DiscussionService, discussion_service
from app.services.sector_analysis_service import SectorAnalysisService

# High-confidence JSON payload: keeps the smart verification pipeline from
# triggering self-reflection / extra LLM calls in the mocked flow.
EXPERT_REPLY = json.dumps(
    {
        "core_thesis": "化肥板块景气度向上，钾肥价格处于上行周期。",
        "confidence": 0.85,
        "rating": "Buy",
        "risks": [],
        "key_metrics_extracted": [],
    },
    ensure_ascii=False,
)

SECTOR_SNAPSHOT = {
    "name": "化肥",
    "type": "sector",
    "timestamp": "2026-08-29T12:00:00",
}


def _sector_mock_patches(llm_prompts):
    """Return the list of patchers applied for every sector-flow test.

    Mocks the LLM gateway (capturing every prompt sent), the agent
    orchestrator's tool-calling loop (the path Serenity Alpha Analyst
    actually takes), the background batch search, macro/commodity data
    services, agent memory recall, and the self-reflection agent so the
    discussion runs fully offline.
    """
    async def fake_generate_content(prompt, *args, **kwargs):
        llm_prompts.append(prompt)
        return EXPERT_REPLY

    async def fake_generate_with_tools(prompt, *args, **kwargs):
        llm_prompts.append(prompt)
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
            "app.services.self_reflection_agent.self_reflection_agent.reflect",
            AsyncMock(return_value={}),
        ),
    ]


def _sector_mock_stack(llm_prompts):
    """Context manager applying all shared sector-flow patches at once."""
    stack = ExitStack()
    for p in _sector_mock_patches(llm_prompts):
        stack.enter_context(p)
    return stack


@pytest.mark.asyncio
async def test_sector_keyword_flow_not_early_aborted():
    """Case A (the bug): keyword snapshot + serenity_alpha level must reach the
    experts instead of returning the 'unidentifiable stock' System message."""
    ds = DiscussionService()
    llm_prompts = []

    with _sector_mock_stack(llm_prompts):
        results = await ds.run_discussion(
            symbol="化肥",
            name="化肥",
            snapshot=dict(SECTOR_SNAPSHOT),
            level="serenity_alpha",
            market="sector",
        )

    # 1. No early-abort "unidentifiable" message anywhere.
    for msg in results:
        assert "无法识别" not in (msg.get("content") or "")

    # 2. A real expert (non-System) message was produced.
    assert len(results) == 1  # SERENITY_ALPHA_TOPOLOGY = single round/expert
    assert results[0]["role"] == "Serenity Alpha Analyst"
    assert results[0]["role"] != "System"

    # 3. The LLM was actually called and the keyword reached the prompt.
    assert len(llm_prompts) >= 1
    assert any("化肥" in p for p in llm_prompts)


@pytest.mark.asyncio
async def test_sector_flow_exempt_even_with_default_market():
    """SerenityGraph path calls run_discussion WITHOUT an explicit market
    (default 'us'). The exemption must not depend on the market argument."""
    ds = DiscussionService()
    llm_prompts = []

    with _sector_mock_stack(llm_prompts):
        results = await ds.run_discussion(
            symbol="化肥",
            name="化肥",
            snapshot=dict(SECTOR_SNAPSHOT),
            level="serenity_alpha",
            # market intentionally omitted → default "us"
        )

    assert len(results) == 1
    assert results[0]["role"] == "Serenity Alpha Analyst"
    assert "无法识别" not in (results[0].get("content") or "")


@pytest.mark.asyncio
async def test_level_sector_also_exempt():
    """level='sector' (plain sector endpoint) must be exempt too, even when the
    snapshot lacks an explicit type marker."""
    ds = DiscussionService()
    llm_prompts = []

    with _sector_mock_stack(llm_prompts):
        results = await ds.run_discussion(
            symbol="PCB",
            name="PCB",
            snapshot={"name": "PCB", "timestamp": "2026-08-01T00:00:00"},
            level="sector",
            market="sector",
        )

    # SECTOR_TOPOLOGY has 5 rounds; even if later experts are mocked the flow
    # must NOT be cut short to a single System abort message.
    assert all(m.get("role") != "System" for m in results)
    assert len(llm_prompts) >= 1


@pytest.mark.asyncio
async def test_stock_flow_still_early_aborts():
    """Case B (guard the 2026-08-03 fix): a stock-style snapshot
    (name == symbol, no price, no data_quality, non-sector level) must still
    trigger the early abort."""
    ds = DiscussionService()
    llm_prompts = []

    with _sector_mock_stack(llm_prompts):
        results = await ds.run_discussion(
            symbol="03986",
            name="03986",
            snapshot={"name": "03986"},  # name == symbol, no price, no data_quality
            level="standard",
            market="HK-Share",
        )

    assert len(results) == 1
    assert results[0]["role"] == "System"
    assert "无法识别" in results[0]["content"]
    assert "03986.HK-Share" in results[0]["content"]
    # The LLM was never reached — the abort happened before any expert call.
    assert len(llm_prompts) == 0


@pytest.mark.asyncio
async def test_stock_flow_quick_level_still_aborts():
    """Same guard for level='quick' (another stock-level)."""
    ds = DiscussionService()

    results = await ds.run_discussion(
        symbol="ZZZZ",
        name="ZZZZ",
        snapshot={"name": "ZZZZ"},
        level="quick",
    )

    assert len(results) == 1
    assert results[0]["role"] == "System"
    assert "无法识别" in results[0]["content"]


@pytest.mark.asyncio
async def test_run_sector_job_passes_sector_market():
    """Case C: _run_sector_job must pass market='sector' to run_discussion
    instead of relying on the default 'us' (misleading '化肥.us' wording)."""
    service = SectorAnalysisService(job_repo=MagicMock())

    discussion_stub = [
        {
            "role": "Serenity Alpha Analyst",
            "content": "化肥板块分析结论。" + "x" * 120,
            "model": "test-model",
            "timestamp": "2026-08-29T12:00:00",
        }
    ]

    with patch.object(service, "update_progress"), \
         patch.object(service, "_build_sector_snapshot",
                      AsyncMock(return_value=dict(SECTOR_SNAPSHOT))), \
         patch.object(service, "_fetch_sector_stocks",
                      AsyncMock(return_value=[])), \
         patch.object(service, "_enrich_result_with_prices",
                      AsyncMock(return_value={})), \
         patch(
             "app.services.discussion_service.discussion_service.run_discussion",
             AsyncMock(return_value=discussion_stub),
         ) as mock_run, \
         patch("app.services.critic_agent.critic_agent.critique",
               AsyncMock(return_value=None)):
        await service._run_sector_job(
            job_id="sector_test0001",
            sector_name="化肥",
            model="test-model",
            level="serenity_alpha",
        )

    assert mock_run.await_count == 1
    kwargs = mock_run.call_args.kwargs
    pos_args = mock_run.call_args.args
    assert kwargs.get("market") == "sector"
    assert kwargs.get("market") != "us"
    assert kwargs.get("level") == "serenity_alpha"
    # symbol/name are positional args, still the keyword, by design.
    assert pos_args[0] == "化肥"  # symbol
    assert pos_args[1] == "化肥"  # name
