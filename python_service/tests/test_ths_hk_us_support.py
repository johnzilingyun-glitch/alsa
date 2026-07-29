"""Unit and integration tests for THS HK and US stock support."""

import pytest
from unittest.mock import AsyncMock, patch
from app.services.data_providers.ths_provider import format_ths_code, THSProvider


def test_format_ths_code_hk_and_us():
    # HK share code formatting
    assert format_ths_code("00700") == "UHKG00700"
    assert format_ths_code("00700.HK") == "UHKG00700"
    assert format_ths_code("UHKG00700") == "UHKG00700"
    assert format_ths_code("9988") == "UHKG09988"

    # US share code formatting
    assert format_ths_code("AAPL") == "UNQQAAPL"
    assert format_ths_code("AAPL.US") == "UNQQAAPL"
    assert format_ths_code("UNQQAAPL") == "UNQQAAPL"
    assert format_ths_code("TSLA") == "UNQQTSLA"

    # A-share code formatting
    assert format_ths_code("600519") == "USHA600519"
    assert format_ths_code("600519.SH") == "USHA600519"
    assert format_ths_code("300033") == "USZA300033"
    assert format_ths_code("300033.SZ") == "USZA300033"


@pytest.mark.asyncio
async def test_get_market_data_cn_auto_routes_hk_and_us():
    provider = THSProvider()

    with patch.object(provider, "get_market_data_hk", AsyncMock(return_value={"data": [{"代码": "UHKG00700", "价格": 380.0}], "columns": ["代码", "价格"]})) as mock_hk, \
         patch.object(provider, "get_market_data_us", AsyncMock(return_value={"data": [{"代码": "UNQQAAPL", "价格": 220.0}], "columns": ["代码", "价格"]})) as mock_us:

        # Passing HK stock to get_market_data_cn should auto-route to get_market_data_hk
        res_hk = await provider.get_market_data_cn("UHKG00700")
        mock_hk.assert_called_once_with("UHKG00700", "基础数据")
        assert res_hk["data"][0]["价格"] == 380.0

        # Passing US stock to get_market_data_cn should auto-route to get_market_data_us
        res_us = await provider.get_market_data_cn("UNQQAAPL")
        mock_us.assert_called_once_with("UNQQAAPL", "基础数据")
        assert res_us["data"][0]["价格"] == 220.0
