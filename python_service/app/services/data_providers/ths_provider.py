"""THS SDK Data Provider — 同花顺实时数据源"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from thsdk import THS

logger = logging.getLogger(__name__)


class THSProvider:
    """Wrapper around thsdk for async usage in FastAPI."""

    async def _run_sync(self, fn, *args, timeout: float = 15.0, **kwargs):
        """Run synchronous THS call in thread pool with timeout."""
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, lambda: fn(*args, **kwargs))
        return await asyncio.wait_for(future, timeout=timeout)

    @staticmethod
    def _to_records(resp) -> Dict:
        if resp and resp.df is not None and not resp.df.empty:
            return {"data": resp.df.to_dict(orient="records"), "columns": list(resp.df.columns)}
        return {"data": [], "columns": []}

    @staticmethod
    def _to_list(resp) -> Dict:
        if resp and resp.data:
            total = resp.extra.get("total_count", len(resp.data)) if resp.extra else len(resp.data)
            return {"data": resp.data, "total": total}
        return {"data": [], "total": 0}

    async def search_symbols(self, keyword: str) -> List[Dict]:
        with THS() as ths:
            resp = await self._run_sync(ths.search_symbols, keyword)
            return resp.data if resp else []

    async def get_klines(self, ths_code: str, interval: str = "5m", count: int = 78, adjust: str = "") -> Dict:
        with THS() as ths:
            kwargs = {"ths_code": ths_code, "interval": interval, "count": count}
            if adjust:
                kwargs["adjust"] = adjust
            resp = await self._run_sync(ths.klines, **kwargs)
            return self._to_records(resp)

    async def get_intraday(self, ths_code: str) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.intraday_data, ths_code)
            return self._to_records(resp)

    async def get_depth(self, ths_codes: Union[str, List[str]]) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.depth, ths_codes)
            return self._to_records(resp)

    async def get_big_order_flow(self, ths_code: str) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.big_order_flow, ths_code)
            return self._to_records(resp)

    async def get_call_auction_anomaly(self, market: str = "USHA") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.call_auction_anomaly, market)
            return self._to_records(resp)

    async def get_market_data_cn(self, ths_codes: Union[str, List[str]], query_key: str = "基础数据") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_cn, ths_codes, query_key)
            return self._to_records(resp)

    async def get_market_data_hk(self, ths_code: str, query_key: str = "基础数据") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_hk, ths_code, query_key)
            return self._to_records(resp)

    async def get_market_data_us(self, ths_code: str, query_key: str = "基础数据") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_us, ths_code, query_key)
            return self._to_records(resp)

    async def get_market_data_index(self, ths_codes: Union[str, List[str]]) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_index, ths_codes)
            return self._to_records(resp)

    async def get_ths_industry(self) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.ths_industry)
            return self._to_list(resp)

    async def get_ths_concept(self) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.ths_concept)
            return self._to_list(resp)

    async def get_block_constituents(self, link_code: str) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.block_constituents, link_code)
            return self._to_list(resp)

    async def get_market_data_block(self, link_code: str, query_key: str = "基础数据") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_block, link_code, query_key)
            return self._to_records(resp)

    async def wencai_nlp(self, query: str) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.wencai_nlp, query)
            return self._to_records(resp)

    async def get_news(self, **kwargs) -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.news, **kwargs)
            if resp and resp.data:
                return {"data": resp.data}
            return {"data": []}

    async def get_market_data_forex(self, ths_code: str, query_key: str = "基础数据") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_forex, ths_code, query_key)
            return self._to_records(resp)

    async def get_market_data_future(self, ths_code: str, query_key: str = "基础数据") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_future, ths_code, query_key)
            return self._to_records(resp)


ths_provider = THSProvider()
