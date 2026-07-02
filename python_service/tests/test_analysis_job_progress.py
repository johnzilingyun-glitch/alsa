import asyncio
import json

import pytest

from python_service.app.services.analysis_job_service import (
    AnalysisJobService,
    PROGRESS_REDIS_PREFIX,
)


class DummyJobRepository:
    pass


class DummySnapshotService:
    pass


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.expirations[key] = ex

    async def get(self, key):
        return self.values.get(key)


@pytest.mark.asyncio
async def test_update_job_progress_persists_shared_progress(monkeypatch):
    fake_redis = FakeRedis()

    async def fake_get_redis():
        return fake_redis

    monkeypatch.setattr("python_service.app.db.redis_client.get_redis", fake_get_redis)
    service = AnalysisJobService(DummyJobRepository(), DummySnapshotService())

    service.update_job_progress("job-1", "snapshot", 10, message="\u6b63\u5728\u91c7\u96c6\u884c\u60c5")
    await asyncio.sleep(0)

    key = f"{PROGRESS_REDIS_PREFIX}:job-1"
    assert fake_redis.expirations[key] == 86400
    assert json.loads(fake_redis.values[key]) == {
        "stage": "snapshot",
        "percent": 10,
        "round": None,
        "total_rounds": None,
        "message": "\u6b63\u5728\u91c7\u96c6\u884c\u60c5",
        "count": None,
        "error_type": None,
    }


@pytest.mark.asyncio
async def test_get_job_progress_reads_shared_progress_when_memory_empty(monkeypatch):
    key = f"{PROGRESS_REDIS_PREFIX}:job-2"
    fake_redis = FakeRedis()
    fake_redis.values[key] = json.dumps(
        {
            "stage": "discussion",
            "percent": 65,
            "message": "\u4e13\u5bb6\u8ba8\u8bba\u4e2d",
        },
        ensure_ascii=False,
    ).encode("utf-8")

    async def fake_get_redis():
        return fake_redis

    monkeypatch.setattr("python_service.app.db.redis_client.get_redis", fake_get_redis)
    service = AnalysisJobService(DummyJobRepository(), DummySnapshotService())

    progress = await service.get_job_progress("job-2")

    assert progress == {
        "stage": "discussion",
        "percent": 65,
        "message": "\u4e13\u5bb6\u8ba8\u8bba\u4e2d",
    }
