import os
import secrets
import httpx
from typing import Dict
from datetime import datetime
from .registry import tool_registry

async def _iwencai_fallback_search(query: str, label: str) -> str:
    """Fallback to web search when Iwencai is unavailable/exhausted."""
    try:
        from ..search_service import search_service
        results = await search_service.search(query, max_results=5)
        if not results:
            return f"<tool_observation>\n{label} Fallback: No search results found for query '{query}'\n</tool_observation>"
        
        lines = ["<tool_observation>"]
        lines.append(f"{label} (Fallback Web Search): {query}")
        lines.append("")
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "N/A")[:100]
            content = r.get("content", "")[:250]
            url = r.get("url", "")
            lines.append(f"{i}. {title}")
            if content:
                lines.append(f"   {content}")
            if url:
                lines.append(f"   {url}")
        lines.append("</tool_observation>")
        return "\n".join(lines)
    except Exception as e:
        return f"<tool_observation>\n{label} Fallback Error: {str(e)}\n</tool_observation>"


_iwencai_disabled = False

async def exec_iwencai_query(query: str, skill_id: str, label: str) -> str:
    """Generic Iwencai query2data API call for structured data skills."""
    global _iwencai_disabled
    if _iwencai_disabled:
        return await _iwencai_fallback_search(query, label)

    MAX_ITEMS = 8
    MAX_FIELDS = 6
    MAX_VALUE_LEN = 50

    api_key = os.getenv("IWENCAI_API_KEY", "")
    if not api_key:
        _iwencai_disabled = True
        return await _iwencai_fallback_search(query, label)

    url = "https://openapi.iwencai.com/v1/query2data"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": "normal",
        "X-Claw-Skill-Id": skill_id,
        "X-Claw-Skill-Version": "2.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }
    payload = {
        "query": query,
        "page": "1",
        "limit": str(MAX_ITEMS),
        "is_cache": "1",
        "expand_index": "true",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        datas = data.get("datas", data.get("data", []))
        if not datas:
            text_resp = data.get("text_response", "")
            if text_resp:
                return f"<tool_observation>\n{label}: {query}\n{text_resp[:500]}\n</tool_observation>"
            # Attempt search fallback if data is empty
            return await _iwencai_fallback_search(query, label)

        lines = ["<tool_observation>"]
        lines.append(f"{label}: {query} ({len(datas)} items)")
        lines.append("")

        for item in datas[:MAX_ITEMS]:
            if isinstance(item, dict):
                parts = []
                for k, v in list(item.items())[:MAX_FIELDS]:
                    if v is not None and v != "":
                        v_str = str(v)[:MAX_VALUE_LEN]
                        parts.append(f"{k}:{v_str}")
                if parts:
                    lines.append(" | ".join(parts))
            else:
                lines.append(str(item)[:200])

        lines.append("</tool_observation>")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        # Fallback for quota limit (HTTP 401 / 403 / 429) or other errors
        _iwencai_disabled = True
        return await _iwencai_fallback_search(query, label)
    except Exception as e:
        _iwencai_disabled = True
        return await _iwencai_fallback_search(query, label)


MACRO_QUERY_SCHEMA = {
    "name": "macro_query",
    "description": "Query macroeconomic indicators (GDP, CPI, PPI, interest rates, exchange rates, social financing, M2, PMI, industrial output, consumption, investment, imports/exports). Source: 同花顺问财 (Iwencai). Supports natural language queries in Chinese. Returns structured data with indicator values, time periods, and units.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Macro data query in natural language. Supports Chinese. Examples: '中国最新GDP增速', 'CPI同比', '美联储利率', 'M2货币供应量', '社融规模'.",
            "required": True,
        }
    },
    "examples": [
        'tool: macro_query\nreason: Get latest GDP growth rate\nquery: 中国最新GDP同比增速',
        'tool: macro_query\nreason: Check CPI inflation trend\nquery: 中国CPI同比最近6个月',
        'tool: macro_query\nreason: Get M2 money supply data\nquery: M2货币供应量同比',
        'tool: macro_query\nreason: Check PMI manufacturing index\nquery: 中国制造业PMI最新',
        'tool: macro_query\nreason: Get social financing data\nquery: 社会融资规模增量',
    ],
}

@tool_registry.register(MACRO_QUERY_SCHEMA)
async def exec_macro_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-macro-query", "Macro data")


BUSINESS_QUERY_SCHEMA = {
    "name": "business_query",
    "description": "Query company business/operations data: revenue breakdown by product/region, major customers, suppliers, subsidiaries, equity investments, major contracts. Source: 同花顺问财 (Iwencai). Supports natural language queries in Chinese. Use for understanding a company's business structure and operations.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Business data query. Include company name or stock code. Examples: '贵州茅台主营业务构成', '002532主要客户', '宁德时代供应商', '比亚迪参控股公司'.",
            "required": True,
        }
    },
    "examples": [
        'tool: business_query\nreason: Understand revenue breakdown by product\nquery: 贵州茅台 主营业务构成 产品收入占比',
        'tool: business_query\nreason: Check major customers concentration\nquery: 002532 主要客户 销售占比',
        'tool: business_query\nreason: Check subsidiary investments\nquery: 宁德时代 参控股公司',
    ],
}

@tool_registry.register(BUSINESS_QUERY_SCHEMA)
async def exec_business_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-business-query", "Business data")


FINANCE_QUERY_SCHEMA = {
    "name": "finance_query",
    "description": "Query company financial indicators: revenue, net profit, ROE, debt ratio, cash flow, gross margin, net margin, EPS, valuation metrics (PE/PB/PS). Source: 同花顺问财 (Iwencai). Supports natural language queries. Use for cross-market financial screening and comparison.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Financial data query. Include company name/code and metrics. Examples: '贵州茅台 ROE 净利润 营收', '沪深300成分股 市盈率低于15', '002532 毛利率 净利率 近3年'.",
            "required": True,
        }
    },
    "examples": [
        'tool: finance_query\nreason: Get key financial metrics\nquery: 贵州茅台 营业收入 净利润 ROE 近4个季度',
        'tool: finance_query\nreason: Screen stocks by financial criteria\nquery: 创业板 ROE大于20% 营收增速大于30%',
        'tool: finance_query\nreason: Check debt and cash flow health\nquery: 002532 资产负债率 经营性现金流 近3年',
    ],
}

@tool_registry.register(FINANCE_QUERY_SCHEMA)
async def exec_finance_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-finance-query", "Financial data")


MANAGEMENT_QUERY_SCHEMA = {
    "name": "management_query",
    "description": "查询股本结构、股权结构、股东户数、前十大股东/流通股东、主要持有人、实控人等股权信息，支持自然语言问句输入，返回相关股东股本数据结果。当用户询问股本结构、股东户数、前十大股东、股权质押、实控人、主要持有人等股东股本数据查询问题时，必须使用此 hithink-management-query 技能。Source: 同花顺问财 (Iwencai).",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Shareholder/management query. Include company name or code. Examples: '贵州茅台 前十大股东', '002532 股东户数变化', '宁德时代 实控人'.",
            "required": True,
        }
    },
    "examples": [
        'tool: management_query\nreason: Check shareholder concentration\nquery: 002532 股东户数 户均持股 最近变化',
        'tool: management_query\nreason: Identify controlling shareholder\nquery: 贵州茅台 实控人 控股比例',
        'tool: management_query\nreason: Check institutional holdings\nquery: 宁德时代 前十大流通股东 机构持仓',
    ],
}

@tool_registry.register(MANAGEMENT_QUERY_SCHEMA)
async def exec_management_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-management-query", "Management/shareholder data")


COMMODITY_PRICE_QUERY_SCHEMA = {
    "name": "commodity_price_query",
    "description": "Search for commodity spot prices using Iwencai comprehensive search.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Commodity query. Example: 'R32 价格', '萤石 现货价'.",
            "required": True,
        }
    },
    "examples": [
        'tool: commodity_price_query\nreason: Check R32 refrigerant price\nquery: R32 现货价',
    ],
}

@tool_registry.register(COMMODITY_PRICE_QUERY_SCHEMA)
async def exec_commodity_price_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    MAX_ITEMS = 8
    MAX_TITLE = 80
    MAX_CONTENT = 250

    lines = ["<tool_observation>"]
    lines.append(f"Commodity Price Search: {query}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    try:
        from app.services.data_providers.iwencai_news import search_comprehensive
        raw = await search_comprehensive(query)
        if raw.get("status_code") == 0 and raw.get("data"):
            items = raw["data"]
            def get_date(x):
                d = x.get("publish_date", "")
                return d if d else "0000-00-00"
            items.sort(key=get_date, reverse=True)
            
            count = 0
            for item in items:
                if count >= MAX_ITEMS:
                    break
                title = item.get("title", "")[:MAX_TITLE]
                content = item.get("summary", "")[:MAX_CONTENT]
                date = item.get("publish_date", "")[:10]
                source = item.get("extra", {}).get("real_publish_source", "")[:20]
                
                lines.append(f"{count+1}. [{date}] {title} ({source})")
                if content:
                    lines.append(f"   {content}")
                count += 1
            if count == 0:
                raise Exception("Iwencai returned 0 items")
        else:
            raise Exception("Iwencai returned no data or error status")
    except Exception as e:
        from app.services.search_service import SearchService
        search_service = SearchService()
        try:
            results = await search_service.search(query, max_results=8)
            if results:
                for count, r in enumerate(results):
                    title = r.get("title", "")[:MAX_TITLE]
                    content = r.get("content", "")[:MAX_CONTENT]
                    source = r.get("source", "")[:20]
                    lines.append(f"{count+1}. {title} ({source})")
                    if content:
                        lines.append(f"   {content}")
            else:
                lines.append(f"No results found in fallback web search (SearXNG/DDG). Previous error: {str(e)}")
        except Exception as fe:
            lines.append(f"Error querying fallback web search: {str(fe)}. Previous error: {str(e)}")

    lines.append("</tool_observation>")
    return "\n".join(lines)


FUTURES_QUERY_SCHEMA = {
    "name": "futures_query",
    "description": "Query futures and commodity spot prices via Iwencai.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Futures query.",
            "required": True,
        }
    },
    "examples": [],
}

@tool_registry.register(FUTURES_QUERY_SCHEMA)
async def exec_futures_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-futures-query", "Futures/commodity data")


VALUATION_QUERY_SCHEMA = {
    "name": "valuation_query",
    "description": "Query stock valuation metrics via Iwencai.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Valuation query.",
            "required": True,
        }
    },
    "examples": [],
}

@tool_registry.register(VALUATION_QUERY_SCHEMA)
async def exec_valuation_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-valuation-query", "Valuation data")


INDUSTRY_QUERY_SCHEMA = {
    "name": "industry_query",
    "description": "Query industry/sector themes and concept stocks via Iwencai.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Industry query.",
            "required": True,
        }
    },
    "examples": [],
}

@tool_registry.register(INDUSTRY_QUERY_SCHEMA)
async def exec_industry_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-industry-query", "Industry data")


POLICY_QUERY_SCHEMA = {
    "name": "policy_query",
    "description": "Query national/local policy drivers and concept inclusions via Iwencai.",
    "parameters": {
        "query": {
            "type": "string",
            "description": "Policy query.",
            "required": True,
        }
    },
    "examples": [],
}

@tool_registry.register(POLICY_QUERY_SCHEMA)
async def exec_policy_query(tool_call: Dict[str, str]) -> str:
    query = tool_call.get("query", "")
    return await exec_iwencai_query(query, "hithink-policy-query", "Policy data")
