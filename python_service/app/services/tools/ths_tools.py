"""THS (同花顺) AI Tools — 供讨论系统中的 agent 调用"""

from .registry import tool_registry
from ..data_providers.ths_provider import ths_provider

THS_KLINES_SCHEMA = {
    "name": "ths_klines",
    "description": "获取同花顺分钟K线/日K线数据。支持 1m/5m/15m/30m/60m/120m/day/week/month 周期。需要先通过 search_symbols 获取 THSCODE。",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "THSCODE, e.g. USHA600519 (A股), UHKG00700 (港股), UNQQAAPL (美股)"},
            "interval": {"type": "string", "enum": ["1m", "5m", "15m", "30m", "60m", "120m", "day", "week", "month"], "description": "K线周期"},
            "count": {"type": "integer", "description": "K线条数，默认78", "default": 78},
        },
        "required": ["code", "interval"],
    },
}

THS_DEPTH_SCHEMA = {
    "name": "ths_depth",
    "description": "获取同花顺五档盘口深度数据。显示买卖五档价格和挂单量。需要 THSCODE。",
    "parameters": {
        "type": "object",
        "properties": {
            "codes": {"type": "string", "description": "逗号分隔的 THSCODE 列表，如 USHA600519,USHA000858"},
        },
        "required": ["codes"],
    },
}

THS_BIG_ORDER_SCHEMA = {
    "name": "ths_big_order",
    "description": "获取同花顺大单流向数据。显示主力资金的买卖方向和金额。需要 THSCODE。",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "THSCODE, e.g. USHA600519"},
        },
        "required": ["code"],
    },
}

THS_QUOTE_SCHEMA = {
    "name": "ths_quote",
    "description": "获取同花顺实时行情数据。支持 A股/港股/美股。需要 THSCODE。",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "THSCODE, e.g. USHA600519 (A股), UHKG00700 (港股), UNQQAAPL (美股)"},
            "market": {"type": "string", "enum": ["cn", "hk", "us"], "description": "市场类型: cn=A股, hk=港股, us=美股"},
        },
        "required": ["code", "market"],
    },
}

THS_SECTOR_SCHEMA = {
    "name": "ths_sector",
    "description": "获取同花顺板块行情数据。可查询申万行业或概念板块的行情和成分股。先用 action=list 获取板块列表，再用 action=quote 查板块行情，action=constituents 查成分股。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list_industry", "list_concept", "quote", "constituents"], "description": "操作类型"},
            "code": {"type": "string", "description": "板块 THSCODE (quote/constituents 时必填)，如 URFI883404"},
        },
        "required": ["action"],
    },
}

THS_WENCAI_SCHEMA = {
    "name": "ths_wencai",
    "description": "同花顺问财自然语言查询。支持中文条件选股，如 '连续3日主力净流入，换手率大于5%'、'今日涨停，非ST' 等。返回符合条件的股票列表和相关数据。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "问财自然语言查询条件"},
        },
        "required": ["query"],
    },
}

THS_NEWS_SCHEMA = {
    "name": "ths_news",
    "description": "获取同花顺实时资讯/快讯。返回最新的财经新闻和市场动态。",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


@tool_registry.register(THS_KLINES_SCHEMA)
async def exec_ths_klines(args: dict) -> str:
    code = args.get("code", "")
    interval = args.get("interval", "5m")
    count = args.get("count", 78)
    if not code:
        return "<tool_observation>\nths_klines: code 参数必填。请先用 search_symbols 获取 THSCODE。\n</tool_observation>"
    try:
        result = await ths_provider.get_klines(code, interval, count)
        data = result.get("data", [])
        if not data:
            return f"<tool_observation>\nths_klines: {code} ({interval}) 无数据。\n</tool_observation>"
        lines = [f"<tool_observation>\nths_klines: {code} {interval} ({len(data)}条)"]
        for row in data[:10]:
            t = row.get("时间", "")
            o, h, l, c = row.get("开盘价", ""), row.get("最高价", ""), row.get("最低价", ""), row.get("收盘价", "")
            v = row.get("成交量", "")
            lines.append(f"  {t} O={o} H={h} L={l} C={c} V={v}")
        if len(data) > 10:
            lines.append(f"  ... 共{len(data)}条")
        lines.append("</tool_observation>")
        return "\n".join(lines)
    except Exception as e:
        return f"<tool_observation>\nths_klines 错误: {e}\n</tool_observation>"


@tool_registry.register(THS_DEPTH_SCHEMA)
async def exec_ths_depth(args: dict) -> str:
    codes = args.get("codes", "")
    if not codes:
        return "<tool_observation>\nths_depth: codes 参数必填。\n</tool_observation>"
    code_list = [c.strip() for c in codes.split(",")]
    try:
        result = await ths_provider.get_depth(code_list)
        data = result.get("data", [])
        if not data:
            return f"<tool_observation>\nths_depth: 无盘口数据。\n</tool_observation>"
        lines = [f"<tool_observation>\nths_depth: {len(data)}只股票盘口"]
        for row in data[:5]:
            name = row.get("名称", row.get("代码", ""))
            lines.append(f"  {name}: 买1={row.get('买1价','')}({row.get('买1量','')}) 卖1={row.get('卖1价','')}({row.get('卖1量','')})")
        lines.append("</tool_observation>")
        return "\n".join(lines)
    except Exception as e:
        return f"<tool_observation>\nths_depth 错误: {e}\n</tool_observation>"


@tool_registry.register(THS_BIG_ORDER_SCHEMA)
async def exec_ths_big_order(args: dict) -> str:
    code = args.get("code", "")
    if not code:
        return "<tool_observation>\nths_big_order: code 参数必填。\n</tool_observation>"
    try:
        result = await ths_provider.get_big_order_flow(code)
        data = result.get("data", [])
        if not data:
            return f"<tool_observation>\nths_big_order: {code} 无大单数据。\n</tool_observation>"
        lines = [f"<tool_observation>\nths_big_order: {code} ({len(data)}条大单)"]
        for row in data[:10]:
            t = row.get("时间", "")
            direction = row.get("成交方向", "")
            amount = row.get("总金额", "")
            lines.append(f"  {t} {direction} 金额={amount}")
        lines.append("</tool_observation>")
        return "\n".join(lines)
    except Exception as e:
        return f"<tool_observation>\nths_big_order 错误: {e}\n</tool_observation>"


@tool_registry.register(THS_QUOTE_SCHEMA)
async def exec_ths_quote(args: dict) -> str:
    code = args.get("code", "")
    market = args.get("market")
    if not code:
        return "<tool_observation>\nths_quote: code 参数必填。\n</tool_observation>"
    try:
        from ..data_providers.base import detect_market, MarketType
        m_type = detect_market(code) if not market else None
        if market == "hk" or (m_type == MarketType.HK_SHARE or code.upper().startswith("UHKG")):
            result = await ths_provider.get_market_data_hk(code)
        elif market == "us" or (m_type == MarketType.US_SHARE or code.upper().startswith(("UNQQ", "UNYS"))):
            result = await ths_provider.get_market_data_us(code)
        else:
            result = await ths_provider.get_market_data_cn(code)
        data = result.get("data", [])
        if not data:
            # thsdk guest account returns no HK/US data — fall back to Tencent
            # quotes (qt.gtimg.cn), which cover A-share/HK/US from any IP.
            from ..data_providers.a_stock_direct import fetch_tencent_quote
            tq = await fetch_tencent_quote([code])
            if tq:
                lines = [f"<tool_observation>\nths_quote: {code} (腾讯行情 fallback — thsdk 无此市场数据)"]
                for row in tq[:3]:
                    lines.append(f"  名称: {row.get('name','')} 代码: {row.get('code','')}")
                    lines.append(f"  最新价: {row.get('price','N/A')} 涨跌幅: {row.get('change_pct','N/A')}%")
                    lines.append(f"  涨跌额: {row.get('change_amt','N/A')} 昨收: {row.get('prev_close','N/A')}")
                    lines.append(f"  今开: {row.get('open','N/A')} 最高: {row.get('high','N/A')} 最低: {row.get('low','N/A')}")
                    lines.append(f"  成交量: {row.get('volume','N/A')} 成交额: {row.get('amount','N/A')}")
                    lines.append(f"  市盈率: {row.get('pe','N/A')} 市净率: {row.get('pb','N/A')} 总市值: {row.get('market_cap','N/A')}")
                    lines.append(f"  时间: {row.get('time','')}")
                lines.append("</tool_observation>")
                return "\n".join(lines)
            return f"<tool_observation>\nths_quote: {code} 无行情数据 (thsdk 与腾讯 fallback 均无数据)。\n</tool_observation>"
        lines = [f"<tool_observation>\nths_quote: {code}"]
        for row in data[:3]:
            for k, v in row.items():
                lines.append(f"  {k}: {v}")
        lines.append("</tool_observation>")
        return "\n".join(lines)
    except Exception as e:
        return f"<tool_observation>\nths_quote 错误: {e}\n</tool_observation>"


@tool_registry.register(THS_SECTOR_SCHEMA)
async def exec_ths_sector(args: dict) -> str:
    action = args.get("action", "list_industry")
    code = args.get("code", "")
    try:
        if action == "list_industry":
            result = await ths_provider.get_ths_industry()
            data = result.get("data", [])
            total = result.get("total", 0)
            lines = [f"<tool_observation>\nths_sector 申万行业 ({total}个)"]
            for item in data[:20]:
                lines.append(f"  {item.get('名称','')} ({item.get('代码','')})")
            if len(data) > 20:
                lines.append(f"  ... 共{total}个行业")
            lines.append("</tool_observation>")
            return "\n".join(lines)

        elif action == "list_concept":
            result = await ths_provider.get_ths_concept()
            data = result.get("data", [])
            total = result.get("total", 0)
            lines = [f"<tool_observation>\nths_sector 概念板块 ({total}个)"]
            for item in data[:20]:
                lines.append(f"  {item.get('名称','')} ({item.get('代码','')})")
            if len(data) > 20:
                lines.append(f"  ... 共{total}个概念")
            lines.append("</tool_observation>")
            return "\n".join(lines)

        elif action == "quote":
            if not code:
                return "<tool_observation>\nths_sector quote: code 参数必填。\n</tool_observation>"
            result = await ths_provider.get_market_data_block(code)
            data = result.get("data", [])
            if not data:
                return f"<tool_observation>\nths_sector: 板块 {code} 无行情数据。\n</tool_observation>"
            lines = [f"<tool_observation>\nths_sector 行情: {code}"]
            for row in data[:3]:
                for k, v in row.items():
                    lines.append(f"  {k}: {v}")
            lines.append("</tool_observation>")
            return "\n".join(lines)

        elif action == "constituents":
            if not code:
                return "<tool_observation>\nths_sector constituents: code 参数必填。\n</tool_observation>"
            result = await ths_provider.get_block_constituents(code)
            data = result.get("data", [])
            total = result.get("total", 0)
            lines = [f"<tool_observation>\nths_sector 成分股: {code} ({total}只)"]
            for item in data[:15]:
                lines.append(f"  {item.get('名称','')} ({item.get('代码','')})")
            if len(data) > 15:
                lines.append(f"  ... 共{total}只成分股")
            lines.append("</tool_observation>")
            return "\n".join(lines)

        return "<tool_observation>\nths_sector: 未知 action。\n</tool_observation>"
    except Exception as e:
        return f"<tool_observation>\nths_sector 错误: {e}\n</tool_observation>"


@tool_registry.register(THS_WENCAI_SCHEMA)
async def exec_ths_wencai(args: dict) -> str:
    query = args.get("query", "")
    if not query:
        return "<tool_observation>\nths_wencai: query 参数必填。\n</tool_observation>"
    try:
        result = await ths_provider.wencai_nlp(query)
        data = result.get("data", [])
        columns = result.get("columns", [])
        if not data:
            return f"<tool_observation>\nths_wencai: 查询 '{query}' 无结果。\n</tool_observation>"
        lines = [f"<tool_observation>\nths_wencai: '{query}' ({len(data)}条结果)"]
        lines.append(f"字段: {', '.join(columns[:8])}")
        for row in data[:10]:
            name = row.get("股票简称", row.get("名称", ""))
            code = row.get("股票代码", "")
            vals = ", ".join(f"{k}={v}" for k, v in list(row.items())[:4] if k not in ("股票简称", "名称", "股票代码"))
            lines.append(f"  {name}({code}) {vals}")
        if len(data) > 10:
            lines.append(f"  ... 共{len(data)}条")
        lines.append("</tool_observation>")
        return "\n".join(lines)
    except Exception as e:
        return f"<tool_observation>\nths_wencai 错误: {e}\n</tool_observation>"


@tool_registry.register(THS_NEWS_SCHEMA)
async def exec_ths_news(args: dict) -> str:
    try:
        result = await ths_provider.get_news()
        data = result.get("data", [])
        if not data:
            return "<tool_observation>\nths_news: 无资讯数据。\n</tool_observation>"
        lines = [f"<tool_observation>\nths_news: ({len(data)}条)"]
        import re
        for item in data[:10]:
            props = dict(re.findall(r'(\w+)=([^\n]+)', item.get('Properties', '')))
            title = item.get('Title', '')
            source = props.get('source', '')
            summ = props.get('summ', '')[:80]
            lines.append(f"  [{source}] {title}")
            if summ:
                lines.append(f"    {summ}")
        lines.append("</tool_observation>")
        return "\n".join(lines)
    except Exception as e:
        return f"<tool_observation>\nths_news 错误: {e}\n</tool_observation>"
