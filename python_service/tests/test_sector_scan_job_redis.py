"""Regression tests for the scan-job Redis update race and the sector
analysis progress-scheduling bug (both found via browser E2E: scan_44a26bfb /
scan_6f0075fa — UI stuck in scanning phase).

Bug 1 — scan completion race (app/api/sector.py):
    _run_scan used to fire FOUR concurrent fire-and-forget
    _update_scan_job_redis tasks at completion time (status / result /
    sectors / progress, one field each). Every task did an independent
    GET -> merge -> SET on the same ``scan_job:{job_id}`` key; interleaved
    GETs all observed the same stale snapshot, the last SET won, and fields
    written by the other tasks were silently dropped. get_scan_status then
    served a job dict missing status/result/sectors, and SectorScanner.tsx
    (which switches UI state on ``job.status === 'completed'``) polled
    forever without ever detecting the completed state.

    Fix: per-job asyncio.Lock serializes the read-modify-write cycle, and the
    completion / failure / cancel paths now perform ONE atomic write of the
    full state (awaited, not fire-and-forget).

Bug 2 — progress never awaited (app/services/sector_analysis_service.py):
    update_progress only scheduled its coroutine when the running loop was
    identical to the loop captured in __init__. In the Celery path
    (app/worker.py:run_sector_analysis_task) the service is constructed in a
    sync task context (no running loop -> _main_loop is None) and the job
    then runs on a fresh asyncio.run() loop, so BOTH branches were skipped:
    the coroutine object was dropped ("coroutine was never awaited") and
    job_progress:{job_id} was never written — get_progress() always
    returned {}.

    Fix: schedule on the CURRENT loop whenever one is running; only fall back
    to run_coroutine_threadsafe when called from a thread without a loop; if
    no loop is usable at all, close the coroutine explicitly (no warning).
"""
import asyncio
import json
import sys
import threading

import pytest

from python_service.app.api import sector as sector_api

# ---------------------------------------------------------------------------
# Dual-module guard. conftest aliases ``app.*`` to ``python_service.app.*``
# only for modules already loaded at conftest import time. sector_analysis_service
# imports ``from app.db.redis_client import RedisManager`` at module level; if
# that import loads ``app.db.redis_client`` as a SECOND module object, the
# import system also rebinds the ``redis_client`` attribute on the (aliased)
# ``python_service.app.db`` package to the second object. After that,
# monkeypatch's attribute-chain resolution ("python_service.app.db.redis_client.*")
# and business code's sys.modules-based relative imports see DIFFERENT modules,
# silently breaking unrelated redis-mocking tests (test_analysis_job_progress.py).
# Pre-aliasing here (after sector.py's relative import loaded the canonical
# module, before sector_analysis_service's absolute import runs) keeps a
# single module object under both names.
# ---------------------------------------------------------------------------
import python_service.app.db.redis_client as _redis_client_mod
sys.modules.setdefault("app.db.redis_client", _redis_client_mod)

from python_service.app.services import sector_analysis_service as sas_module
from python_service.app.services.sector_analysis_service import SectorAnalysisService
from python_service.app.db.redis_client import RedisManager

SCAN_TTL = 86400


class FakeRedis:
    """In-memory async redis stub (same pattern as test_analysis_job_progress).

    The ``await asyncio.sleep(0)`` calls inside get/set force a yield to the
    event loop so that concurrent read-modify-write coroutines actually
    interleave — reproducing the network-I/O interleaving of a real redis
    client. Without them a mock coroutine runs to completion without ever
    yielding and the lost-update race cannot be reproduced deterministically.
    """

    def __init__(self):
        self.values = {}
        self.expirations = {}

    async def get(self, key):
        await asyncio.sleep(0)
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        await asyncio.sleep(0)
        self.values[key] = value
        self.expirations[key] = ex
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    """Route every RedisManager.get_client() call to a fresh FakeRedis.

    Dual-import hazard: tests/conftest.py aliases ``app.*`` to
    ``python_service.app.*`` only for modules already loaded at conftest
    import time. ``app.db.redis_client`` can still be imported later under
    BOTH paths, producing two distinct module objects — and therefore two
    distinct RedisManager class objects. Patch the class object each
    consumer module actually references (deduplicated) so the stub reaches
    both sector.py and sector_analysis_service.py.
    """
    fake = FakeRedis()

    async def fake_get_client():
        return fake

    classes = {
        id(RedisManager): RedisManager,
        id(sector_api.RedisManager): sector_api.RedisManager,
        id(sas_module.RedisManager): sas_module.RedisManager,
    }
    for cls in classes.values():
        monkeypatch.setattr(cls, "get_client", staticmethod(fake_get_client))
    return fake


async def _seed_running_job(job_id: str):
    """Seed the same baseline document start_scan writes before _run_scan."""
    await sector_api._update_scan_job_redis(
        job_id,
        status="running",
        progress="正在扫描A股市场板块轮动...",
        result=None,
        sectors=[],
        error=None,
        created_at="2026-08-31T00:00:00",
    )


# ---------- Bug 1: scan completion race ----------

@pytest.mark.asyncio
async def test_concurrent_scan_job_updates_keep_all_fields(fake_redis):
    """Whatever the interleaving, the final Redis document must contain the
    UNION of all fields. Simulates the OLD completion code shape (four
    CONCURRENT single-field updates racing on the same key) — before the
    per-job lock this deterministically dropped status/result/sectors."""
    job_id = "scan_race0001"
    await _seed_running_job(job_id)

    # Four concurrent updates, one field each — gathered as tasks so their
    # GET/SET pairs interleave at FakeRedis's yield points (this is exactly
    # what the old `asyncio.create_task(...) x4` completion path did).
    await asyncio.gather(
        sector_api._update_scan_job_redis(job_id, status="completed"),
        sector_api._update_scan_job_redis(job_id, result="full scan text"),
        sector_api._update_scan_job_redis(job_id, sectors=["化肥", "光伏"]),
        sector_api._update_scan_job_redis(job_id, progress="扫描完成"),
    )

    job = json.loads(fake_redis.values[f"scan_job:{job_id}"])
    # Fields SectorScanner.tsx reads on every poll:
    assert job["status"] == "completed"        # completion detection
    assert job["result"] == "full scan text"   # setScanResult(job.result)
    assert job["sectors"] == ["化肥", "光伏"]  # setSectors(job.sectors)
    assert job["progress"] == "扫描完成"        # progress line
    # Baseline fields must survive every merge (poll's failed branch reads error).
    assert job["error"] is None
    assert job["created_at"] == "2026-08-31T00:00:00"


@pytest.mark.asyncio
async def test_completed_job_payload_readable_by_status_poller(fake_redis):
    """After the (merged) completion write, the helper behind
    GET /sector/run/{job_id} must surface every field the frontend needs."""
    job_id = "scan_poll0002"
    await _seed_running_job(job_id)

    # New completion path: ONE atomic write with the full completed state.
    await sector_api._update_scan_job_redis(
        job_id, status="completed", result="scan text", sectors=["化肥"], progress="扫描完成"
    )

    job = await sector_api._get_scan_job_redis(job_id)
    assert job["status"] == "completed"
    assert job["result"] == "scan text"
    assert job["sectors"] == ["化肥"]
    assert job["progress"] == "扫描完成"
    assert job["error"] is None


@pytest.mark.asyncio
async def test_scan_job_ttl_semantics_not_regressed(fake_redis):
    """Every write must keep refreshing the 24h TTL (ex=86400), including the
    merged completion write."""
    job_id = "scan_ttl0003"
    key = f"scan_job:{job_id}"

    await _seed_running_job(job_id)
    assert fake_redis.expirations[key] == SCAN_TTL

    await sector_api._update_scan_job_redis(
        job_id, status="completed", result="scan text", sectors=[], progress="扫描完成"
    )
    assert fake_redis.expirations[key] == SCAN_TTL


@pytest.mark.asyncio
async def test_failed_job_write_is_atomic(fake_redis):
    """The failure path (empty result / exception) writes status AND error in
    a single update — the frontend failed branch reads job.status and
    job.error together."""
    job_id = "scan_fail0004"
    await _seed_running_job(job_id)

    await sector_api._update_scan_job_redis(job_id, status="failed", error="扫描返回空结果")

    job = json.loads(fake_redis.values[f"scan_job:{job_id}"])
    assert job["status"] == "failed"
    assert job["error"] == "扫描返回空结果"


@pytest.mark.asyncio
async def test_progress_and_content_count_share_one_write(fake_redis):
    """The stream callback (_on_chunk) now carries progress AND content_count
    in a single write, so neither field can be lost to a two-task race."""
    job_id = "scan_chunk005"
    await _seed_running_job(job_id)

    # Mirrors the merged _on_chunk payload.
    await sector_api._update_scan_job_redis(
        job_id, progress="AI 正在生成分析内容... (1,234 chars)", content_count=1234
    )

    job = json.loads(fake_redis.values[f"scan_job:{job_id}"])
    assert job["progress"] == "AI 正在生成分析内容... (1,234 chars)"
    assert job["content_count"] == 1234
    assert job["status"] == "running"  # untouched field preserved


# ---------- Bug 2: progress coroutine never awaited ----------

def test_update_progress_celery_worker_scenario(fake_redis):
    """Celery worker regression (the actual E2E failure mode):
    run_sector_analysis_task constructs the service in a SYNC context (no
    running loop -> _main_loop=None) and then runs the job via asyncio.run()
    on a fresh loop. update_progress called inside that job must still write
    job_progress:{job_id} to Redis — the old code dropped the coroutine
    ("coroutine was never awaited") and progress stayed {} forever."""

    # Constructed OUTSIDE any event loop — exactly like the Celery task body.
    service = SectorAnalysisService(job_repo=object())

    async def job_body():
        # Simulates _run_sector_job running on the fresh asyncio.run() loop:
        # get_running_loop() succeeds but is NOT the (None) _main_loop.
        service.update_progress(
            "job_celery001", "discussion", 30,
            message="正在搜索和整理板块市场数据...",
        )
        # Let the fire-and-forget task run to completion on this loop.
        for _ in range(100):
            if not service._progress_tasks:
                break
            await asyncio.sleep(0.01)

    asyncio.run(job_body())

    data = json.loads(fake_redis.values["job_progress:job_celery001"])
    assert data["stage"] == "discussion"
    assert data["progress"] == 30
    assert data["message"] == "正在搜索和整理板块市场数据..."


@pytest.mark.asyncio
async def test_update_progress_same_loop_schedules_task(fake_redis):
    """FastAPI path: service and job share the running loop — the coroutine
    is scheduled with create_task and reaches Redis."""
    service = SectorAnalysisService(job_repo=object())

    service.update_progress("job_sameloop01", "sector_snapshot", 10)
    for _ in range(100):
        if "job_progress:job_sameloop01" in fake_redis.values:
            break
        await asyncio.sleep(0.01)

    data = json.loads(fake_redis.values["job_progress:job_sameloop01"])
    assert data["stage"] == "sector_snapshot"
    assert data["progress"] == 10


def test_update_progress_from_worker_thread_hands_off_to_main_loop(fake_redis):
    """Worker-thread path: called from a thread with no running loop, the
    update must be handed off (run_coroutine_threadsafe) to the loop captured
    at construction time — the on_chunk-in-thread-pool scenario."""

    async def main():
        service = SectorAnalysisService(job_repo=object())  # captures this loop

        def thread_cb():
            service.update_progress(
                "job_thread001", "discussion", 55, message="from-thread"
            )

        t = threading.Thread(target=thread_cb)
        t.start()
        # Serve the loop until the thread-side handoff lands in redis.
        for _ in range(200):  # ~2s ceiling
            t.join(timeout=0.01)
            if "job_progress:job_thread001" in fake_redis.values:
                break
            await asyncio.sleep(0.01)
        assert "job_progress:job_thread001" in fake_redis.values

    asyncio.run(main())
    data = json.loads(fake_redis.values["job_progress:job_thread001"])
    assert data["progress"] == 55
    assert data["message"] == "from-thread"


def test_update_progress_no_loop_closes_coroutine_without_warning(fake_redis, recwarn):
    """Degenerate path: no loop at construction AND no loop at call time.
    The coroutine must be closed explicitly — no 'never awaited' warning,
    and a warning breadcrumb is logged instead."""
    service = SectorAnalysisService(job_repo=object())  # no loop here

    service.update_progress("job_noloop001", "finalizing", 90)

    # Nothing written (nothing could be), and no RuntimeWarning leak.
    assert "job_progress:job_noloop001" not in fake_redis.values
    never_awaited = [
        w for w in recwarn.list
        if "never awaited" in str(w.message)
    ]
    assert not never_awaited
