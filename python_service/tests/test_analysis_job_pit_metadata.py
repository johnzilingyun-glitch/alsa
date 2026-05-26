import json
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.db.repositories.job_repo import JobRepository
from python_service.app.db.sqlite import build_session_factory
from python_service.app.services.analysis_job_service import AnalysisJobService


class FakeSnapshotService:
    async def create_snapshot(self, market, symbol):
        history = [
            {
                "trade_date": f"2026-04-{day:02d}",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5 + day * 0.01,
                "volume": 1000 + day,
            }
            for day in range(1, 31)
        ]
        return {
            "snapshot_id": "snap_test123",
            "as_of_date": "2026-04-30T15:00:00Z",
            "data_cutoff": "2026-04-30T15:00:00Z",
            "market": market,
            "name": symbol,
            "history": history,
            "quote": {"price": 11.0, "currency": "USD", "changePercent": 0.5},
            "valuation": {},
            "financials": {"revenueGrowth": 0.1},
            "source_observations": [
                {
                    "dataset": "ohlc",
                    "storage_path": "/tmp/ohlc.parquet",
                    "effective_from": "2026-04-30T15:00:00Z",
                }
            ],
            "data_quality": {"score": 0.9, "blocking_errors": [], "warnings": []},
        }


@pytest.mark.asyncio
async def test_analysis_job_persists_snapshot_id(monkeypatch, tmp_path):
    session_factory = build_session_factory(str(tmp_path / "app.db"))
    repo = JobRepository(session_factory)
    service = AnalysisJobService(repo, FakeSnapshotService())
    monkeypatch.setattr(
        "python_service.app.services.discussion_service.discussion_service.run_discussion",
        AsyncMock(
            return_value=[
                {
                    "role": "Chief Strategist",
                    "content": "Investment Thesis\nHold while evidence matures.",
                    "timestamp": "2026-04-30T15:01:00Z",
                }
            ]
        ),
    )

    job_id = await service.start_job("MSFT", "US-Share")
    await service._run_job(job_id, "MSFT", "US-Share")

    job = repo.get_by_id(job_id)
    runs = repo.get_runs_by_job(job_id)
    payload = json.loads(job.result_payload)

    assert job.snapshot_id == "snap_test123"
    assert runs[0].snapshot_id == "snap_test123"
    assert payload["snapshot_id"] == "snap_test123"
    assert payload["snapshot"]["source_observations"][0]["dataset"] == "ohlc"
