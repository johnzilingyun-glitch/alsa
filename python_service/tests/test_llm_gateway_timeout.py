import asyncio
import time

import pytest

from python_service.app.services.llm_gateway import LLMGateway


@pytest.mark.asyncio
async def test_blocking_llm_call_times_out_without_waiting_for_thread(monkeypatch):
    monkeypatch.setenv("LLM_STREAM_TIMEOUT_SECONDS", "0.05")
    gateway = LLMGateway(deepseek_api_key="sk-test")

    def blocked_call():
        time.sleep(2)
        return "late-result"

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="test-provider streaming call timed out"):
        await gateway._run_blocking_llm_call("test-provider", blocked_call)

    assert time.monotonic() - started < 0.5


@pytest.mark.asyncio
async def test_blocking_llm_call_returns_successful_result(monkeypatch):
    monkeypatch.setenv("LLM_STREAM_TIMEOUT_SECONDS", "1")
    gateway = LLMGateway(deepseek_api_key="sk-test")

    result = await gateway._run_blocking_llm_call("test-provider", lambda: "ok")

    assert result == "ok"
