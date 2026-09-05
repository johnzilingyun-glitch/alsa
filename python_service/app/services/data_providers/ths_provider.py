"""THS SDK Data Provider — 同花顺实时数据源"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from thsdk import THS

logger = logging.getLogger(__name__)


def format_ths_code(code: str, market_hint: str = "") -> str:
    """Format raw stock symbol into standard THSCODE with market prefix."""
    if not code:
        return code
    s = code.strip().upper()
    prefixes = ("USHA", "USZA", "USTM", "USHI", "USZI", "UHKG", "UNQQ", "UNYS", "URFI", "UFXB", "UCFS", "USHD")
    if any(s.startswith(p) for p in prefixes):
        return s

    clean = s.replace(".HK", "").replace(".SH", "").replace(".SS", "").replace(".SZ", "").replace(".US", "")

    if market_hint == "hk" or (clean.isdigit() and len(clean) <= 5):
        return f"UHKG{clean.zfill(5)}"
    elif market_hint == "us" or clean.isalpha():
        return f"UNQQ{clean}"
    elif clean.isdigit() and len(clean) == 6:
        if clean.startswith("6"):
            return f"USHA{clean}"
        elif clean.startswith(("0", "3")):
            return f"USZA{clean}"
        elif clean.startswith(("8", "4")):
            return f"USTM{clean}"
    return s


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
        formatted_code = format_ths_code(ths_code)
        with THS() as ths:
            kwargs = {"ths_code": formatted_code, "interval": interval, "count": count}
            if adjust:
                kwargs["adjust"] = adjust
            resp = await self._run_sync(ths.klines, **kwargs)
            return self._to_records(resp)

    async def get_intraday(self, ths_code: str) -> Dict:
        formatted_code = format_ths_code(ths_code)
        with THS() as ths:
            resp = await self._run_sync(ths.intraday_data, formatted_code)
            return self._to_records(resp)

    async def get_depth(self, ths_codes: Union[str, List[str]]) -> Dict:
        if isinstance(ths_codes, list):
            formatted_codes = [format_ths_code(c) for c in ths_codes]
        else:
            formatted_codes = format_ths_code(ths_codes)
        with THS() as ths:
            resp = await self._run_sync(ths.depth, formatted_codes)
            return self._to_records(resp)

    async def get_big_order_flow(self, ths_code: str) -> Dict:
        formatted_code = format_ths_code(ths_code)
        with THS() as ths:
            resp = await self._run_sync(ths.big_order_flow, formatted_code)
            return self._to_records(resp)

    async def get_call_auction_anomaly(self, market: str = "USHA") -> Dict:
        with THS() as ths:
            resp = await self._run_sync(ths.call_auction_anomaly, market)
            return self._to_records(resp)

    async def get_market_data_cn(self, ths_codes: Union[str, List[str]], query_key: str = "基础数据") -> Dict:
        if isinstance(ths_codes, list):
            formatted_codes = [format_ths_code(c, market_hint="cn") for c in ths_codes]
        else:
            formatted_codes = format_ths_code(ths_codes, market_hint="cn")

        # Auto-route HK/US codes if passed to get_market_data_cn
        if isinstance(formatted_codes, str):
            if formatted_codes.startswith("UHKG"):
                return await self.get_market_data_hk(formatted_codes, query_key)
            elif formatted_codes.startswith(("UNQQ", "UNYS")):
                return await self.get_market_data_us(formatted_codes, query_key)
        elif isinstance(formatted_codes, list) and len(formatted_codes) == 1:
            code_single = formatted_codes[0]
            if code_single.startswith("UHKG"):
                return await self.get_market_data_hk(code_single, query_key)
            elif code_single.startswith(("UNQQ", "UNYS")):
                return await self.get_market_data_us(code_single, query_key)

        with THS() as ths:
            resp = await self._run_sync(ths.market_data_cn, formatted_codes, query_key)
            return self._to_records(resp)

    async def get_market_data_hk(self, ths_code: str, query_key: str = "基础数据") -> Dict:
        formatted_code = format_ths_code(ths_code, market_hint="hk")
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_hk, formatted_code, query_key)
            return self._to_records(resp)

    async def get_market_data_us(self, ths_code: str, query_key: str = "基础数据") -> Dict:
        formatted_code = format_ths_code(ths_code, market_hint="us")
        with THS() as ths:
            resp = await self._run_sync(ths.market_data_us, formatted_code, query_key)
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

    async def get_market_data_block(self, link_code: Union[str, List[str]], query_key: str = "基础数据") -> Dict:
        # thsdk.market_data_block accepts str | list[str] (see query_configs.MARKET_DATA_BLOCK_QUERY_CONFIG
        # + market_queries.MarketQueryAPIMixin.market_data_block which declares block_code: Any).
        # The previous signature lied; batch lookups for all 90 SW industries in one shot
        # cuts thsdk connection overhead from 180 round-trips (~90s, guest mac pool exhausts)
        # to 2 round-trips (~1s).
        codes: Union[str, list] = link_code
        try:
            with THS() as ths:
                resp = await self._run_sync(ths.market_data_block, codes, query_key)
                return self._to_records(resp)
        except Exception as e:
            # 批量调用任何阶段（连接、序列化、解析）抛错都返回空 dict
            # 而不是让异常向上冒泡到 caller；caller 必须靠
            # `if not result.get('data'): ...` 处理空结果。这种"软失败"
            # 让 sector-scan 在 thsdk 不稳定时仍能降级到老路径（web_search），
            # 而不是整个扫描任务挂掉。
            logger.warning(f"ths_provider.get_market_data_block({len(codes) if isinstance(codes, list) else 1} codes, '{query_key}') failed: {e}")
            return {"data": [], "columns": [], "_error": str(e)}

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
