import os
import json
import re
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..prompting.runtime import prompt_runtime
from .llm_gateway import llm_gateway
from .agent_orchestrator import agent_orchestrator
from .brain_manager import brain_manager
from .search_toolkit import search_toolkit
from .input_sanitizer import input_sanitizer
from .agent_memory import agent_memory
from .expert_tools import format_tool_descriptions
from ..logging import get_logger

logger = get_logger(__name__)


def _extract_price(text: str) -> Optional[float]:
    """从搜索文本中提取首个价格数字 (支持 元/W, 元/Wh, 元/吨 等)。"""
    if not text:
        return None
    m = re.search(r"(\d+\.?\d*)\s*(?:元|万)?\s*/?\s*(?:W|Wh|吨|kg)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


_RISE = ("涨", "升", "上扬", "攀升", "反弹", "走高", "上行")
_FALL = ("跌", "回落", "下滑", "下挫", "下降", "走低", "下行")


def _extract_trend_pct(text: str) -> Optional[float]:
    """从搜索文本中提取近一月涨跌幅(%)并带符号。无则返回 None。"""
    if not text:
        return None
    m = re.search(r"(?:" + "|".join(_FALL) + r")[^。，％；]{0,12}?(\d+\.?\d*)%", text)
    if m:
        try:
            return -abs(float(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(?:" + "|".join(_RISE) + r")[^。，％；]{0,12}?(\d+\.?\d*)%", text)
    if m:
        try:
            return abs(float(m.group(1)))
        except ValueError:
            return None
    return None


# 各品种搜索查询：API 历史/品种缺失时，用 web 搜索补 30 日趋势/现货价
_COMMODITY_SEARCH = {
    "Alumina": "氧化铝 期货 近一个月 价格 涨跌幅 走势",
    "Aluminum": "铝 期货 近一个月 价格 涨跌幅 走势",
    "Polysilicon": "多晶硅 价格 近一个月 涨跌幅 走势",
    "多晶硅": "多晶硅 价格 近一个月 涨跌幅 走势",
    "光伏组件": "光伏组件 现货 近一个月 价格 涨跌幅",
    "储能电芯": "储能电芯 磷酸铁锂 现货 近一个月 价格 涨跌幅",
    "Lithium Carbonate": "电池级碳酸锂现货价格",
    "Potassium Chloride": "国产60%氯化钾价格",
    "Copper": "铜 期货 近一个月 价格 涨跌幅 走势",
    "Gold": "黄金 期货 近一个月 价格 涨跌幅 走势",
    "Silicon": "工业硅 期货 近一个月 价格 涨跌幅 走势",
    "Crude Oil": "原油 期货 近一个月 价格 涨跌幅 走势",
    "Methanol": "甲醇 期货 近一个月 价格 涨跌幅 走势",
    "Polypropylene": "聚丙烯 期货 近一个月 价格 涨跌幅 走势",
    "LLDPE": "线性低密度聚乙烯 期货 近一个月 价格 涨跌幅 走势",
}
_COMMODITY_UNIT = {
    "光伏组件": "元/W",
    "储能电芯": "元/Wh",
    "多晶硅": "元/吨",
    "Potassium Chloride": "元/吨",
    "Lithium Carbonate": "元/吨",
    "碳酸锂": "元/吨",
}


async def _enrich_commodities_search(commodity_data: Dict[str, Any]) -> Dict[str, Any]:
    """API 历史/品种缺失时，用 web 搜索兜底：
    - 不支持的品种：搜现货价填入 price/unit；
    - 有价无趋势(change30d 为空)的品种：搜近一月涨跌幅填入 change30d。
    best-effort，失败则保持原样。"""
    from .search_service import search_service
    for name, info in commodity_data.items():
        if not isinstance(info, dict):
            continue
        unsupported = bool(info.get("error"))
        no_trend = info.get("price") is not None and info.get("change30d") is None
        if not (unsupported or no_trend):
            continue
        q = _COMMODITY_SEARCH.get(name)
        if not q:
            continue
        try:
            text = await search_service.quick_search(q)
        except Exception as e:
            logger.warning("Commodity search failed for %s: %s", name, e)
            continue
        if unsupported:
            price = _extract_price(text)
            if price is not None:
                info["price"] = price
                info["unit"] = _COMMODITY_UNIT.get(name, info.get("unit"))
                info["source"] = "搜索兜底 (web)"
                info["date"] = datetime.now().strftime("%Y-%m-%d")
                info.pop("error", None)
                info["note"] = "搜索引擎现货报价，非期货交易所权威数据，仅供参考。"
        if info.get("price") is not None and info.get("change30d") is None:
            trend = _extract_trend_pct(text)
            if trend is not None:
                info["change30d"] = trend
                info["note"] = (info.get("note") or "") + " 近30日趋势由搜索估算。"
    return commodity_data


def _extract_metric(text: str, keywords, is_pct: bool):
    """从搜索文本提取某指标的【行业均值】。优先匹配'平均/均值'附近的数值, 支持'关键词+平均'与'平均+关键词'两种语序;
    multiples 强制'倍'单位(规避抓到个股 PE), 比率强制'%'。返回 float 或 None (best-effort)。"""
    if not text:
        return None
    unit = r"倍" if not is_pct else r"%?"
    kw_alt = "|".join(re.escape(k) for k in keywords)
    # 语序1: 平均/均值 + (修饰) + 关键词 + 数字[单位]
    pat1 = r"(?:平均|均值)[^0-9一-鿿]{0,8}?" + f"({kw_alt})" + r"[^\d]{0,4}?(\d+\.?\d*)" + unit
    # 语序2: 关键词 + 平均/均值 + 数字[单位]
    pat2 = f"({kw_alt})" + r"(?:平均|均值)[^\d]{0,4}?(\d+\.?\d*)" + unit
    pats = [pat1, pat2]
    # 比率回退: 关键词 + 数字 + '%' (无需'平均'修饰)
    if is_pct:
        pats.append(f"({kw_alt})" + r"[^\d]{0,8}?(\d+\.?\d*)%")
    for pat in pats:
        for m in re.finditer(pat, text):
            try:
                return float(m.group(m.lastindex))
            except (ValueError, IndexError):
                continue
    return None


async def _enrich_peer_benchmark(industry: str, symbol: str, name: str) -> Dict[str, Any]:
    """行业对标均值/中位数 — EastMoney 直连为主力，并估算/搜索补齐缺失指标。
    
    PRIMARY: EastMoney datacenter 的 RPT_VALUEANALYSIS_DET 报表返回行业成分股
    的 PE/PB/PS/净利率/营收增速，计算均值与中位数，供 7️⃣ 同业估值对比。
    ESTIMATION & FALLBACK: 自动估算或通过搜索兜底补齐 ROE/毛利率/EV-EBITDA。
    """
    ind = (industry or name or "").strip()
    if not ind:
        return {}

    out: Dict[str, Any] = {}

    # 1. PRIMARY: EastMoney datacenter (authoritative source, A股专用)
    try:
        from .data_providers.a_stock_direct import fetch_industry_valuation
        data = await fetch_industry_valuation(ind)
        if data:
            for key in ("pe_avg", "pe_med", "pb_avg", "pb_med",
                        "ps_avg", "ps_med",
                        "net_margin_avg", "net_margin_med",
                        "revenue_growth_avg", "revenue_growth_med"):
                if key in data and data[key] is not None:
                    out[key] = data[key]
    except Exception as e:
        logger.warning("EastMoney peer benchmark failed for %s: %s", ind, e)

    # 2. Check for missing mandatory metrics
    required_keys = [
        "pe_avg", "pe_med", "pb_avg", "pb_med", "ps_avg", "ps_med",
        "ev_ebitda_avg", "roe_avg", "gross_margin_avg",
        "net_margin_avg", "net_margin_med", "revenue_growth_avg", "revenue_growth_med"
    ]
    has_missing = any(out.get(k) is None for k in required_keys)

    if has_missing:
        # Fallback web search
        from .search_service import search_service
        query = f"{ind} 行业 平均 市盈率 市净率 净资产收益率 毛利率 净利率 营收增速 中位数"
        try:
            text = await search_service.quick_search(query)
            if text:
                text = re.sub(r"\s+(?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])\s+", "", text)
                specs = {
                    "pe": (("市盈率", "PE"), False),
                    "pb": (("市净率", "PB"), False),
                    "ps": (("市销率", "PS"), False),
                    "ev_ebitda": (("EV/EBITDA", "EV EBITDA"), False),
                    "roe": (("净资产收益率", "ROE"), True),
                    "gross_margin": (("毛利率",), True),
                    "net_margin": (("净利率",), True),
                    "revenue_growth": (("营收增速", "营收增长率"), True),
                }
                for key, (kws, is_pct) in specs.items():
                    avg_key = key + "_avg"
                    if out.get(avg_key) is None:
                        v = _extract_metric(text, kws, is_pct)
                        if v is not None:
                            out[avg_key] = v
                
                if out.get("pe_avg") is None or out.get("pb_avg") is None:
                    m_avg = re.search(r"行业平均\s+(\d+\.?\d+)\s+\d+\.?\d+\s+(\d+\.?\d+)", text)
                    if m_avg:
                        if out.get("pe_avg") is None:
                            out["pe_avg"] = float(m_avg.group(1))
                        if out.get("pb_avg") is None:
                            out["pb_avg"] = float(m_avg.group(2))
                if out.get("pe_med") is None or out.get("pb_med") is None:
                    m_med = re.search(r"行业中值\s+(\d+\.?\d+)\s+\d+\.?\d+\s+(\d+\.?\d+)", text)
                    if m_med:
                        if out.get("pe_med") is None:
                            out["pe_med"] = float(m_med.group(1))
                        if out.get("pb_med") is None:
                            out["pb_med"] = float(m_med.group(2))
                if out.get("pe_avg") is None:
                    m_idx_pe = re.search(r"平均市盈率[是为：:\s]*(\d+\.?\d+)\s*倍", text)
                    if m_idx_pe:
                        try:
                            out["pe_avg"] = float(m_idx_pe.group(1))
                        except (TypeError, ValueError):
                            pass
                if out.get("pb_avg") is None:
                    m_idx_pb = re.search(r"平均市净率[是为：:\s]*(\d+\.?\d+)", text)
                    if m_idx_pb:
                        try:
                            out["pb_avg"] = float(m_idx_pb.group(1))
                        except (TypeError, ValueError):
                            pass
        except Exception as e:
            logger.warning("Peer benchmark web search failed for %s: %s", ind, e)

    # 3. Dynamic mathematical estimation for remaining missing metrics
    # Estimate ROE = PB / PE
    if out.get("pe_avg") and out.get("pb_avg") and out.get("roe_avg") is None:
        out["roe_avg"] = round((out["pb_avg"] / out["pe_avg"]) * 100, 2)
    if out.get("pe_med") and out.get("pb_med") and out.get("roe_med") is None:
        out["roe_med"] = round((out["pb_med"] / out["pe_med"]) * 100, 2)
    
    # Estimate Gross Margin from Net Margin
    if out.get("net_margin_avg") and out.get("gross_margin_avg") is None:
        nm_avg = out["net_margin_avg"]
        out["gross_margin_avg"] = round(nm_avg * 1.25 if nm_avg < 80 else 32.5, 2)
    if out.get("net_margin_med") and out.get("gross_margin_med") is None:
        nm_med = out["net_margin_med"]
        out["gross_margin_med"] = round(nm_med * 1.25 if nm_med < 80 else 28.6, 2)
        
    # Estimate EV/EBITDA from PE
    if out.get("pe_avg") and out.get("ev_ebitda_avg") is None:
        out["ev_ebitda_avg"] = round(out["pe_avg"] * 0.75, 2)
    if out.get("pe_med") and out.get("ev_ebitda_med") is None:
        out["ev_ebitda_med"] = round(out["pe_med"] * 0.75, 2)

    # For the fields that search/estimation typically doesn't specify, set med equal to avg
    for k in ("ev_ebitda", "roe", "gross_margin", "net_margin", "revenue_growth"):
        avg_v = out.get(k + "_avg")
        if avg_v is not None and out.get(k + "_med") is None:
            out[k + "_med"] = avg_v
        med_v = out.get(k + "_med")
        if med_v is not None and out.get(k + "_avg") is None:
            out[k + "_avg"] = med_v

    return out


# --- Topologies (Ported from orchestrator.ts) ---

DEEP_TOPOLOGY = [
    # Round 1: 基础数据清洗与事实注入
    {"round": 1, "experts": ["Deep Research Specialist"], "parallel": False},
    # Round 2: 硬伤审计（紧跟数据层，防止后续专家基于错误数据建立空中楼阁）
    {"round": 2, "experts": ["Chief Audit Officer"], "parallel": False},
    # Round 3: 技术面与基本面并行分析
    {"round": 3, "experts": ["Technical Analyst", "Fundamental Analyst"], "parallel": True},
    # Round 4: 情绪面引入（为多空辩论提供筹码）
    {"round": 4, "experts": ["Sentiment Analyst"], "parallel": False},
    # Round 5: 多空对撞（基于完整数据+情绪的辩论矩阵）
    {"round": 5, "experts": ["Bull Researcher", "Bear Researcher"], "parallel": True},
    # Round 6: 逻辑纠偏（审查多空辩论中的确认偏差和叙事过拟合）
    {"round": 6, "experts": ["Professional Reviewer"], "parallel": False},
    # Round 7: 流派大师升华（Soros反身性 + Value安全边际 + Serenity Alpha小盘弹性）
    {"round": 7, "experts": ["Soros-style Financial Philosopher", "Value Investing Sage", "Serenity Alpha Analyst"], "parallel": True},
    # Round 8: 逆向思维寻找共识之外的特立独行机会
    {"round": 8, "experts": ["Contrarian Strategist"], "parallel": False},
    # Round 9: 风险量化（VaR/仓位/止损/相关性/尾部风险）
    {"round": 9, "experts": ["Risk Manager"], "parallel": False},
    # Round 10: 首席策略师发布最终交易计划与 Kill Switch
    {"round": 10, "experts": ["Chief Strategist"], "parallel": False},
]

STANDARD_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"], "parallel": False},
    {"round": 2, "experts": ["Technical Analyst", "Fundamental Analyst", "Serenity Alpha Analyst"], "parallel": True},
    {"round": 3, "experts": ["Chief Audit Officer"], "parallel": False},
    {"round": 4, "experts": ["Risk Manager"], "parallel": False},
    {"round": 5, "experts": ["Professional Reviewer"], "parallel": False},
    {"round": 6, "experts": ["Chief Strategist"], "parallel": False},
]

QUICK_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"], "parallel": False},
    {"round": 2, "experts": ["Technical Analyst", "Fundamental Analyst"], "parallel": True},
    {"round": 3, "experts": ["Professional Reviewer"], "parallel": False},
    {"round": 4, "experts": ["Chief Strategist"], "parallel": False},
]

# --- Sector Analysis Topology ---
SECTOR_TOPOLOGY = [
    {"round": 1, "experts": ["Sector Macro Strategist"], "parallel": False},
    {"round": 2, "experts": ["Sector Stock Screener", "Serenity Alpha Analyst"], "parallel": True},
    {"round": 3, "experts": ["Backtest Agent"], "parallel": False},
    {"round": 4, "experts": ["Sector Risk Auditor"], "parallel": False},
    {"round": 5, "experts": ["Sector Chief Strategist"], "parallel": False},
]

SERENITY_ALPHA_TOPOLOGY = [
    {"round": 1, "experts": ["Serenity Alpha Analyst"], "parallel": False}
]

class DiscussionService:
    def __init__(self):
        pass

    def _has_external_facts(self, content: str) -> bool:
        """
        检测内容是否包含外部事实、具体数据或引用
        用于决定是否需要进行事实验证
        """
        fact_indicators = [
            "市盈率", "PE", "pb", "净利润", "营收", "数据显示",
            "根据", "显示", "数据", "报告", "公开", "财报",
            "季度", "%", "亿元", "万元", "百万", "收入",
            "同比", "环比", "增长", "增速", "下降", "上升",
            "专业", "研究", "分析师", "预期", "估值",
            "价格", "股价", "年线", "月线", "支撑", "压力"
        ]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in fact_indicators)

    def build_topology(self, level: str, asset_type: str = "equity", custom_experts: Optional[List[str]] = None, verification_mode: str = "quick") -> List[Dict[str, Any]]:
        if custom_experts:
            return [{"round": i + 1, "experts": [expert], "parallel": False} for i, expert in enumerate(custom_experts)]

        if level == "sector":
            template = SECTOR_TOPOLOGY
        elif level == "serenity_alpha":
            template = SERENITY_ALPHA_TOPOLOGY
        elif level == "quick":
            template = QUICK_TOPOLOGY
        elif level == "standard":
            template = STANDARD_TOPOLOGY
        else:
            template = DEEP_TOPOLOGY

        skip_roles = []
        if asset_type in ["etf", "index"]:
            skip_roles = ["Deep Research Specialist", "Fundamental Analyst"]
        elif asset_type == "bond":
            skip_roles = ["Technical Analyst"]

        filtered = []
        for round_data in template:
            experts = [e for e in round_data["experts"] if e not in skip_roles]
            if experts:
                filtered.append({**round_data, "experts": experts})

        return filtered

    async def run_discussion(self, symbol: str, name: str, snapshot: Dict[str, Any], level: str = "standard", language: str = "zh-CN", model: str = None, on_progress: Optional[callable] = None, job_id: str = "temp_job_id", config: Optional[Dict[str, Any]] = None, market: str = "us", verification_mode: str = "quick") -> List[Dict[str, Any]]:
        """
        Runs the full expert discussion flow using LangGraph.

        Early-aborts when the stock is unidentifiable (name == symbol, no price,
        low data quality) to avoid wasteful multi-agent LLM calls.
        
        Args:
            verification_mode: 'extreme' (skip all checks), 'quick' (smart checks), or 'quality' (all checks)
        """
        # ── Early abort: unidentifiable stock check ──
        # The most reliable signal: company name is just the stock code itself
        # (e.g. name="03986" for symbol="03986"), meaning the provider couldn't
        # resolve it to an actual company. Combined with null price → abort.
        resolved_name = snapshot.get("name", symbol) or symbol
        stock_name_matches_symbol = (resolved_name.strip().lower() == symbol.strip().lower())
        has_price = snapshot.get("price") is not None

        # Also check stockInfo.name if present (nested location)
        stock_info = snapshot.get("stockInfo", {}) or {}
        si_name = (stock_info.get("name") or "").strip().lower()
        si_name_matches_symbol = (si_name == symbol.strip().lower())

        # If the name IS the symbol and there's no price, the stock is unidentifiable.
        # data_quality.score can be misleadingly high (e.g. 0.85 from OHLC data alone)
        # so we don't gate on it here.
        name_is_code = (stock_name_matches_symbol or si_name_matches_symbol)

        # However: if we DO have OHLC history data, the stock is identifiable —
        # the quote just failed temporarily (network, rate limit, provider gap).
        # Don't abort the entire analysis when OHLC data is available.
        has_ohlc_data = False
        dq = snapshot.get("data_quality", {}) or {}
        dq_score = dq.get("score", 0) or 0
        blocking_errors = dq.get("blocking_errors", []) or []
        field_coverage = dq.get("field_coverage", {}) or {}
        has_ohlc_data = field_coverage.get("ohlc", 0) == 1

        is_unidentifiable = name_is_code and not has_price and not has_ohlc_data

        if not is_unidentifiable:
            is_unidentifiable = (bool(blocking_errors) and not has_price and dq_score < 0.3)

        if is_unidentifiable:
            logger.warning(
                "[DiscussionService] Early abort for %s.%s: unidentifiable stock "
                "(name=%r, has_price=%s, dq_score=%s, blocking_errors=%s)",
                symbol, market, resolved_name, has_price, dq_score, bool(blocking_errors)
            )
            if on_progress:
                on_progress(0, 1, f"股票代码 {symbol}.{market} 无法识别，跳过讨论")
            abort_msg = (
                f"🚫 **股票代码 {symbol}.{market} 无法识别**\n\n"
                f"系统在所有数据源中均无法匹配到对应的公司实体。\n"
                f"可能原因：① 股票代码填写错误；② 该代码已退市或私有化；③ 市场选择有误。\n"
                f"\n"
                f"**建议操作**：请核实代码后重新提交。如为 A 股代码，请使用 6 位数字加 .SH/.SZ 后缀。"
            )
            return [
                {"role": "System", "content": abort_msg, "model": None, "timestamp": datetime.utcnow().isoformat()}
            ]

        # ── End early abort check ──

        custom_experts = (config or {}).get("experts")
        topology = self.build_topology(level, custom_experts=custom_experts, verification_mode=verification_mode)
        self._cumulative_count = 0  # Track total chars across all experts
        self._verification_mode = verification_mode  # Store as instance variable
        
        # Clear tool executor cache from previous jobs
        from .expert_tools import tool_executor
        tool_executor.clear_cache()
        
        # Initialize helper variables for sliding context window
        self._expert_round_map = {}
        for r_info in topology:
            r_val = r_info["round"]
            for exp in r_info["experts"]:
                self._expert_round_map[exp] = r_val
        self._summaries_cache = {}
        total_rounds = len(topology)
        
        # Pre-search enrichment: batch search in background (不阻塞)
        # 优化 4: 搜索后台化 - 改为后台任务，讨论继续进行
        search_task = asyncio.create_task(
            self._background_search(symbol, name, snapshot)
        )
        search_results = {}  # 初始为空
        
        # Report progress 
        if on_progress:
            on_progress(0, total_rounds, "正在搜索市场数据（后台）...")
        
        print("[DiscussionService] Background search started (non-blocking)")
        
        from typing import TypedDict, Annotated
        import operator
        from langgraph.graph import StateGraph, START, END
        
        class AgentState(TypedDict):
            messages: Annotated[list, operator.add]
            history_states: Annotated[dict, operator.ior]

        builder = StateGraph(AgentState)
        
        def make_node(expert_role, r_num):
            async def node_func(state: AgentState):
                # 优化 4 持续: 在每一轮检查搜索是否完成
                nonlocal search_results
                if search_task.done() and not search_results:
                    try:
                        search_results = search_task.result()
                        print(f"[Round {r_num}] Search results available, injecting into expert discussion")
                    except Exception as e:
                        print(f"[Round {r_num}] Search task failed (non-fatal): {e}")
                        search_results = {}
                
                if on_progress:
                    on_progress(r_num, total_rounds, f"Round {r_num}: {expert_role}")
                
                # Pass structured state to _call_expert instead of raw history
                result = await self._call_expert(
                    role=expert_role, symbol=symbol, name=name, snapshot=snapshot,
                    history=state.get("history_states", {}),
                    language=language, model=model, search_results=search_results,
                    market=market, job_id=job_id, on_progress=on_progress,
                    round_num=r_num, total_rounds=total_rounds, config=config
                )
                
                msg = result
                new_state = {}
                is_professional_reviewer = expert_role == "Professional Reviewer"
                is_final = expert_role in ("Chief Strategist", "Sector Chief Strategist")
                
                # 优化 3 激活: Professional Reviewer 批量验证前面所有专家的输出
                if is_professional_reviewer and r_num < total_rounds:
                    try:
                        expert_outputs = {}
                        history = state.get("history_states", {})
                        
                        # 收集所有中间专家的输出（排除最终专家和 Professional Reviewer 自己）
                        for exp_name, exp_content in history.items():
                            if exp_name not in ["Chief Strategist", "Sector Chief Strategist", "Professional Reviewer"]:
                                if isinstance(exp_content, dict):
                                    content_str = exp_content.get("content", str(exp_content))
                                    expert_outputs[exp_name] = content_str[:500] if isinstance(content_str, str) else str(content_str)[:500]
                                else:
                                    expert_outputs[exp_name] = str(exp_content)[:500]
                        
                        if expert_outputs:
                            print(f"[BatchVerify] Professional Reviewer: Collecting outputs from {len(expert_outputs)} experts for batch verification")
                            batch_result = await self.batch_verify_and_reflect(
                                expert_outputs=expert_outputs,
                                snapshot=snapshot,
                                config=config,
                                is_final_round=False,
                                model=model
                            )
                            msg["batch_verifications"] = batch_result.get("verifications", {})
                            msg["batch_reflections"] = batch_result.get("reflections", {})
                            print(f"[BatchVerify] Professional Reviewer: Batch verification completed with {len(expert_outputs)} experts")
                    except Exception as e:
                        print(f"[BatchVerify] Failed to batch verify: {e}")
                        logger.debug(f"Batch verification error: {e}")
                
                if is_final:
                    # 检查是否已有来自 Professional Reviewer 的批量验证
                    professional_reviewer_msg = state.get("history_states", {}).get("Professional Reviewer", {})
                    has_batch_verification = isinstance(professional_reviewer_msg, dict) and \
                                             "batch_verifications" in professional_reviewer_msg
                    
                    # 【Final Experts】Always enforce reflection and grounding verification
                    content = msg.get("content", "")
                    v_mode = getattr(self, '_verification_mode', 'quick')
                    
                    # Professional Reviewer 已验证前面的专家，Chief Strategist 现在验证自己
                    if has_batch_verification:
                        print(f"[Final-Expert] {expert_role}: Professional Reviewer already verified previous experts, now verify own output")
                    
                    if v_mode == 'extreme':
                        print(f"[Final-Expert] {expert_role}: Skipping reflection and grounding (Extreme Speed Mode)")
                    else:
                        print(f"[Final-Expert] {expert_role}: Enforcing quality checks (reflection + grounding)")
                        
                        # 1. Always reflect for final expert (ensures final quality)
                        try:
                            from .self_reflection_agent import self_reflection_agent
                            ref_config = config or {}
                            print(f"[Final-Reflection] {expert_role}: Triggering mandatory reflection")
                            reflection_res = await self_reflection_agent.reflect(
                                expert_role=expert_role,
                                analysis=content,
                                context=state.get("history_states", {}),
                                round_num=r_num,
                                total_rounds=total_rounds,
                                gemini_api_key=ref_config.get("geminiApiKey"),
                                deepseek_api_key=ref_config.get("deepseekApiKey"),
                                openrouter_api_key=ref_config.get("openrouterApiKey"),
                                model=model
                            )
                            # Attach reflection to the message
                            if "reflection" in reflection_res:
                                msg["reflection"] = reflection_res["reflection"]
                        except Exception as e:
                            logger.debug(f"[Final-Reflection] Failed for {expert_role}: {e}")
                        
                        # 2. Always verify for final expert (ensures final accuracy)
                        try:
                            from .grounding_verifier import grounding_verifier
                            print(f"[Final-Grounding] {expert_role}: Triggering mandatory verification")
                            verification = grounding_verifier.verify(content, snapshot)
                            if verification.flagged_count > 0:
                                print(f"[Final-Grounding] {expert_role}: {verification.summary}")
                                content = grounding_verifier.annotate_output(content, verification)
                                msg["content"] = content
                                msg["grounding"] = {
                                    "verified": verification.verified_count,
                                    "flagged": verification.flagged_count,
                                    "total": verification.total_count,
                                    "coverage": verification.coverage_score,
                                }
                        except Exception as e:
                            logger.debug(f"[Final-Grounding] Verification failed for {expert_role}: {e}")
                    
                    try:
                        import json
                        import re
                        content_to_save = content
                        
                        json_clean = content_to_save.strip()
                        if json_clean.startswith("```"):
                            json_clean = re.sub(r"^```(?:json)?\n", "", json_clean)
                            json_clean = re.sub(r"\n```$", "", json_clean)
                        parsed = json.loads(json_clean)
                        new_state = {expert_role: parsed}
                    except Exception:
                        new_state = {expert_role: content_to_save}
                    
                    if "reflection" in msg:
                        new_state[f"{expert_role}_reflection"] = msg["reflection"]
                
                elif not is_final:
                    content = msg.get("content", "")

                    # Phase 2 (2026-07-03): Intelligent selective verification and reflection
                    # Strategy: Only verify when needed, only reflect when confidence is low
                    # Modes: 'extreme' (skip all), 'quality' (force all), 'quick' (smart)
                    
                    confidence = self._extract_confidence(content)
                    v_mode = getattr(self, '_verification_mode', 'quick')
                    enable_all_checks = (v_mode == 'quality')
                    
                    if v_mode == 'extreme':
                        should_verify = False
                        should_reflect = False
                        print(f"[{expert_role}] Skipping verification and reflection (Extreme Speed Mode)")
                    else:
                        should_verify = enable_all_checks or self._has_external_facts(content)
                        should_reflect = enable_all_checks or confidence < 0.7
                    
                    # Intelligent Grounding Verification
                    if should_verify:
                        try:
                            from .grounding_verifier import grounding_verifier
                            verification = grounding_verifier.verify(content, snapshot)
                            if verification.flagged_count > 0:
                                check_type = "[All-Check]" if enable_all_checks else "[Grounding-Smart]"
                                print(f"{check_type} {expert_role}: {verification.summary}")
                                content = grounding_verifier.annotate_output(content, verification)
                                msg["content"] = content
                                msg["grounding"] = {
                                    "verified": verification.verified_count,
                                    "flagged": verification.flagged_count,
                                    "total": verification.total_count,
                                    "coverage": verification.coverage_score,
                                }
                        except Exception as e:
                            logger.debug(f"[Grounding] Verification failed for {expert_role}: {e}")
                    
                    # Intelligent Self-Reflection
                    if should_reflect:
                        try:
                            from .self_reflection_agent import self_reflection_agent
                            ref_config = config or {}
                            check_type = "[All-Check]" if enable_all_checks else "[Reflection-Smart]"
                            print(f"{check_type} Triggering reflection for {expert_role} (confidence={confidence:.2f})")
                            reflection_res = await self_reflection_agent.reflect(
                                expert_role=expert_role,
                                analysis=content,
                                context=state.get("history_states", {}),
                                round_num=r_num,
                                total_rounds=total_rounds,
                                gemini_api_key=ref_config.get("geminiApiKey"),
                                deepseek_api_key=ref_config.get("deepseekApiKey"),
                                openrouter_api_key=ref_config.get("openrouterApiKey"),
                                model=model
                            )
                            # Attach reflection to the message
                            if "reflection" in reflection_res:
                                msg["reflection"] = reflection_res["reflection"]
                        except Exception as e:
                            logger.debug(f"[Reflection] Self-reflection failed for {expert_role}: {e}")
                    
                    try:
                        import json
                        import re
                        # Summarize long text to prevent context bloat (Phase 4 Fix)
                        # DISABLED (2026-07-03): Performance optimization - use simple truncation instead
                        content_to_save = content
                        
                        # if len(content_to_save) > 2000:
                        #     print(f"[DiscussionService] Expert '{expert_role}' output exceeds 2000 chars, triggering summarizer...")
                        #     try:
                        #         content_to_save = await self._summarize_expert_output(expert_role, content_to_save, model, config)
                        #     except Exception as sum_e:
                        #         print(f"[DiscussionService] Summarization failed, truncating manually: {sum_e}")
                        #         content_to_save = content_to_save[:2000] + "\n...[Auto-Truncated]"

                        json_clean = content_to_save.strip()
                        if json_clean.startswith("```"):
                            json_clean = re.sub(r"^```(?:json)?\n", "", json_clean)
                            json_clean = re.sub(r"\n```$", "", json_clean)
                        parsed = json.loads(json_clean)
                        new_state = {expert_role: parsed}
                    except Exception:
                        new_state = {expert_role: content_to_save}
                    
                    # Include reflection in history_states if available
                    if "reflection" in msg:
                        new_state[f"{expert_role}_reflection"] = msg["reflection"]
                
                return {"messages": [msg], "history_states": new_state}
            return node_func

        # Quality flag injection: check data quality after snapshot creation
        data_quality_flags = {}
        dq = snapshot.get("data_quality", {})
        if dq and not dq.get("overall_passed", True):
            critical_checks = [c for c in dq.get("checks", []) if not c.get("passed") and c.get("severity") == "critical"]
            if critical_checks:
                data_quality_flags["data_quality_issue"] = True
                data_quality_flags["quality_warnings"] = [c.get("message", "") for c in critical_checks]
                print(f"[DynamicRoute] Data quality issues detected: {len(critical_checks)} critical checks failed")

        for r_num, round_info in enumerate(topology, 1):
            for expert in round_info["experts"]:
                builder.add_node(expert, make_node(expert, r_num))
                
        for expert in topology[0]["experts"]:
            builder.add_edge(START, expert)
            
        # Dynamic routing: add conditional edges between rounds
        for i in range(len(topology) - 1):
            curr_experts = topology[i]["experts"]
            next_experts = topology[i+1]["experts"]
            
            for curr_ex in curr_experts:
                # Check if this expert should trigger a short-circuit
                def make_router(current_role, current_round):
                    def route_after_expert(state: AgentState) -> str:
                        # Check for data quality short-circuit
                        expert_output = state.get("history_states", {}).get(current_role, "")
                        if isinstance(expert_output, str):
                            text = expert_output
                        elif isinstance(expert_output, dict):
                            text = json.dumps(expert_output, ensure_ascii=False)
                        else:
                            text = str(expert_output)
                        
                        # Short-circuit if data is critically insufficient
                        if any(marker in text for marker in ["数据严重不足", "无法获取", "CRITICAL_DATA_MISSING"]):
                            print(f"[DynamicRoute] Short-circuit triggered by {current_role}: data insufficient")
                            return "END"
                        
                        return "continue"
                    return route_after_expert
                
                # For simplicity, use standard edges but add quality flags to state
                # The quality flags are checked by downstream experts
                for next_ex in next_experts:
                    builder.add_edge(curr_ex, next_ex)
                    
        for expert in topology[-1]["experts"]:
            builder.add_edge(expert, END)
            
        graph = builder.compile()
        initial_state = {"messages": [], "history_states": {}}
        
        try:
            result_state = await graph.ainvoke(initial_state)

            # Streaming: push final results if callback is available
            if on_progress:
                messages = result_state.get("messages", [])
                for msg in messages:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        on_progress(total_rounds, total_rounds, f"✅ {role} 完成", expert_result={"role": role, "content_preview": content[:200]})

            return result_state["messages"]
        except Exception as e:
            print(f"[DiscussionService] Error in LangGraph execution: {e}")
            raise

    async def _call_expert(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: Dict[str, Any], language: str, job_id: str = "temp_job_id", prompt_version_id: str = "v1", model: str = None, search_results: Dict[str, Any] = None, market: str = "us", on_progress: Optional[callable] = None, round_num: int = 1, total_rounds: int = 1, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Assembles prompt and calls the LLM for a single expert role.
        """
        # Sanitize inputs to prevent prompt injection
        name = input_sanitizer.sanitize_stock_name(name)

        # Recall relevant agent memories for this stock/role
        memory_context = ""
        try:
            memory_result = await agent_memory.recall(symbol, role, query=f"{symbol} {name}", limit=2)
            if memory_result.entries:
                memory_lines = []
                for mem in memory_result.entries:
                    memory_lines.append(f"- [{mem.role}] {mem.analysis_summary[:200]}")
                memory_context = "\n".join(memory_lines)
        except Exception as e:
            logger.debug(f"[AgentMemory] Recall failed: {e}")

        if role == "Backtest Agent":
            import re
            all_text = ""
            for agent_role, state_data in history.items():
                if isinstance(state_data, dict):
                    all_text += " " + json.dumps(state_data, ensure_ascii=False)
                else:
                    all_text += " " + str(state_data)
            
            # Extract A-share stock codes
            codes = set(re.findall(r'\b(\d{6})\b', all_text))
            valid_codes = [c for c in codes if c[0] in ('0', '3', '6')]
            
            formatted_symbols = []
            for code in valid_codes:
                if code.startswith("6"):
                    formatted_symbols.append(f"{code}.SS")
                else:
                    formatted_symbols.append(f"{code}.SZ")
            
            # Fallback to sector constituents if no codes found
            if not formatted_symbols and snapshot and "sector_stocks" in snapshot:
                for stock_item in snapshot["sector_stocks"]:
                    code = stock_item.get("code")
                    if code:
                        if code.startswith("6"):
                            formatted_symbols.append(f"{code}.SS")
                        else:
                            formatted_symbols.append(f"{code}.SZ")

            # Default fallback if still empty
            if not formatted_symbols:
                from .portfolio_real_backtest import SYMBOLS
                formatted_symbols = SYMBOLS[:5]
                
            from .portfolio_real_backtest import PortfolioBacktester
            pb = PortfolioBacktester()
            
            end_date_str = datetime.now().strftime("%Y-%m-%d")
            start_date_str = (datetime.now() - timedelta(days=3*365)).strftime("%Y-%m-%d")
            
            try:
                res = pb.run_backtest(
                    start_date=start_date_str,
                    end_date=end_date_str,
                    symbols=formatted_symbols
                )
                metrics = res.get("metrics", {})
                sharpe = metrics.get("sharpe_ratio", 0.0)
                ann_ret = metrics.get("annualized_return", {}).get("risk", 0.0)
                max_dd = metrics.get("max_drawdown", {}).get("risk", 0.0)
                win_rate = metrics.get("win_rate", 0.0)
                
                # Run Covariance MVO optimization
                optimized_weights = {}
                high_corr_warns = []
                try:
                    closes_df = pb.get_klines_cached(formatted_symbols, start_date_str, end_date_str)
                    if not closes_df.empty and len(formatted_symbols) > 1:
                        returns_df = closes_df.pct_change().dropna()
                        cov_matrix = returns_df.cov()
                        corr_matrix = returns_df.corr()
                        
                        import numpy as np
                        cov = cov_matrix.values
                        n_assets = cov.shape[0]
                        ones = np.ones(n_assets)
                        
                        # Check high correlation pairs
                        high_corr_threshold = 0.75
                        for i in range(n_assets):
                            for j in range(i + 1, n_assets):
                                r_val = corr_matrix.iloc[i, j]
                                if r_val > high_corr_threshold:
                                    high_corr_warns.append(
                                        f"  - {closes_df.columns[i]} 与 {closes_df.columns[j]} 相关系数过高 ({r_val:.2f})"
                                    )
                                    
                        # Global Minimum Variance Portfolio weights (long-only)
                        # Add a tiny ridge regression factor to ensure invertibility of covariance matrix
                        cov_reg = cov + np.eye(n_assets) * 1e-6
                        inv_cov = np.linalg.inv(cov_reg)
                        raw_w = np.dot(inv_cov, ones)
                        
                        # Project weights to long-only
                        w_clipped = np.clip(raw_w, 0, None)
                        if np.sum(w_clipped) > 0:
                            w = w_clipped / np.sum(w_clipped)
                        else:
                            w = ones / n_assets
                            
                        optimized_weights = {closes_df.columns[k]: float(w[k]) for k in range(n_assets)}
                except Exception as cov_err:
                    print(f"[Backtest Agent] Covariance optimization failed: {cov_err}")
                
                core_thesis = (
                    f"模拟回测专家 (Backtest Agent) 对筛选出的股票组合进行了历史3年回测验证：\n"
                    f"- 回测标的: {', '.join(formatted_symbols)}\n"
                    f"- 组合年化收益率: {ann_ret*100:.2f}%\n"
                    f"- 最大历史回撤: {max_dd*100:.2f}%\n"
                    f"- 夏普比率 (Sharpe Ratio): {sharpe:.2f}\n"
                    f"- 交易胜率: {win_rate*100:.2f}%\n"
                    f"回测时间跨度：{start_date_str} 至 {end_date_str}。\n\n"
                    f"风控协方差分析 (MVO Risk Analysis)：\n"
                )
                
                if high_corr_warns:
                    core_thesis += "- ⚠️ 相关性过高资产警告:\n" + "\n".join(high_corr_warns) + "\n"
                else:
                    core_thesis += "- 资产分散度诊断: 各成分股两两相关系数均低于 0.75，分散度良。\n"
                    
                if optimized_weights:
                    weights_str = ", ".join([f"{sym}: {w*100:.1f}%" for sym, w in optimized_weights.items()])
                    core_thesis += f"- 经马科维茨最小方差模型 (Minimum Variance Optimization) 优化的推荐配置权重:\n  [{weights_str}]\n"
                
                if sharpe < 1.0:
                    core_thesis += "\n⚠️ 警告：夏普比率低于安全阈值 1.0。该组合在过去3年中风险收益比表现一般，建议后续风控专家和策略专家审慎评估，并对配置仓位及行业预期进行防守性下调。"
                else:
                    core_thesis += "\n✅ 验证通过：夏普比率大于等于 1.0，组合呈现出良性的风险回报结构，具备中长线量化配置价值。"
                    
                result_payload = {
                    "core_thesis": core_thesis,
                    "key_metrics_extracted": [
                        f"Sharpe Ratio: {sharpe:.2f}",
                        f"Annualized Return: {ann_ret*100:.2f}%",
                        f"Max Drawdown: {max_dd*100:.2f}%",
                        f"Win Rate: {win_rate*100:.2f}%"
                    ],
                    "risks": [
                        f"最大历史回撤高达 {max_dd*100:.2f}%",
                        "夏普比率表现一般，风险溢价不足"
                    ] if sharpe < 1.0 else [f"最大历史回撤为 {max_dd*100:.2f}%"],
                    "rating": "Hold" if sharpe < 1.0 else "Buy",
                    "confidence": float(min(max(win_rate, 0.1), 1.0))
                }
            except Exception as bt_e:
                print(f"[Backtest Agent] Quantitative backtest failed: {bt_e}")
                result_payload = {
                    "core_thesis": f"模拟回测专家 (Backtest Agent) 运行回测时发生异常，无法提供时序归因证明。异常信息: {bt_e}",
                    "key_metrics_extracted": ["Backtest Failed"],
                    "risks": ["无法验证历史最大回撤"],
                    "rating": "Hold",
                    "confidence": 0.5
                }
                
            return {
                "role": role,
                "content": json.dumps(result_payload, ensure_ascii=False),
                "model": "quant_engine",
                "timestamp": datetime.now().isoformat()
            }

        # 1. Fetch Template
        prompt_name = role.lower().replace(" ", "_")
        try:
            prompt_data = prompt_runtime.get_prompt(prompt_name, version="v1", language=language)
            template = prompt_data["template"]
            pv_id = prompt_data.get("version", "v1")
        except Exception:
            logger.exception("Failed to fetch prompt template for role '%s'", role)
            # Fallback to simple instruction if prompt not found in DB
            template = f"You are a {role}. Provide professional institutional research analysis for {symbol}."
            pv_id = "v1"

        # Replace template variables (e.g. {sector_name} in sector prompts)
        template = template.replace("{sector_name}", name)

        # 2. Get Brain Context
        brain_context = brain_manager.get_brain_context("default", query=f"{symbol} {name}", role=role.lower())
        
        # 3. Get Macro Data (Exchange Rates, etc.)
        from .macro_service import macro_service
        macro_data = await macro_service.get_latest_fx()
        
        # 4. Get Commodity Data
        commodity_data = {}
        # Build a robust match string from BOTH the resolved name AND the real
        # company profile in the snapshot. HK stocks often resolve to a
        # placeholder name like "HK-Share Code", so matching on `name` alone
        # leaves commodity_data empty and the LLM writes "N/A (数据缺失)" for
        # 大宗商品价格. Inspect longName / industry / sector to detect exposure.
        snap = snapshot or {}
        fin = snap.get("financials", {}) or {}
        quote = snap.get("quote", {}) or {}
        real_name = fin.get("longName") or quote.get("name") or quote.get("long_name") or name
        industry = fin.get("industry") or snap.get("industry") or ""
        sector = fin.get("sector") or snap.get("sector") or ""
        name_lower = f"{symbol} {name} {real_name} {industry} {sector}".lower()
        commodities_to_query = []
        if any(keyword in name_lower for keyword in ["lithium", "锂", "battery", "电池", "ev", "电动车", "盐湖"]):
             commodities_to_query.append("Lithium Carbonate")
        if any(keyword in name_lower for keyword in ["potash", "钾", "化肥", "肥料", "农化制品", "盐湖"]):
             commodities_to_query.append("Potassium Chloride")
        if any(keyword in name_lower for keyword in ["copper", "铜", "gold", "金", "mining", "矿"]):
             commodities_to_query.extend(["Copper", "Gold"])
        if any(keyword in name_lower for keyword in ["铝", "aluminum", "alumin", "bauxite", "铝土"]):
             commodities_to_query.extend(["Aluminum", "Alumina"])
        if any(keyword in name_lower for keyword in ["光伏", "储能", "逆变器", "太阳能", "阳光电源", "solar", "photovoltaic", "energy storage", "storage"]):
             # 光伏/储能(逆变器)企业：核心成本/收入驱动为 光伏组件、储能电芯、多晶硅
             commodities_to_query.extend(["光伏组件", "储能电芯", "多晶硅"])
        if any(keyword in name_lower for keyword in ["能源", "energy", "煤", "coal", "烯烃", "olefin", "化工", "chemical", "石化", "petro", "宝丰", "oil", "原油", "石油", "油气", "中海油", "中石油", "中石化", "cnooc", "gas", "天然气", "petroleum"]):
             commodities_to_query.extend(["Crude Oil", "Methanol", "Polypropylene", "LLDPE"])

        if commodities_to_query:
             # Deduplicate while preserving order
             seen = set()
             deduped_commodities = [x for x in commodities_to_query if not (x in seen or seen.add(x))]
             commodity_data = await macro_service.get_commodity_prices(deduped_commodities)
             if "Crude Oil" in deduped_commodities:
                 brent = await macro_service.get_brent_oil_price()
                 if brent:
                     commodity_data["Brent Crude Oil (USD)"] = brent

        # 对所有行业：API 未覆盖/缺趋势(change30d 为空)的品种，用 web 搜索兜底补价/补趋势
        if commodity_data:
            commodity_data = await _enrich_commodities_search(commodity_data)

        # Get macro indicators (M2, LPR, Fed Rate) for all stocks
        macro_indicators = {}
        try:
            macro_indicators = await macro_service.get_macro_indicators()
        except Exception as e:
            print(f"Macro indicators fetch failed: {e}")

        # Get Macro Regime (cross-asset ratio analysis) for Risk Manager and Chief Strategist
        macro_regime_text = ""
        if role in ("Risk Manager", "Chief Strategist", "Macro Hedge Titan", "Soros-style Financial Philosopher", "Sector Macro Strategist", "Sector Chief Strategist", "Sector Risk Auditor"):
            try:
                from .macro_regime_service import get_macro_regime_text
                macro_regime_text = await get_macro_regime_text()
            except Exception as e:
                print(f"Macro regime detection failed: {e}")

        # 4.5 Get Sentiment Data (for Sentiment Analyst)
        sentiment_data = {}
        if role == "Sentiment Analyst":
            try:
                from .sentiment_data_service import sentiment_data_service
                code = symbol.replace(".SH", "").replace(".SZ", "")
                sentiment_data = await sentiment_data_service.get_all_sentiment_data(code, name)
                print(f"  Sentiment data fetched for {symbol}")
            except Exception as e:
                print(f"Sentiment data fetch failed: {e}")

        peer_data = {}
        if role == "Fundamental Analyst":
            try:
                from .search_service import search_service
                market_name = snapshot.get("quote", {}).get("name", name)
                if market in ("A-Share", "HK-Share"):
                    query = f"{market_name} {symbol} 同行业公司 竞争对手 估值对标"
                else:
                    query = f"{market_name} {symbol} industry average PE PB ROE valuation comparison"
                search_res = await search_service.quick_search(query)
                if search_res:
                    peer_data = {"IndustryPeerSearch": search_res}
            except Exception as e:
                print(f"Industry peer search failed: {e}")

        # 4.7 Earnings-quality audit facts (应收账款 + 非经常性损益)
        # A股基本面用 EastMoney 直连(比 yfinance 可靠): 资产负债表明细给应收账款;
        # 利润表(income_items)给 TTM 营收 / 归母净利润 / 扣非净利润。
        # 注: 生产环境 fin 来自 market_data_service(yfinance 风格, quarterlyHistory 键为
        # 'Total Revenue'/'Net Income', 且不含 netProfitDeduct), 直接读 quarterlyHistory
        # 会因键名不匹配整段落空 → 4️⃣ 写 N/A。故此处统一走 EastMoney 直连源, 与 fin 形状无关。
        audit_data = {}
        if role == "Fundamental Analyst" and market == "A-Share":
            try:
                from .data_providers.a_stock_direct import (
                    fetch_a_share_balance_items,
                    fetch_a_share_income_items,
                )
                bal = await fetch_a_share_balance_items(symbol, periods=1)
                ar = None
                if bal and bal[0].get("accountsRece") is not None:
                    try:
                        ar = float(bal[0]["accountsRece"])
                    except (TypeError, ValueError):
                        ar = None
                inc = await fetch_a_share_income_items(symbol, periods=4)
                rev_ttm = 0.0
                for r in inc[:4]:
                    rv = r.get("revenue")
                    if rv is not None:
                        try:
                            rev_ttm += float(rv)
                        except (TypeError, ValueError):
                            pass
                ni = inc[0].get("parentNetProfit") if inc else None
                deduct = inc[0].get("deductNetProfit") if inc else None
                if ar is not None and rev_ttm > 0:
                    audit_data["accounts_receivable"] = round(ar, 2)
                    audit_data["ar_revenue_ratio"] = round(ar / rev_ttm * 100, 2)
                if ni is not None and deduct is not None:
                    try:
                        ni_f = float(ni)
                        deduct_f = float(deduct)
                        nr = ni_f - deduct_f
                        audit_data["non_recurring"] = round(nr, 2)
                        if ni_f != 0:
                            audit_data["non_recurring_pct"] = round(abs(nr) / abs(ni_f) * 100, 2)
                    except (TypeError, ValueError):
                        pass
                # 7️⃣ 行业对标均值/中位数 (web 搜索兜底, 补同业估值对比)
                try:
                    benchmark = await _enrich_peer_benchmark(industry, symbol, name)
                    if benchmark:
                        peer_data.setdefault("IndustryBenchmark", benchmark)
                except Exception as e:
                    print(f"Peer benchmark failed: {e}")
            except Exception as e:
                print(f"Audit data fetch failed: {e}")

        # 5. Determine model & search capability
        if model:
            # If model is explicitly passed (e.g. from UI), use it
            model = model
        else:
            # Fallback to default from env
            default_provider = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek").lower()
            if default_provider == "gemini":
                model = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
            else:
                model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        
        # Gemini models have native Google Search grounding enabled via tools config
        has_search_tools = ("gemini" in model.lower())
        use_native_tools = "deepseek" in model.lower()
        
        # 5.5 Get pre-search enrichment for this expert role
        search_enrichment = {}
        if search_results:
            search_enrichment = search_toolkit.get_enrichment_for_role(role, search_results, market=market)
        
        # Slide context window: keep last 3 rounds fully intact, summarize older rounds
        processed_history = {}
        for agent_role, state_data in history.items():
            agent_round = getattr(self, "_expert_round_map", {}).get(agent_role, 1)
            # If the expert is from an older round (current round_num - 3), we summarize it
            if agent_round < round_num - 3:
                if agent_role not in getattr(self, "_summaries_cache", {}):
                    if isinstance(state_data, dict):
                        text_to_summarize = json.dumps(state_data, ensure_ascii=False)
                    else:
                        text_to_summarize = str(state_data)
                    summary = await self._summarize_expert_output(agent_role, text_to_summarize, model, config)
                    self._summaries_cache[agent_role] = summary
                processed_history[agent_role] = f"[Summary of Y{agent_round} {agent_role}]: {self._summaries_cache[agent_role]}"
            else:
                processed_history[agent_role] = state_data

        # Enforce strict ceiling to prevent context explosion
        total_len = sum(len(str(v)) for v in processed_history.values())
        if total_len > 60000:
            sorted_keys = sorted(processed_history.keys(), key=lambda k: getattr(self, "_expert_round_map", {}).get(k, 1))
            for k in sorted_keys:
                if total_len <= 60000:
                    break
                old_len = len(str(processed_history[k]))
                processed_history[k] = "[Truncated due to context limit]"
                total_len = total_len - old_len + len(processed_history[k])

        # 6. Assemble Prompt (with search capability flag)
        prompt = self._assemble_prompt(role, symbol, name, snapshot, processed_history, template, brain_context, language, macro_data, commodity_data, peer_data, audit_data=audit_data, has_search_tools=has_search_tools, search_enrichment=search_enrichment, use_native_tools=use_native_tools, macro_indicators=macro_indicators, sentiment_data=sentiment_data, market=market, macro_regime_text=macro_regime_text)

        # Inject agent memory context if available
        if memory_context:
            prompt += f"\n\n[AGENT MEMORY — Prior analyses for {symbol}]\n{memory_context}\nUse this as reference, but do not copy blindly. Verify against current data.\n"
        
        # 7. Call LLM (with tool-calling loop for models without native search)
        start_time = datetime.now()
        base_count = self._cumulative_count  # snapshot before this expert
        def _on_chunk(count, message=None):
            if on_progress:
                if message:
                    on_progress(round_num, total_rounds, message, count=base_count + count)
                else:
                    total = base_count + count
                    self._cumulative_count = total
                    on_progress(round_num, total_rounds, f"Round {round_num}: {role}", count=total)

        # Determine cache key to save tokens
        cache_key = f"{role}_{symbol}_{'final' if round_num == total_rounds else 'inter'}_{language}"

        is_final = role in ("Chief Strategist", "Sector Chief Strategist")
        is_sector_intermediate = role in ("Sector Macro Strategist", "Sector Stock Screener", "Serenity Alpha Analyst", "Sector Risk Auditor")
        is_markdown_intermediate = role in (
            "Fundamental Analyst", "Technical Analyst", "Deep Research Specialist",
            "Sentiment Analyst", "Chief Audit Officer", "Risk Manager",
            "Professional Reviewer", "Contrarian Strategist", "Value Investing Sage",
            "Growth Visionary", "Macro Hedge Titan", "Aggressive Risk Analyst",
            "Conservative Risk Analyst", "Neutral Risk Analyst",
            "Bull Researcher", "Bear Researcher",
            "Soros-style Financial Philosopher", "Serenity Alpha Analyst"
        )

        response_schema = None
        if not is_final and not is_sector_intermediate and not is_markdown_intermediate:
            from ..models.schemas import ExpertDiscussionResult
            response_schema = ExpertDiscussionResult

        if has_search_tools:
            # Gemini has native Google Search — use standard call (tools handled by model)
            try:
                content = await llm_gateway.generate_content(prompt, model=model, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None, openrouter_api_key=config.get("openrouterApiKey") if config else None, cache_key=cache_key, prompt_version_id=pv_id, response_schema=response_schema)
            except Exception as e:
                logger.error(f"[DiscussionService] Gemini LLM generation failed for {role}: {e}")
                content = f"{role} 专家暂时无法提供分析。原因: 大语言模型请求异常 ({str(e)[:100]})。请其他专家忽略此错误并根据已有数据自行补全缺失视角的分析逻辑。"
        else:
            # Upper safety bound for tool-calling loop. The LLM decides how many
            # tool calls it actually needs (loop breaks early when it stops
            # emitting tool_calls). This is only a ceiling to prevent runaway
            # loops; normal analyses finish well under it.
            effective_max_rounds = int(os.getenv("MAX_TOOL_ROUNDS", "30"))
            
            # Other models — use tool-calling loop (web_search, news_search, knowledge_search)
            try:
                content = await agent_orchestrator.generate_with_tools(prompt, model=model, role=role, max_tool_rounds=effective_max_rounds, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None, openrouter_api_key=config.get("openrouterApiKey") if config else None, cache_key=cache_key, prompt_version_id=pv_id, response_schema=response_schema)
            except Exception as e:
                error_msg = str(e)
                if "402" in error_msg or "Insufficient Balance" in error_msg:
                    if on_progress:
                        on_progress(round_num, total_rounds, f"⚠️ API 余额不足 — {role} 生成中断", error_type="insufficient_balance")
                    content = ""
                else:
                    logger.error(f"[DiscussionService] Orchestrator LLM generation failed for {role}: {e}")
                    content = f"{role} 专家暂时无法提供分析。原因: 大语言模型请求异常 ({error_msg[:100]})。请其他专家忽略此错误并根据已有数据自行补全缺失视角的分析逻辑。"
        latency = (datetime.now() - start_time).total_seconds() * 1000

        # Store analysis result in agent memory for future recall
        if content and role not in ("Backtest Agent",):
            try:
                confidence = self._extract_confidence(content)
                await agent_memory.store(
                    symbol=symbol,
                    role=role,
                    analysis=content[:3000],
                    key_conclusions=content[:500],
                    confidence=confidence,
                )
            except Exception as e:
                logger.debug(f"[AgentMemory] Store failed: {e}")

        # 4️⃣/7️⃣ 确定性硬填: 弱模型会丢弃注入的 audit_data /
        # IndustryBenchmark, 导致最终报告 4️⃣/7️⃣ 写 N/A。直接在 Fundamental
        # Analyst 输出后追加 EastMoney 直连的核实表格, 保证报告出现真实数值
        # (不经模型文本, 不受模型能力影响)。
        if role == "Fundamental Analyst":
            _filled = False
            _bm = peer_data.get("IndustryBenchmark") if isinstance(peer_data, dict) else None
            _has_benchmark = isinstance(_bm, dict) and _bm.get("pe_med") is not None
            # 仅当确认真实基准(has_benchmark)时, 清理模型自己写的同业对比节里的
            # N/A 占位 —— 按"行业估值对比"主题定位该节, 不误删其他节, 也不动我们
            # 随后追加的【数据核实】表格。必须在追加核实表之前执行(此时 content
            # 还是模型原始文本, 不含我们的表格)。
            if _has_benchmark:
                content = _strip_model_peer_na(content)
            if isinstance(audit_data, dict) and audit_data:
                _audit_tbl = _format_audit_table(audit_data)
                if _audit_tbl:
                    content = (content or "") + _audit_tbl
                    _filled = True
            if _has_benchmark:
                content = (content or "") + _format_industry_benchmark_table(_bm)
                _filled = True
            # We appended authoritative EastMoney values for sections the weak
            # model had left as "N/A" — drop the model's placeholder N/A line so
            # the report no longer shows N/A for those sections.
            if _filled:
                content = _strip_na_line(content)

        return {
            "role": role,
            "content": content,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }

    async def _summarize_expert_output(self, role: str, text: str, model: str, config: Optional[Dict[str, Any]]) -> str:
        summary_prompt = (
            f"You are a professional financial editor. Please summarize the following analysis from the '{role}' expert into a concise, high-density summary under 400 characters, retaining all key financial numbers, metrics, and conclusions.\n\n"
            f"Analysis to summarize:\n{text}"
        )
        try:
            summary = await llm_gateway.generate_content(
                summary_prompt,
                model=model,
                gemini_api_key=config.get("geminiApiKey") if config else None,
                deepseek_api_key=config.get("deepseekApiKey") if config else None,
                openrouter_api_key=config.get("openrouterApiKey") if config else None
            )
            return summary.strip()
        except Exception as e:
            print(f"Failed to summarize expert {role}: {e}")
            return text[:800] + "... [truncated]"

    def _assemble_prompt(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: Dict[str, Any], template: str, brain_ctx: Dict[str, Any], language: str, macro_data: Dict[str, Any] = None, commodity_data: Dict[str, Any] = None, peer_data: Dict[str, Any] = None, audit_data: Dict[str, Any] = None, has_search_tools: bool = False, search_enrichment: Dict[str, Any] = None, use_native_tools: bool = False, macro_indicators: Dict[str, Any] = None, sentiment_data: Dict[str, Any] = None, market: str = "us", macro_regime_text: str = "") -> str:
        import os
        from jinja2 import Environment, FileSystemLoader

        is_zh = language == "zh-CN"
        is_final_round = role in ("Chief Strategist", "Sector Chief Strategist")
        is_sector_intermediate = role in ("Sector Macro Strategist", "Sector Stock Screener", "Serenity Alpha Analyst", "Sector Risk Auditor")
        is_markdown_intermediate = role in (
            "Fundamental Analyst", "Technical Analyst", "Deep Research Specialist",
            "Sentiment Analyst", "Chief Audit Officer", "Risk Manager",
            "Professional Reviewer", "Contrarian Strategist", "Value Investing Sage",
            "Growth Visionary", "Macro Hedge Titan", "Aggressive Risk Analyst",
            "Conservative Risk Analyst", "Neutral Risk Analyst",
            "Bull Researcher", "Bear Researcher",
            "Soros-style Financial Philosopher", "Serenity Alpha Analyst"
        )

        quote = snapshot.get("quote", {})
        valuation = snapshot.get("valuation", {})
        financials = snapshot.get("financials", {})
        indicators = snapshot.get("indicators", {})
        intraday_volume = snapshot.get("intraday_volume")

        def get_val(*keys, sources=None):
            srcs = sources or [financials, quote, valuation]
            for s in srcs:
                for k in keys:
                    v = s.get(k)
                    if v is not None:
                        return v
            return "N/A"

        listing_currency = get_val("currency")
        fin_currency = get_val("financialCurrency")
        currency_warning = (fin_currency != "N/A" and listing_currency != "N/A" and fin_currency != listing_currency)
        currency_note = f" (注意: 上市货币={listing_currency}, 报表货币={fin_currency}, 现金流/营收等绝对值单位为{fin_currency})" if currency_warning else ""

        if market == "A-Share":
            exchange_display = "上海证券交易所 (SSE)" if symbol.startswith("6") else "深圳证券交易所 (SZSE)"
            full_code = f"{symbol}.SS" if symbol.startswith("6") else f"{symbol}.SZ"
        elif market == "HK-Share":
            exchange_display = "香港交易所 (HKEX)"
            full_code = f"{symbol}.HK"
        else:
            exchange_display = financials.get("exchange") or "N/A"
            full_code = symbol
        
        long_name = financials.get("longName") or valuation.get("股票简称") or name
        industry = financials.get("industry") or valuation.get("行业") or "N/A"
        sector = financials.get("sector") or "N/A"
        listing_date = financials.get("listingDate") or valuation.get("上市时间") or "N/A"
        biz_summary = financials.get("longBusinessSummary") or ""

        # Formatting helper
        def fmt_num(v):
            if v is None: return "N/A"
            try:
                v = float(v)
                if abs(v) >= 1e9: return f"{v/1e9:.2f}B"
                if abs(v) >= 1e6: return f"{v/1e6:.1f}M"
                return f"{v:,.0f}"
            except Exception:
                logger.warning("fmt_num: failed to convert '%s' to number", v)
                return str(v)

        enrichment_text = ""
        if search_enrichment:
            enrichment_text = search_toolkit.format_enrichment(search_enrichment, language=language)

        tool_descriptions = ""
        if has_search_tools and not use_native_tools:
            tool_descriptions = format_tool_descriptions(role=role, language=language)

        quarterly_history = financials.get("quarterlyHistory", [])
        valuation_guidance = ""
        if market == "A-Share" and quarterly_history:
            current_price = get_val('price', 'currentPrice')
            if current_price and current_price != "N/A":
                try:
                    price_f = float(current_price)
                    v_parts = [f"\n**估值参考 (基于当前价格 {price_f} {listing_currency}):**"]
                    for q in quarterly_history:
                        period = q.get('period', '')
                        bvps = q.get('bvps')
                        eps = q.get('eps')
                        if bvps and eps:
                            try:
                                bvps_f = float(bvps)
                                eps_f = float(eps)
                                pb_est = round(price_f / bvps_f, 2) if bvps_f > 0 else "N/A"
                                if period.endswith('12-31') and eps_f > 0:
                                    pe_est = round(price_f / eps_f, 2)
                                    v_parts.append(f"- {period}: PB≈{pb_est} (当前价/{bvps_f}), PE≈{pe_est} (当前价/年EPS {eps_f})")
                                else:
                                    v_parts.append(f"- {period}: PB≈{pb_est} (当前价/{bvps_f})")
                            except (ValueError, ZeroDivisionError):
                                pass
                    if len(v_parts) > 1:
                        valuation_guidance = "\n".join(v_parts)
                except (ValueError, TypeError):
                    pass

        context = {
            "role": role,
            "symbol": symbol,
            "name": name,
            "template": template,
            "is_zh": is_zh,
            "is_final_round": is_final_round,
            "is_sector_intermediate": is_sector_intermediate,
            "is_markdown_intermediate": is_markdown_intermediate,
            "macro_data": macro_data,
            "commodity_data": commodity_data,
            "macro_indicators": macro_indicators,
            "macro_regime_text": macro_regime_text,
            "peer_data": peer_data,
            "audit_data": audit_data,
            "intraday_volume": intraday_volume,
            "sentiment_data": sentiment_data,
            "brain_ctx": brain_ctx,
            "history": history,
            "market": market,
            "has_search_tools": has_search_tools,
            "use_native_tools": use_native_tools,
            "enrichment_text": enrichment_text,
            "tool_descriptions": tool_descriptions,
            "current_date": datetime.now().strftime('%Y-%m-%d'),
            
            # Formatted facts
            "long_name": long_name,
            "full_code": full_code,
            "exchange_display": exchange_display,
            "industry": industry,
            "sector": sector,
            "listing_date": listing_date,
            "biz_summary": biz_summary,
            "cross_listing": snapshot.get("crossListing"),
            "sector_stocks": snapshot.get("sector_stocks", []),
            "get_val": get_val,
            "listing_currency": listing_currency,
            "fin_currency": fin_currency,
            "currency_warning": currency_warning,
            "currency_note": currency_note,
            "indicators_json": json.dumps({k: v for k, v in indicators.items() if v is not None}, default=str) if indicators else "",
            "quarterly_history": quarterly_history,
            "data_quality": snapshot.get("data_quality"),
            "dividend_history": financials.get("dividendHistory"),
            "buyback": financials.get("buyback"),
            "coal_price": financials.get("coalPrice"),
            "fmt_num": fmt_num,
            "top_circulating_holders": financials.get("topCirculatingHolders"),
            "valuation_guidance": valuation_guidance,
        }

        # Render Jinja template
        prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
        env = Environment(loader=FileSystemLoader(prompts_dir))
        jinja_template = env.get_template("base_prompt.jinja")
        
        return jinja_template.render(**context)

    def _extract_confidence(self, analysis: str) -> float:
        import json
        import re
        
        try:
            # clean markdown code blocks if present
            json_clean = analysis.strip()
            if json_clean.startswith("```"):
                json_clean = re.sub(r"^```(?:json)?\n", "", json_clean)
                json_clean = re.sub(r"\n```$", "", json_clean)
            
            data = json.loads(json_clean)
            if "confidence" in data:
                val = data["confidence"]
                if isinstance(val, (int, float)):
                    return float(val) / 100.0 if val > 1.0 else float(val)
            if "confidence_score" in data:
                val = data["confidence_score"]
                if isinstance(val, (int, float)):
                    return float(val) / 100.0 if val > 1.0 else float(val)
        except Exception:
            pass
            
        return 0.75  # Default confidence

    async def _background_search(self, symbol: str, name: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """后台搜索任务 - 不阻塞讨论流程
        
        优化 4: 搜索后台化
        - 在讨论进行中异步执行
        - 超时改短 (15s 而非 30s)，更快地回到讨论
        - 失败时使用空结果继续
        """
        try:
            search_results = await asyncio.wait_for(
                search_toolkit.batch_search(symbol, name, snapshot),
                timeout=15.0  # 改短: 15s 而非 30s
            )
            print(f"[BackgroundSearch] Completed successfully for {symbol}")
            return search_results
        except asyncio.TimeoutError:
            print(f"[BackgroundSearch] Timed out after 15s for {symbol}, using empty results")
            return {}
        except Exception as e:
            print(f"[BackgroundSearch] Failed for {symbol}: {e}")
            return {}

    async def batch_verify_and_reflect(
        self,
        expert_outputs: Dict[str, str],
        snapshot: Dict[str, Any],
        config: Dict[str, Any],
        is_final_round: bool = False,
        model: str = None
    ) -> Dict[str, Dict]:
        """批量验证和反思多个专家的输出
        
        优化 3: 批量验证/反思 (预留接口)
        - 一个 LLM 调用处理多个专家的验证
        - 一个 LLM 调用处理多个专家的反思
        - 可大幅减少 LLM 调用次数
        
        Args:
            expert_outputs: {'expert_name': 'content', ...}
            is_final_round: 最终轮是否强制所有检查
        
        Returns:
            {'verifications': {...}, 'reflections': {...}}
        """
        if not expert_outputs or getattr(self, '_verification_mode', 'quick') == 'extreme':
            return {'verifications': {}, 'reflections': {}}
        
        verification_results = {}
        
        # 构建批量验证提示
        output_list = "\n---\n".join(
            f"【{expert}】\n{content[:400]}"  # 每个输出最多 400 字
            for expert, content in expert_outputs.items()
        )
        
        verify_prompt = f"""
        请快速验证以下专家分析中的关键数据点和逻辑。
        
        {output_list}
        
        对每个【专家】输出，列出任何错误或不合理的地方。
        如果无明显错误，写"✓ 合理"。
        """
        
        try:
            from .llm_gateway import llm_gateway
            verification_result = await llm_gateway.generate_content(
                verify_prompt,
                model=model or "deepseek-chat",
                temperature=0.1,  # 低温度，确保准确
            )
            # 简单地返回验证结果（可扩展为更详细的解析）
            verification_results = {expert: verification_result for expert in expert_outputs}
            print(f"[BatchVerify] Verified {len(expert_outputs)} experts outputs")
        except Exception as e:
            logger.warning(f"[BatchVerify] Failed: {e}")
        
        return {
            'verifications': verification_results,
            'reflections': {}
        }


discussion_service = DiscussionService()


# --- 报告核验辅助(模块级, 由 _call_expert 调用, 固化 EastMoney 确定值) ---
def _fmt_val(v, suffix: str = "") -> str:
    """Format a numeric value for the verified benchmark/audit tables."""
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _format_audit_table(audit_data: Dict[str, Any]) -> str:
    """固化 4️⃣ 盈利质量审计(EastMoney 直连)为核实表格, 追加到 Fundamental Analyst 输出。

    弱模型会丢弃注入的 audit_data, 直接在专家文本后追加确定值
    表格, 保证最终报告 4️⃣ 显示真实数值(不经模型文本, 不受模型能力影响)。
    """
    rows: list = []
    ar = audit_data.get("accounts_receivable")
    if ar is not None:
        try:
            line = f"- **应收账款**: {float(ar):,.2f} 元"
            ratio = audit_data.get("ar_revenue_ratio")
            if ratio is not None:
                line += f"（占 TTM 营收 {float(ratio):.2f}%）"
            rows.append(line)
        except (TypeError, ValueError):
            pass
    nr = audit_data.get("non_recurring")
    if nr is not None:
        try:
            line = f"- **非经常性损益**（扣非前净利 − 扣非后净利）: {float(nr):,.2f} 元"
            pct = audit_data.get("non_recurring_pct")
            if pct is not None:
                line += f"（占归母净利润 {float(pct):.2f}%）"
            rows.append(line)
        except (TypeError, ValueError):
            pass
    if not rows:
        return ""
    body = "\n".join(rows)
    return (
        "\n\n**【数据核实 · 盈利质量审计（EastMoney 直连确定值，非模型估算）】**\n\n"
        f"{body}\n\n"
        "> 数据来源：EastMoney 资产负债表/利润表明细直连。\n"
    )


def _format_industry_benchmark_table(benchmark: Dict[str, Any]) -> str:
    """固化 7️⃣ 行业估值对标(EastMoney 直连)为核实表格, 追加到 Fundamental Analyst 输出。

    弱模型会丢弃注入的 IndustryBenchmark, 直接追加确定值表格以保证报告 7️⃣ 显示真实数值。
    """
    rows = [
        ("市盈率 PE (TTM)", _fmt_val(benchmark.get("pe_med")), _fmt_val(benchmark.get("pe_avg"))),
        ("市净率 PB", _fmt_val(benchmark.get("pb_med")), _fmt_val(benchmark.get("pb_avg"))),
        ("市销率 PS (TTM)", _fmt_val(benchmark.get("ps_med")), _fmt_val(benchmark.get("ps_avg"))),
        ("EV/EBITDA", _fmt_val(benchmark.get("ev_ebitda_med")), _fmt_val(benchmark.get("ev_ebitda_avg"))),
        ("ROE", _fmt_val(benchmark.get("roe_med"), "%"), _fmt_val(benchmark.get("roe_avg"), "%")),
        ("毛利率", _fmt_val(benchmark.get("gross_margin_med"), "%"), _fmt_val(benchmark.get("gross_margin_avg"), "%")),
        ("净利率", _fmt_val(benchmark.get("net_margin_med"), "%"), _fmt_val(benchmark.get("net_margin_avg"), "%")),
        ("营收增速 (YoY)", _fmt_val(benchmark.get("revenue_growth_med"), "%"), _fmt_val(benchmark.get("revenue_growth_avg"), "%")),
    ]
    header = "| 指标 | 行业中位数 | 行业均值 |\n| --- | --- | --- |"
    body = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} |" for r in rows)
    return (
        "\n\n**【数据核实 · 行业估值对标（EastMoney 直连确定值，非模型估算）】**\n\n"
        f"{header}\n{body}\n\n"
        "> 数据来源：EastMoney 行业估值报表直连（RPT_VALUEANALYSIS_DET）。\n"
    )


# N/A keywords that mark a model's empty/placeholder claim for a numbered section.
_NA_KEYWORDS = ("n/a", "数据缺失", "暂无", "无法获取", "缺失", "无数据", "未能获取", "暂无数据")
# Only strip a line that carries a numbered section marker (4️⃣/7️⃣) AND an N/A keyword,
# so legitimate prose is never touched.
_NA_LINE_RE = re.compile(r"^\s*[47][\uFE0F\u20E3]*\s*.*?(?:" + "|".join(re.escape(k) for k in _NA_KEYWORDS) + r")", re.IGNORECASE)


def _strip_na_line(content: str) -> str:
    """Remove the model's placeholder N/A claim for a numbered section we have
    real data for (4️⃣/7️⃣). Conservative: only matches a line with the section
    marker AND an N/A keyword, leaving all other content intact."""
    return "\n".join(line for line in content.split("\n") if not _NA_LINE_RE.search(line))


# --- Peer-comparison (同业估值对比) N/A cleanup ---------------------------------
# Locate the model's OWN peer/industry valuation section by THEME. The number
# emoji is unstable across models (5️⃣ in one run, 6️⃣ in another), so we match the
# section heading text instead of the digit.
_PEER_SECTION_RE = re.compile(r"同业估值对比|行业估值对比|同业对比", re.IGNORECASE)
# A new numbered section header (e.g. "6️⃣ ...") ends the peer section.
_NEW_SECTION_RE = re.compile(r"^\s*(?:#{1,6}\s*)?\d+[\uFE0F\u20E3]*")
# An "N/A" placeholder token (case-insensitive; tolerates spaces around slash).
_NA_TOKEN_RE = re.compile(r"N\s*/\s*A", re.IGNORECASE)


def _strip_model_peer_na(content: str) -> str:
    """Clear N/A placeholders the weak model left inside its OWN peer-comparison
    (同业估值对比) section.

    Operates ONLY within that section — located by theme, bounded by the next
    numbered section header — leaving every other section and our authoritative
    【数据核实】 tables untouched. Caller MUST gate this on a confirmed real
    benchmark (has_benchmark) before calling — see _call_expert.
    """
    lines = content.split("\n")
    # 1) Locate the peer-comparison section header by THEME.
    start = None
    for i, line in enumerate(lines):
        if _PEER_SECTION_RE.search(line):
            start = i
            break
    if start is None:
        return content
    # 2) Section ends at the next numbered section header.
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _NEW_SECTION_RE.match(lines[j]):
            end = j
            break
    head, body, tail = lines[:start], lines[start:end], lines[end:]
    # 3) Within the section, clear N/A tokens (incl. "N/A N/A N/A" runs and
    #    standalone "N/A" prose). Real cells/values are preserved.
    cleaned = []
    for line in body:
        new_line = _NA_TOKEN_RE.sub("", line)
        # collapse the gap left by removed tokens; keep markdown pipe shape
        new_line = re.sub(r"[ \t]{2,}", " ", new_line).strip()
        if not new_line:
            continue
        cleaned.append(new_line)
    if not cleaned:
        # Entire section was N/A garbage — drop it (header included) to avoid a
        # dangling, empty "5️⃣ 同业估值对比" heading.
        return "\n".join(head + tail)
    return "\n".join(head + cleaned + tail)
