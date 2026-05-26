import os
import sys
from unittest.mock import AsyncMock

import pandas as pd
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.services.market_snapshot_service import MarketSnapshotService
from python_service.app.services import market_data_service as market_data_module


class FakeStore:
    def write_ohlc(self, dataset, market, symbol, rows, **metadata):
        return {
            "dataset": dataset,
            "market": market,
            "symbol": symbol,
            "vendor": metadata["vendor"],
            "observed_at": metadata["observed_at"],
            "ingested_at": metadata["ingested_at"],
            "published_at": metadata["published_at"],
            "effective_from": metadata["effective_from"],
            "content_hash": "hash_abc",
            "row_count": len(rows),
            "storage_path": "/tmp/lake/ohlc.parquet",
        }


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period="6mo"):
        dates = pd.date_range(end="2026-04-17", periods=60)
        return pd.DataFrame(
            {
                "Date": dates,
                "Open": [10.0] * len(dates),
                "High": [11.0] * len(dates),
                "Low": [9.5] * len(dates),
                "Close": [10.8] * len(dates),
                "Volume": [1000] * len(dates),
            }
        )


@pytest.mark.asyncio
async def test_snapshot_includes_pit_metadata_and_source_observations(monkeypatch):
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(
        market_data_module.market_data_service,
        "get_financial_summary",
        AsyncMock(return_value={"revenueGrowth": 0.12}),
    )
    monkeypatch.setattr(
        market_data_module.market_data_service,
        "get_quotes",
        AsyncMock(
            return_value=[
                {
                    "symbol": "MSFT",
                    "name": "Microsoft",
                    "price": 411.0,
                    "currency": "USD",
                    "changePercent": 1.2,
                }
            ]
        ),
    )

    service = MarketSnapshotService(FakeStore())
    snapshot = await service.create_snapshot("US-Share", "MSFT")

    assert snapshot["snapshot_id"].startswith("snap_")
    assert snapshot["as_of_date"].endswith("Z")
    assert snapshot["data_cutoff"] == snapshot["as_of_date"]
    assert snapshot["data_quality"]["score"] >= 0.85
    assert snapshot["source_observations"][0]["dataset"] == "ohlc"
    assert snapshot["source_observations"][0]["effective_from"] == snapshot["data_cutoff"]
