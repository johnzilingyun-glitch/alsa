import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from ..prompting.runtime import prompt_runtime
from .llm_gateway import llm_gateway
from .brain_manager import brain_manager
from .search_toolkit import search_toolkit
from .expert_tools import format_tool_descriptions

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
    {"round": 3, "experts": ["Sector Risk Auditor"], "parallel": False},
    {"round": 4, "experts": ["Sector Chief Strategist"], "parallel": False},
]

SERENITY_ALPHA_TOPOLOGY = [
    {"round": 1, "experts": ["Serenity Alpha Analyst"], "parallel": False}
]

class DiscussionService:
    def __init__(self):
        pass

    def build_topology(self, level: str, asset_type: str = "equity") -> List[Dict[str, Any]]:
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

        # Apply skip rules (basic implementation)
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

    async def run_discussion(self, symbol: str, name: str, snapshot: Dict[str, Any], level: str = "standard", language: str = "zh-CN", model: str = None, on_progress: Optional[callable] = None, job_id: str = "temp_job_id", config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Runs the full expert discussion flow using LangGraph.
        """
        topology = self.build_topology(level)
        market = snapshot.get("market", "us")
        self._cumulative_count = 0  # Track total chars across all experts
        
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
        
        # Pre-search enrichment: batch search ONCE before all experts
        # Report progress during search phase (stays between 30-35%)
        search_results = {}
        try:
            if on_progress:
                on_progress(0, total_rounds, "正在搜索市场数据...")
            from .search_toolkit import search_toolkit
            # Timeout batch_search at 30s to prevent blocking forever on failing searches
            search_results = await asyncio.wait_for(
                search_toolkit.batch_search(symbol, name, snapshot),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            print(f"[DiscussionService] Pre-search enrichment TIMED OUT (30s) — continuing without search data")
        except Exception as e:
            print(f"[DiscussionService] Pre-search enrichment failed (non-fatal): {e}")
            
        total_rounds = len(topology)
        
        from typing import TypedDict, Annotated, Union
        import operator
        from langgraph.graph import StateGraph, START, END
        
        class AgentState(TypedDict):
            messages: Annotated[list, operator.add]
            history_states: Annotated[dict, operator.ior]

        builder = StateGraph(AgentState)
        
        def make_node(expert_role, r_num):
            async def node_func(state: AgentState):
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
                is_final = expert_role in ("Chief Strategist", "Sector Chief Strategist")
                if not is_final:
                    content = msg.get("content", "")
                    confidence = self._extract_confidence(content)
                    # If confidence is lower than 0.6, trigger self-reflection
                    if confidence < 0.6:
                        try:
                            from .self_reflection_agent import self_reflection_agent
                            ref_config = config or {}
                            reflection_res = await self_reflection_agent.reflect(
                                expert_role=expert_role,
                                analysis=content,
                                context=state.get("history_states", {}),
                                round_num=r_num,
                                total_rounds=total_rounds,
                                gemini_api_key=ref_config.get("geminiApiKey"),
                                deepseek_api_key=ref_config.get("deepseekApiKey"),
                                model=model
                            )
                            # Attach reflection to the message
                            if "reflection" in reflection_res:
                                msg["reflection"] = reflection_res["reflection"]
                        except Exception as e:
                            print(f"[DiscussionService] Self-reflection failed for {expert_role}: {e}")
                    
                    try:
                        import json, re
                        # Summarize long text to prevent context bloat (Phase 4 Fix)
                        content_to_save = content
                        if len(content_to_save) > 2000:
                            print(f"[DiscussionService] Expert '{expert_role}' output exceeds 2000 chars, triggering summarizer...")
                            try:
                                content_to_save = await self._summarize_expert_output(expert_role, content_to_save, model, config)
                            except Exception as sum_e:
                                print(f"[DiscussionService] Summarization failed, truncating manually: {sum_e}")
                                content_to_save = content_to_save[:2000] + "\n...[Auto-Truncated]"

                        json_match = re.search(r'\{.*\}', content_to_save, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            new_state = {expert_role: parsed}
                        else:
                            new_state = {expert_role: content_to_save}
                    except Exception as e:
                        new_state = {expert_role: content_to_save}
                
                return {"messages": [msg], "history_states": new_state}
            return node_func

        for r_num, round_info in enumerate(topology, 1):
            for expert in round_info["experts"]:
                builder.add_node(expert, make_node(expert, r_num))
                
        for expert in topology[0]["experts"]:
            builder.add_edge(START, expert)
            
        for i in range(len(topology) - 1):
            curr_experts = topology[i]["experts"]
            next_experts = topology[i+1]["experts"]
            for curr_ex in curr_experts:
                for next_ex in next_experts:
                    builder.add_edge(curr_ex, next_ex)
                    
        for expert in topology[-1]["experts"]:
            builder.add_edge(expert, END)
            
        graph = builder.compile()
        initial_state = {"messages": [], "history_states": {}}
        
        try:
            result_state = await graph.ainvoke(initial_state)
            return result_state["messages"]
        except Exception as e:
            print(f"[DiscussionService] Error in LangGraph execution: {e}")
            raise

    async def _call_expert(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: Dict[str, Any], language: str, job_id: str = "temp_job_id", prompt_version_id: str = "v1", model: str = None, search_results: Dict[str, Any] = None, market: str = "us", on_progress: Optional[callable] = None, round_num: int = 1, total_rounds: int = 1, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Assembles prompt and calls the LLM for a single expert role.
        """
        # 1. Fetch Template
        prompt_name = role.lower().replace(" ", "_")
        try:
            prompt_data = prompt_runtime.get_prompt(prompt_name, version="v1", language=language)
            template = prompt_data["template"]
            pv_id = prompt_data.get("version", "v1")
        except:
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
        name_lower = f"{symbol} {name}".lower()
        if any(keyword in name_lower for keyword in ["lithium", "锂", "battery", "电池", "ev", "电动车"]):
             commodity_data = await macro_service.get_commodity_prices(["Lithium Carbonate"])
        elif any(keyword in name_lower for keyword in ["copper", "铜", "gold", "金", "mining", "矿"]):
             commodity_data = await macro_service.get_commodity_prices(["Copper", "Gold"])
        elif any(keyword in name_lower for keyword in ["铝", "aluminum", "alumin", "bauxite", "铝土"]):
             commodity_data = await macro_service.get_commodity_prices(["Aluminum", "Alumina"])
        elif any(keyword in name_lower for keyword in ["能源", "energy", "煤", "coal", "烯烃", "olefin", "化工", "chemical", "石化", "petro", "宝丰"]):
             commodity_data = await macro_service.get_commodity_prices(["Crude Oil", "Methanol", "Polypropylene", "LLDPE"])
             # Also get Brent oil price (in USD) for international benchmark
             brent = await macro_service.get_brent_oil_price()
             if brent:
                 commodity_data["Brent Crude Oil (USD)"] = brent
        
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

        # 4.6 Get Industry Peer Data (for Fundamental Analyst when API lacks peer comparison)
        peer_data = {}
        if role == "Fundamental Analyst":
            try:
                from .search_service import search_service
                market_name = snapshot.get("quote", {}).get("name", name)
                query = f"{market_name} {symbol} industry average PE PB ROE valuation comparison"
                search_res = await search_service.quick_search(query)
                if search_res:
                    peer_data = {"IndustryPeerSearch": search_res}
            except Exception as e:
                print(f"Industry peer search failed: {e}")

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
        prompt = self._assemble_prompt(role, symbol, name, snapshot, processed_history, template, brain_context, language, macro_data, commodity_data, peer_data, has_search_tools=has_search_tools, search_enrichment=search_enrichment, use_native_tools=use_native_tools, macro_indicators=macro_indicators, sentiment_data=sentiment_data, market=market, macro_regime_text=macro_regime_text)
        
        # 7. Call LLM (with tool-calling loop for models without native search)
        start_time = datetime.now()
        base_count = self._cumulative_count  # snapshot before this expert
        def _on_chunk(count):
            if on_progress:
                total = base_count + count
                self._cumulative_count = total
                experts_str = role # just the current expert name
                on_progress(round_num, total_rounds, f"Round {round_num}: {experts_str}", count=total)

        # Determine cache key to save tokens
        cache_key = f"{role}_{symbol}_{'final' if round_num == total_rounds else 'inter'}_{language}"

        if has_search_tools:
            # Gemini has native Google Search — use standard call (tools handled by model)
            content = await llm_gateway.generate_content(prompt, model=model, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None, cache_key=cache_key, prompt_version_id=pv_id)
        else:
            # No artificial limit on tool rounds — let the model decide when it has enough data
            effective_max_rounds = 20
            # Other models — use tool-calling loop (web_search, news_search, knowledge_search)
            try:
                content = await llm_gateway.generate_with_tools(prompt, model=model, role=role, max_tool_rounds=effective_max_rounds, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None, cache_key=cache_key, prompt_version_id=pv_id)
            except Exception as e:
                error_msg = str(e)
                if "402" in error_msg or "Insufficient Balance" in error_msg:
                    if on_progress:
                        on_progress(round_num, total_rounds, f"⚠️ API 余额不足 — {role} 生成中断", error_type="insufficient_balance")
                    content = ""
                else:
                    raise
        latency = (datetime.now() - start_time).total_seconds() * 1000

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
                deepseek_api_key=config.get("deepseekApiKey") if config else None
            )
            return summary.strip()
        except Exception as e:
            print(f"Failed to summarize expert {role}: {e}")
            return text[:800] + "... [truncated]"

    def _assemble_prompt(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: Dict[str, Any], template: str, brain_ctx: Dict[str, Any], language: str, macro_data: Dict[str, Any] = None, commodity_data: Dict[str, Any] = None, peer_data: Dict[str, Any] = None, has_search_tools: bool = False, search_enrichment: Dict[str, Any] = None, use_native_tools: bool = False, macro_indicators: Dict[str, Any] = None, sentiment_data: Dict[str, Any] = None, market: str = "us", macro_regime_text: str = "") -> str:
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
            "Conservative Risk Analyst", "Neutral Risk Analyst"
        )

        quote = snapshot.get("quote", {})
        valuation = snapshot.get("valuation", {})
        financials = snapshot.get("financials", {})
        indicators = snapshot.get("indicators", {})

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
            except: return str(v)

        enrichment_text = ""
        if search_enrichment:
            from .expert_tools import search_toolkit
            enrichment_text = search_toolkit.format_enrichment(search_enrichment, language=language)

        tool_descriptions = ""
        if has_search_tools and not use_native_tools:
            from .expert_tools import format_tool_descriptions
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
            "fmt_num": fmt_num,
            "valuation_guidance": valuation_guidance,
        }

        # Render Jinja template
        prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
        env = Environment(loader=FileSystemLoader(prompts_dir))
        jinja_template = env.get_template("base_prompt.jinja")
        
        return jinja_template.render(**context)

    def _extract_confidence(self, analysis: str) -> float:
        import re
        import json
        
        # Match patterns like: 置信度[：:]\s*(0\.\d+|\d+%)
        match_zh = re.search(r'(?:置信度|可信度)[：:\s]*([0-9]+(?:\.[0-9]+)?)(%)?', analysis)
        if match_zh:
            val = match_zh.group(1)
            is_pct = match_zh.group(2) is not None
            try:
                val_f = float(val)
                if is_pct:
                    return val_f / 100.0
                if val_f > 1.0:
                    return val_f / 100.0 if val_f <= 100 else 0.5
                return val_f
            except ValueError:
                pass
                
        match_en = re.search(r'(?:confidence score|confidence)[：:\s]*([0-9]+(?:\.[0-9]+)?)(%)?', analysis, re.IGNORECASE)
        if match_en:
            val = match_en.group(1)
            is_pct = match_en.group(2) is not None
            try:
                val_f = float(val)
                if is_pct:
                    return val_f / 100.0
                if val_f > 1.0:
                    return val_f / 100.0 if val_f <= 100 else 0.5
                return val_f
            except ValueError:
                pass
                
        try:
            json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                if "confidence_score" in data:
                    return float(data["confidence_score"])
                if "confidence" in data:
                    val = data["confidence"]
                    if isinstance(val, (int, float)):
                        return float(val) / 100.0 if val > 1.0 else float(val)
        except Exception:
            pass
            
        return 0.75  # Default confidence

import json
discussion_service = DiscussionService()
