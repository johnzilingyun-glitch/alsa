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

class DiscussionService:
    def __init__(self):
        pass

    def build_topology(self, level: str, asset_type: str = "equity") -> List[Dict[str, Any]]:
        if level == "sector":
            template = SECTOR_TOPOLOGY
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
                    try:
                        import json, re
                        content = msg["content"]
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            new_state = {expert_role: parsed}
                        else:
                            new_state = {expert_role: content}
                    except Exception as e:
                        new_state = {expert_role: msg["content"]}
                
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
        except:
            # Fallback to simple instruction if prompt not found in DB
            template = f"You are a {role}. Provide professional institutional research analysis for {symbol}."

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
            valuation = snapshot.get("valuation", {})
            if valuation.get("pe") is None or valuation.get("pb") is None:
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
            default_provider = os.getenv("DEFAULT_LLM_PROVIDER", "gemini").lower()
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
        
        # 6. Assemble Prompt (with search capability flag)
        prompt = self._assemble_prompt(role, symbol, name, snapshot, history, template, brain_context, language, macro_data, commodity_data, peer_data, has_search_tools=has_search_tools, search_enrichment=search_enrichment, use_native_tools=use_native_tools, macro_indicators=macro_indicators, sentiment_data=sentiment_data, market=market, macro_regime_text=macro_regime_text)
        
        # 7. Call LLM (with tool-calling loop for models without native search)
        start_time = datetime.now()
        base_count = self._cumulative_count  # snapshot before this expert
        def _on_chunk(count):
            if on_progress:
                total = base_count + count
                self._cumulative_count = total
                experts_str = role # just the current expert name
                on_progress(round_num, total_rounds, f"Round {round_num}: {experts_str}", count=total)

        if has_search_tools:
            # Gemini has native Google Search — use standard call (tools handled by model)
            content = await llm_gateway.generate_content(prompt, model=model, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None)
        else:
            # No artificial limit on tool rounds — let the model decide when it has enough data
            effective_max_rounds = 20
            # Other models — use tool-calling loop (web_search, news_search, knowledge_search)
            try:
                content = await llm_gateway.generate_with_tools(prompt, model=model, role=role, max_tool_rounds=effective_max_rounds, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None)
            except Exception as e:
                error_msg = str(e)
                if "402" in error_msg or "Insufficient Balance" in error_msg:
                    if on_progress:
                        on_progress(round_num, total_rounds, f"⚠️ API 余额不足 — {role} 生成中断", error_type="insufficient_balance")
                    content = ""
                else:
                    raise
        latency = (datetime.now() - start_time).total_seconds() * 1000

        # 8. Record Metrics
        prompt_runtime.record_run({
            "job_id": "temp_job_id", # 需要从 snapshot 或其他上下文获取
            "prompt_version_id": "v1", # 需要从 registry 获取
            "model": model,
            "provider": "gemini" if "gemini" in model else "deepseek",
            "input_tokens": len(prompt) // 4,
            "output_tokens": len(content) // 4,
            "latency_ms": int(latency)
        })

        return {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }

    def _assemble_prompt(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: Dict[str, Any], template: str, brain_ctx: Dict[str, Any], language: str, macro_data: Dict[str, Any] = None, commodity_data: Dict[str, Any] = None, peer_data: Dict[str, Any] = None, has_search_tools: bool = False, search_enrichment: Dict[str, Any] = None, use_native_tools: bool = False, macro_indicators: Dict[str, Any] = None, sentiment_data: Dict[str, Any] = None, market: str = "us", macro_regime_text: str = "") -> str:
        is_zh = language == "zh-CN"
        
        sections = []
        sections.append(f"Role: {role}")

        # Institutional analyst system directive (anti-hallucination + tool policy)
        sections.append("\n--- SYSTEM DIRECTIVE ---")
        if is_zh:
            sections.append(
                "You are an institutional-grade AI analyst operating inside a multi-agent research system.\n"
                "⚠️ LANGUAGE MANDATE: 你的全部输出内容必须使用**简体中文**。包括分析正文、JSON字段值、表格内容、结论等一切文本。"
                "严禁使用英文输出分析内容（专有名词、指标缩写如PE/ROE/MACD、工具调用格式除外）。"
                "违反语言要求的输出将被系统判定为无效并丢弃。\n"
                "PRIMARY DIRECTIVE: You MUST NEVER fabricate financial data, news, metrics, citations, filings, "
                "market information, timestamps, prices, or analyst opinions.\n"
                "If required information is missing, incomplete, outdated, or uncertain, you MUST use available tools before continuing.\n"
                "If tools fail or data cannot be verified, output UNKNOWN and explain why.\n"
                "Never say 'based on latest information' or 'current data suggests' unless tools were actually used.\n"
                "Every conclusion must include: evidence, confidence (HIGH/MEDIUM/LOW), risks, missing information."
            )
        else:
            sections.append(
                "You are an institutional-grade AI analyst operating inside a multi-agent research system.\n"
                "PRIMARY DIRECTIVE: You MUST NEVER fabricate financial data, news, metrics, citations, filings, "
                "market information, timestamps, prices, or analyst opinions.\n"
                "If required information is missing, incomplete, outdated, or uncertain, you MUST use available tools before continuing.\n"
                "If tools fail or data cannot be verified, output UNKNOWN and explain why.\n"
                "Never say 'based on latest information' or 'current data suggests' unless tools were actually used.\n"
                "Every conclusion must include: evidence, confidence (HIGH/MEDIUM/LOW), risks, missing information."
            )

        sections.append("\n--- SYSTEM INSTRUCTIONS ---")
        sections.append(template)

        # Depth & originality requirements (injected for ALL roles — critical for quality)
        sections.append("\n--- [MANDATORY] DEPTH & ORIGINALITY REQUIREMENTS ---")
        sections.append(
            "1. **禁止复读**: 严禁简单重复前序专家的观点。如果你同意某人，必须提供新的证据或更深的量化推导。\n"
            "2. **深度分析**: 你的分析必须极尽详实，严禁敷衍。建议 400-800 字。\n"
            "3. **数据驱动**: 每一项结论都必须对应具体的数值或分析。禁止纯定性描述。\n"
            "4. **非共识洞察**: 识别并明确指出讨论中的逻辑矛盾或被忽视的关键变量。"
            if is_zh else
            "1. **No Repetition**: Strictly prohibited from simply repeating previous experts' points. Provide NEW evidence or deeper quantitative analysis.\n"
            "2. **Exhaustive Analysis**: Your analysis must be extremely detailed. Suggested 400-800 words.\n"
            "3. **Data-Driven**: Every conclusion must map to specific values or evidence. No hand-waving.\n"
            "4. **Contrarian Insight**: Identify logical contradictions or overlooked variables in the discussion."
        )
        
        sections.append("\n--- [MANDATORY] OUTPUT FORMAT & DISCIPLINE ---")
        is_final_round = role in ("Chief Strategist", "Sector Chief Strategist")
        is_sector_intermediate = role in ("Sector Macro Strategist", "Sector Stock Screener", "Serenity Alpha Analyst", "Sector Risk Auditor")

        if is_sector_intermediate:
            # Sector intermediate experts output full markdown — their content is rendered directly in the HTML report
            sections.append(
                "1. **专业Markdown输出**: 你的输出将直接展示在投资报告中。请使用标准 Markdown 排版（标题、表格、列表、加粗等），输出面向投资者的专业分析内容。\n"
                "   - 主标题推荐使用 Emoji 序号标号（如 1️⃣, 2️⃣ 等）增加活泼感。\n"
                "   - 善用 Markdown 表格展示关键数据对比。\n"
                "   - 严禁输出 JSON 格式。严禁输出工具调用计划或内部推理过程。\n"
                "2. **单次输出**: 在所有必要的工具调用结束后，只输出一次完整分析内容。\n"
                if is_zh else
                "1. **Professional Markdown Output**: Your output will be rendered directly in the investment report. Use standard Markdown formatting (headers, tables, lists, bold, etc.) for professional investor-facing analysis.\n"
                "   - Use Emoji numbers (1️⃣, 2️⃣) for main section headers.\n"
                "   - Use Markdown tables for key data comparisons.\n"
                "   - Do NOT output JSON. Do NOT output tool plans or internal reasoning.\n"
                "2. **Single Pass**: Output only the final analysis after all necessary tools are used.\n"
            )
        elif not is_final_round:
            sections.append(
                "1. **中间态结构化输出 (Intermediate State)**: 作为非最终报告编撰者，你必须输出标准的 JSON 格式。\n"
                "   请输出形如 `{\"core_thesis\": \"...\", \"key_metrics_extracted\": [\"...\"], \"risks\": [\"...\"], \"rating\": \"...\"}` 的 JSON 对象。\n"
                "   严禁在 JSON 之外输出任何多余内容，确保其他分析师可以完美解析该 JSON。\n"
                "2. **单次输出**: 在所有必要的工具调用结束后，只输出一次 JSON。\n"
                if is_zh else
                "1. **Structured Intermediate State**: As a non-final analyst, you MUST output a standard JSON object.\n"
                "   Output format: `{\"core_thesis\": \"...\", \"key_metrics_extracted\": [\"...\"], \"risks\": [\"...\"], \"rating\": \"...\"}`.\n"
                "   Do NOT output anything outside the JSON.\n"
                "2. **Single Pass**: Output only the JSON after all necessary tools are used.\n"
            )
        else:
            sections.append(
                "1. **最终输出要求**: 你的输出必须100%是面向投资者的专业分析内容。严禁包含工具调用计划（如'让我调用XX'）、内部推理过程、工具返回结果的元描述、或任何面向系统而非读者的过渡语。\n"
                "2. **活泼的排版**: 强制使用标准 Markdown 语法排版。为了让报告看起来更生动，主标题推荐使用 Emoji 序号标号（如 1️⃣, 2️⃣ 等），增加活泼感。\n"
                "3. **单次输出**: 在所有必要的工具调用结束后，只输出一次最终完整报告，删除任何中间草稿。\n"
                if is_zh else
                "1. **Final Output Rule**: Your output MUST be 100% professional analysis for investors. NO tool plans ('I will now call...'), internal reasoning, meta-descriptions of tool results, or transitional phrases.\n"
                "2. **Lively Formatting**: Mandatory use of standard Markdown. To make the report more engaging, it is recommended to use Emoji numbers (e.g., 1️⃣, 2️⃣) for main section headers.\n"
                "3. **Single Pass**: Output only the final comprehensive report after all necessary tools are used. Delete intermediate drafts.\n"
            )
        
        sections.append("\n--- [API] MACRO & COMMODITY DATA ---")
        sections.append("以下数据来自权威数据源 (CFETS/期货交易所/Sina Finance/yfinance)，为辅助参考数据。")
        if macro_data:
            # Prominently display FX rate at the top
            fx_rate = macro_data.get("USD/CNY")
            fx_source = macro_data.get("Source", "")
            fx_date = macro_data.get("Date", "")
            if fx_rate is not None:
                sections.append(f"★ 实时汇率 USD/CNY: {fx_rate} — {fx_source} [{fx_date}]")
                sections.append(f"  >>> 所有涉及USD↔CNY换算必须使用此汇率 {fx_rate}，严禁使用估算值 <<<")
            for k, v in macro_data.items():
                if k in ("SearchContext", "USD/CNY", "Source", "Date", "Note"):
                    continue
                elif isinstance(v, dict):
                    sections.append(f"{k}: {v.get('price', v.get('USD/CNY', 'N/A'))} ({v.get('unit', '')}) — {v.get('source', '')} [{v.get('date', '')}]")
                    if v.get("error"):
                        sections.append(f"  ⚠ {v['error']}")
                else:
                    sections.append(f"{k}: {v}")

        if commodity_data:
            sections.append("--- [API] 大宗商品实时报价 (权威数据源，优先级高于搜索结果) ---")
            for k, v in commodity_data.items():
                if isinstance(v, dict):
                    if v.get("error"):
                        sections.append(f"⚠ {k}: 数据获取失败 — {v['error']}")
                        sections.append(f"   >>> 严禁使用训练数据中的{k}价格。必须标注'数据缺失'。<<<")
                    elif v.get("price") is not None:
                        sections.append(f"★ {k}: {v['price']} {v.get('unit', '')} — {v.get('source', '')} [{v.get('date', '')}]")
                        sections.append(f"  >>> 此为交易所实时报价，比搜索结果更准确。分析{k}影响时必须使用此价格 {v['price']}，严禁使用搜索到的过期价格 <<<")
                    else:
                        sections.append(f"⚠ {k}: 暂无权威报价")
                elif isinstance(v, str):
                    sections.append(f"{k}: {v}")
                else:
                    sections.append(str(v))

        if not macro_data and not commodity_data:
            sections.append("⚠ 宏观与商品数据暂不可用。请仅基于 [API DATA / MARKET SNAPSHOT] 进行分析。")
            sections.append("⚠ 严禁使用训练数据中的大宗商品价格（如WTI原油、铜、锂等）。若API未提供，必须标注'数据缺失'而非编造数值。")

        # Inject macro economic indicators (M2, LPR, Fed Rate)
        if macro_indicators:
            sections.append("\n--- [API] KEY MACRO INDICATORS ---")
            sections.append("以下为权威宏观经济指标，来自央行/官方数据源。")
            m2 = macro_indicators.get("M2", {})
            if m2.get("value") is not None:
                sections.append(f"中国M2货币供应量: {m2.get('value')} {m2.get('unit', '')} (同比增长: {m2.get('yoy', 'N/A')}) — {m2.get('source', '')} [{m2.get('date', '')}]")
            elif m2.get("error"):
                sections.append(f"⚠ 中国M2: {m2['error']}")
            
            lpr = macro_indicators.get("LPR", {})
            if lpr.get("1y") is not None:
                sections.append(f"LPR利率: 1年期={lpr.get('1y')}% | 5年期={lpr.get('5y', 'N/A')}% — {lpr.get('source', '')} [{lpr.get('date', '')}]")
            elif lpr.get("error"):
                sections.append(f"⚠ LPR: {lpr['error']}")
            
            fed = macro_indicators.get("FedRate", {})
            if fed.get("rate") is not None:
                sections.append(f"美联储联邦基金利率: {fed.get('rate')}% — {fed.get('source', '')} [{fed.get('date', '')}]")
            elif fed.get("error"):
                sections.append(f"⚠ 美联储利率: {fed['error']}")

        # Macro Regime cross-asset analysis (for Risk Manager, Chief Strategist, Macro Hedge Titan)
        if macro_regime_text:
            sections.append(f"\n--- [API] MACRO REGIME DETECTION (跨资产体制分析) ---")
            sections.append(macro_regime_text)

        # Industry peer search data (when API lacks industry comparison)
        if peer_data and peer_data.get("IndustryPeerSearch"):
            sections.append("\n--- [WEB SEARCH] INDUSTRY PEER DATA (Supplementary) ---")
            sections.append("以下为行业对标搜索数据，供补充参考。请注意这是搜索引擎结果，需自行判断可靠性。")
            sections.append(peer_data["IndustryPeerSearch"])

        # Sentiment data (for Sentiment Analyst)
        if sentiment_data:
            sections.append("\n--- [API] SENTIMENT DATA (权威数据源) ---")
            sections.append("以下为实时情绪数据，来自AkShare API + 论坛抓取。优先使用这些数据，不要编造。")

            # Northbound flow
            nb = sentiment_data.get("northbound_flow", {})
            if nb.get("data"):
                sections.append("\n**陆股通(北向资金)持股变化:**")
                sections.append(f"5日净增持资金: {nb.get('five_day_net_inflow', 'N/A')} 元 ({nb.get('five_day_trend', 'N/A')})")
                latest = nb.get("latest", {})
                if latest:
                    sections.append(f"最新日期: {latest.get('date', '')} | 持股占A股比: {latest.get('pct_of_float', '')}%")
                    sections.append(f"当日增持股数: {latest.get('daily_change_shares', '')} | 增持资金: {latest.get('daily_change_value', '')}")
                # Show last 5 days
                for rec in nb.get("data", [])[-5:]:
                    sections.append(f"  {rec.get('date', '')} | 增持: {rec.get('daily_change_shares', '')}股 | {rec.get('daily_change_value', '')}元")
            elif nb.get("error"):
                sections.append(f"⚠ 陆股通: {nb['error']}")

            # Sentiment score
            score = sentiment_data.get("sentiment_score", {})
            score_data = score.get("data", {})
            if score_data:
                sections.append("\n**东方财富综合评分:**")
                sections.append(f"综合得分: {score_data.get('composite_score', 'N/A')} | 排名: {score_data.get('ranking', 'N/A')} (↑{score_data.get('ranking_change', 'N/A')})")
                sections.append(f"机构参与度: {score_data.get('institutional_participation', 'N/A')} | 关注指数: {score_data.get('attention_index', 'N/A')}")
                sections.append(f"主力成本: {score_data.get('main_cost', 'N/A')} | 换手率: {score_data.get('turnover_rate', 'N/A')}%")
            elif score.get("error"):
                sections.append(f"⚠ 综合评分: {score['error']}")

            # Forum data
            forums = sentiment_data.get("forum_sentiment", {})
            forum_list = forums.get("forums", [])
            if forum_list:
                sections.append("\n**论坛情绪抓取 (实时):**")
                for f in forum_list:
                    sections.append(f"\n[{f.get('source', '')}] ({f.get('url', '')})")
                    sections.append(f"{f.get('content', '无内容')[:1500]}")
            elif forums.get("error"):
                sections.append(f"⚠ 论坛抓取: {forums['error']}")

        # Pre-search enrichment data (role-specific, from SearchToolkit)
        if search_enrichment:
            enrichment_text = search_toolkit.format_enrichment(search_enrichment, language=language)
            if enrichment_text:
                sections.append("\n" + enrichment_text)

        if brain_ctx.get("instructions"):
            sections.append("\n--- EVOLVED GUIDELINES ---")
            sections.append(brain_ctx["instructions"])

        if brain_ctx.get("facts"):
            sections.append("\n--- LONG-TERM MEMORY ---")
            sections.append("\n".join(brain_ctx["facts"]))

        sections.append("\n--- CONTEXT ---")
        sections.append(f"Current Date: {datetime.now().strftime('%Y-%m-%d')}")
        sections.append(f"Target: {symbol} ({name})")

        # --- COMPANY FACTUAL PROFILE (anti-hallucination for identity facts) ---
        sections.append("\n--- [API] COMPANY FACTUAL PROFILE (严禁编造以下事实) ---")
        profile_financials = snapshot.get("financials", {})
        profile_valuation = snapshot.get("valuation", {})
        cross_listing = snapshot.get("crossListing")
        
        # Determine exchange display
        if market == "A-Share":
            exchange_display = "上海证券交易所 (SSE)" if symbol.startswith("6") else "深圳证券交易所 (SZSE)"
            full_code = f"{symbol}.SS" if symbol.startswith("6") else f"{symbol}.SZ"
        elif market == "HK-Share":
            exchange_display = "香港交易所 (HKEX)"
            full_code = f"{symbol}.HK"
        else:
            exchange_display = profile_financials.get("exchange") or "N/A"
            full_code = symbol
        
        long_name = profile_financials.get("longName") or profile_valuation.get("股票简称") or name
        industry = profile_financials.get("industry") or profile_valuation.get("行业") or "N/A"
        sector = profile_financials.get("sector") or "N/A"
        listing_date = profile_financials.get("listingDate") or profile_valuation.get("上市时间") or "N/A"
        biz_summary = profile_financials.get("longBusinessSummary") or ""
        
        sections.append(f"- 公司全称: {long_name}")
        sections.append(f"- 股票代码: {full_code}")
        sections.append(f"- 上市交易所: {exchange_display}")
        sections.append(f"- 行业: {industry}")
        if sector != "N/A":
            sections.append(f"- 板块: {sector}")
        if listing_date != "N/A":
            sections.append(f"- 上市时间: {listing_date}")
        if biz_summary:
            sections.append(f"- 主营业务: {biz_summary[:300]}")
        
        # Cross-listing / dual-listing facts
        if cross_listing:
            sections.append(f"- ⚠ 跨市场上市: {cross_listing['type']} 双重上市，H股代码 {cross_listing['symbol']}（{cross_listing['name']}）")
        elif market == "A-Share":
            sections.append(f"- 跨市场: 该股票未在港交所双重上市（仅A股）")
        
        sections.append("⚠ 以上公司身份信息来自API，属于不可更改的事实。严禁基于训练数据记忆编造或修改上述事实（如交易所、行业分类、上市状态、跨市场信息等）。")

        # Structured Market Data (P2-11: replace raw JSON dump with structured format)
        sections.append("\n--- [API DATA / MARKET SNAPSHOT] ---")

        # Sector constituent stocks with REAL-TIME prices (for sector analysis)
        sector_stocks = snapshot.get("sector_stocks", [])
        if sector_stocks:
            sections.append("\n--- [API] 板块成分股实时行情 (AkShare 权威数据，优先级最高) ---")
            sections.append(f"⚠ 以下为 {name}板块 TOP {len(sector_stocks)} 成分股的**实时价格**，来自交易所权威数据源。")
            sections.append(">>> 严禁使用训练数据中的股票价格。推荐个股时，当前价必须引用下表中的价格。如果推荐的股票不在下表中，必须使用 financial_data 工具获取真实价格。 <<<")
            sections.append("")
            sections.append("| 代码 | 名称 | 最新价(元) | 涨跌幅(%) | PE(动) | PB | 总市值(亿) | 换手率(%) |")
            sections.append("|------|------|-----------|----------|--------|------|----------|----------|")
            for s in sector_stocks:
                sections.append(
                    f"| {s.get('code', '')} "
                    f"| {s.get('name', '')} "
                    f"| {s.get('price', 'N/A')} "
                    f"| {s.get('change_pct', 'N/A')} "
                    f"| {s.get('pe', 'N/A')} "
                    f"| {s.get('pb', 'N/A')} "
                    f"| {s.get('market_cap_yi', 'N/A')} "
                    f"| {s.get('turnover_pct', 'N/A')} |"
                )
            sections.append("")
            sections.append("⚠ 以上价格为交易所实时数据。你的推荐表格中的'当前价'列必须使用这些价格。如果某只推荐股不在上表中，你必须使用 `financial_data` 工具查询其真实价格，严禁编造。")
            sections.append("")

        quote = snapshot.get("quote", {})
        valuation = snapshot.get("valuation", {})
        financials = snapshot.get("financials", {})
        indicators = snapshot.get("indicators", {})

        # Helper: read from multiple dicts/keys with fallbacks
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
        currency_note = ""
        if fin_currency != "N/A" and listing_currency != "N/A" and fin_currency != listing_currency:
            currency_note = f" (注意: 上市货币={listing_currency}, 报表货币={fin_currency}, 现金流/营收等绝对值单位为{fin_currency})"

        sections.append(f"- 当前价格: {get_val('price', 'currentPrice')} {listing_currency}")
        sections.append(f"- 涨跌幅: {get_val('changePercent')}%")
        sections.append(f"- 市值: {get_val('marketCap')}{currency_note}")
        sections.append(f"- PE(TTM): {get_val('trailingPE', 'pe')} | Forward PE: {get_val('forwardPE')} | PB: {get_val('priceToBook', 'pb')} | PS: {get_val('priceToSales')}")
        sections.append(f"- PEG: {get_val('pegRatio')} | EV/EBITDA: {get_val('enterpriseToEbitda')} | EV: {get_val('enterpriseValue')}")
        sections.append(f"- ROE: {get_val('returnOnEquity', 'roe')} | ROA: {get_val('returnOnAssets', 'roa')}")
        sections.append(f"- 毛利率: {get_val('grossMargins', 'grossMargin')} | 营业利润率: {get_val('operatingMargins', 'operatingMargin')} | 净利率: {get_val('profitMargins', 'profitMargin')}")
        sections.append(f"- 营收增速-单季YoY: {get_val('revenueGrowth', 'revenueYoY')} | 营收增速-全年YoY: {get_val('revenueYoY_annual')} | 净利润增速 (YoY): {get_val('earningsGrowth', 'netProfitYoY', 'netProfitGrowth')}")
        sections.append(f"- 资产负债率(D/E): {get_val('debtToEquity', 'debtRatio')} | 流动比率: {get_val('currentRatio')} | 速动比率: {get_val('quickRatio')}")
        sections.append(f"- 经营现金流(TTM): {get_val('operatingCashflow')} | 自由现金流(TTM): {get_val('freeCashflow')} | CAPEX: {get_val('capitalExpenditure')}")
        sections.append(f"- 总现金(含短投): {get_val('totalCash')} | 总有息负债: {get_val('totalDebt')} | 净现金(=总现金-总负债): {get_val('netCash')}")
        sections.append(f"- 每股净现金({get_val('financialCurrency')}): {get_val('netCashPerShare')} | 流通股数: {get_val('sharesOutstanding')}")
        sections.append(f"- EPS(TTM): {get_val('eps', 'trailingEps')} | 股息率: {get_val('dividendYield')} | 分红率: {get_val('payoutRatio')}")
        sections.append(f"- 内部人持股(ADS口径): {get_val('heldPercentInsiders')} | 机构持股(ADS口径): {get_val('heldPercentInstitutions')}")
        sections.append(f"- 52周高: {get_val('fiftyTwoWeekHigh')} | 52周低: {get_val('fiftyTwoWeekLow')}")
        sections.append(f"- 营收3年CAGR: {get_val('revenueCagr3y')} | 净利润3年CAGR: {get_val('incomeCagr3y')}")

        # --- Quarterly Financial History Table ---
        quarterly_history = financials.get("quarterlyHistory", [])
        if quarterly_history and len(quarterly_history) >= 2:
            sections.append("\n--- [API] 季度财务数据对比 (权威数据源，无需搜索) ---")
            if market == "A-Share":
                # A-Share format from stock_financial_abstract_ths
                sections.append("以下为最近各报告期的核心财务指标，已由API直接提供。")
                # Compute estimated PE/PB at each quarter-end using current price as approximation
                current_price = get_val('price', 'currentPrice')
                header = "| 报告期 | 营业总收入 | 营收同比 | 净利润 | 净利润同比 | 扣非净利润 | 扣非同比 | 毛利率 | 净利率 | ROE | EPS | BVPS | 每股经营现金流 | 资产负债率 |"
                divider = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
                sections.append(header)
                sections.append(divider)
                for q in quarterly_history:
                    sections.append(
                        f"| {q.get('period', '')} "
                        f"| {q.get('revenue', 'N/A')} "
                        f"| {q.get('revenueYoY', 'N/A')} "
                        f"| {q.get('netProfit', 'N/A')} "
                        f"| {q.get('netProfitYoY', 'N/A')} "
                        f"| {q.get('netProfitDeduct', 'N/A')} "
                        f"| {q.get('netProfitDeductYoY', 'N/A')} "
                        f"| {q.get('grossMargin', 'N/A')} "
                        f"| {q.get('netMargin', 'N/A')} "
                        f"| {q.get('roe', 'N/A')} "
                        f"| {q.get('eps', 'N/A')} "
                        f"| {q.get('bvps', 'N/A')} "
                        f"| {q.get('ocfPerShare', 'N/A')} "
                        f"| {q.get('debtRatio', 'N/A')} |"
                    )
                # Add PE/PB estimation guidance
                if current_price and current_price != "N/A":
                    try:
                        price_f = float(current_price)
                        sections.append(f"\n**估值参考 (基于当前价格 {price_f} {listing_currency}):**")
                        for q in quarterly_history:
                            period = q.get('period', '')
                            bvps = q.get('bvps')
                            eps = q.get('eps')
                            if bvps and eps:
                                try:
                                    bvps_f = float(bvps)
                                    eps_f = float(eps)
                                    pb_est = round(price_f / bvps_f, 2) if bvps_f > 0 else "N/A"
                                    # For annual reports (12-31), compute trailing PE
                                    if period.endswith('12-31') and eps_f > 0:
                                        pe_est = round(price_f / eps_f, 2)
                                        sections.append(f"- {period}: PB≈{pb_est} (当前价/{bvps_f}), PE≈{pe_est} (当前价/年EPS {eps_f})")
                                    else:
                                        sections.append(f"- {period}: PB≈{pb_est} (当前价/{bvps_f})")
                                except (ValueError, ZeroDivisionError):
                                    pass
                    except (ValueError, TypeError):
                        pass
            else:
                # US/HK format from yfinance quarterly_financials
                sections.append("以下为最近各季度的核心财务指标 (yfinance)。")
                header = "| Quarter | Total Revenue | Net Income | Gross Profit | Operating Income | EBITDA |"
                divider = "|---|---|---|---|---|---|"
                sections.append(header)
                sections.append(divider)
                def _fmt_num(v):
                    if v is None: return "N/A"
                    try:
                        v = float(v)
                        if abs(v) >= 1e9: return f"{v/1e9:.2f}B"
                        if abs(v) >= 1e6: return f"{v/1e6:.1f}M"
                        return f"{v:,.0f}"
                    except: return str(v)
                for q in quarterly_history:
                    sections.append(
                        f"| {q.get('period', '')} "
                        f"| {_fmt_num(q.get('Total Revenue'))} "
                        f"| {_fmt_num(q.get('Net Income'))} "
                        f"| {_fmt_num(q.get('Gross Profit'))} "
                        f"| {_fmt_num(q.get('Operating Income'))} "
                        f"| {_fmt_num(q.get('EBITDA'))} |"
                    )
            sections.append("⚠ 以上季度数据来自API，为已审计/已公告数据。严禁使用搜索或训练数据中的数值覆盖。环比变化可由相邻季度数据直接计算。")

        sections.append("")
        sections.append("--- [MANDATORY] DATA VALIDATION WARNINGS ---")
        sections.append(
            "⚠ **数据口径警告（所有专家必读）**:\n"
            "1. **净现金**: 上方'净现金(=总现金-总负债)'已由API直接计算，请直接引用此值。严禁自行推算或使用搜索到的不同口径数据。注意：'总现金'含现金等价物+短期投资，口径偏宽；如需纯现金口径需搜索年报。\n"
            "2. **每股净现金**: 单位为报表货币（见括号标注），ADR股票需要除以汇率才能换算为上市货币。例如CNY口径需÷汇率换算为USD。\n"
            "3. **持股比例**: '内部人持股'和'机构持股'来自yfinance，对于ADR/港股仅反映ADS层面数据，严重低估真实比例。如分析创始人实际持股或全口径机构持仓，必须搜索SEC 20-F/proxy statement或港交所披露。\n"
            "4. **营收增速**: 提供了'单季YoY'和'全年YoY'两个口径。分析增长趋势时应以全年YoY为主，单季YoY受季节性影响大。严禁将单季数据当作全年趋势。\n"
            "5. **自由现金流**: 为TTM(过去12个月)口径，可能包含已过时的季度。如需判断最新趋势，应搜索最近一个季度的FCF数据。\n"
            "6. **EV(企业价值)**: 对于跨币种股票(ADR/港股)，EV已通过实时汇率重新计算: EV = 市值×汇率 + 有息负债 - 总现金。如仍显示N/A则数据暂不可用，严禁自行推算。\n"
            "7. **月度交付量环比**: 季度末月（3/6/9/12月）通常有冲量效应，次月（4/7/10/1月）回调属正常。判断趋势需看同比，不能仅凭环比下滑就断言增长放缓。"
        )
        if fin_currency != "N/A" and listing_currency != "N/A" and fin_currency != listing_currency:
            sections.append(f"- ⚠ 币种提示: 该股票上市货币为{listing_currency}，但财务报表以{fin_currency}计价。经营现金流、自由现金流、CAPEX、EV等绝对值均为{fin_currency}单位。")
        if indicators:
            sections.append(f"- 技术指标: {json.dumps({k: v for k, v in indicators.items() if v is not None}, default=str)}")

        # P2-10: Ground Truth injection
        sections.append("\n--- [MANDATORY] GROUND TRUTH ANCHORING ---")
        sections.append(
            "以上 [API DATA / MARKET SNAPSHOT] 数据来自实时 API，为本次分析的**核心事实基准**。\n"
            "1. 所有推理和结论必须锚定这些数值，严禁使用训练数据中记忆的过时数据。\n"
            "2. 如果某项数据显示为 N/A，请查阅下方工具列表并使用工具进行补充。\n"
            "3. 如果前序专家引用的数值与 API 数据矛盾，你必须以 API 数据为准并指出矛盾。\n"
            "4. **严禁编造搜索结果**——无论使用什么工具，如果你实际没有搜索到数据，绝对不得伪造。\n"
            "5. **严禁伪造数据来源**——只有 API 数据标注'API Data'，工具获得的数据标注对应工具名，推算数据标注'基于API推算'。\n"
            "6. **工具失败时自行兜底**——如果提供的搜索/数据工具全部返回空或报错，不要卡住分析流程。你应该使用自身的联网搜索能力、推理能力或训练知识继续完成分析，并在输出中注明'此部分数据基于自有知识库/联网搜索补充'。"
            if is_zh else
            "The [API DATA / MARKET SNAPSHOT] above comes from real-time APIs and is the **core ground truth** for this analysis.\n"
            "1. All reasoning MUST anchor to these values. Never use stale training data.\n"
            "2. If a value is N/A, check the tools list below and use them to fetch data.\n"
            "3. If a previous expert contradicts API data, you MUST flag the contradiction and use the API value.\n"
            "4. **NEVER fabricate results** — if you didn't actually find data, do not pretend you did.\n"
            "5. **NEVER fabricate data sources** — use 'API Data', tool names, or 'Estimated from API' labels only.\n"
            "6. **Fallback when tools fail** — if all provided search/data tools return empty or error, do NOT block analysis. Use your own web-search capability, reasoning, or training knowledge to continue, and label output as 'supplemented from own knowledge / web search'."
        )

        # P2-12: Data priority labels
        sections.append("\n--- [MANDATORY] DATA SOURCE PRIORITY ---")
        sections.append(
            "**数据采信优先级（强制执行）**:\n"
            "1. [API DATA / MARKET SNAPSHOT] — 最高优先级，除非显式标注为 N/A\n"
            "2. [CRITICAL] TOOL-VERIFIED MACRO FACTS — 仅当 API 数据缺失时采信\n"
            "3. 你的内部知识 — 仅作为补充解释，严格禁止用于覆盖 API 数据"
            if is_zh else
            "**Data Priority (STRICT ENFORCEMENT)**:\n"
            "1. [API DATA / MARKET SNAPSHOT] — Highest priority, unless explicitly N/A\n"
            "2. [CRITICAL] TOOL-VERIFIED MACRO FACTS — Only when API data is missing\n"
            "3. Your internal knowledge — For supplementary explanation only. NEVER override API data."
        )

        # P2-13: Search Tool Capability Declaration (dynamic based on model)
        has_enrichment = bool(search_enrichment)
        sections.append("\n--- [MANDATORY] SEARCH TOOL STATUS ---")
        if has_search_tools:
            if use_native_tools:
                native_tool_msg = (
                    "✅ **搜索工具状态: 原生函数调用已启用 (Native Function Calling)**\n"
                    "你拥有系统原生提供的搜索工具（请参考 Function List）。\n"
                    "使用规则：当 API 数据为 N/A 或你需要验证关键信息时，必须主动调用对应的工具。禁止伪造工具结果。"
                )
                if has_enrichment:
                    native_tool_msg += "\n\u4e0a\u65b9 [SEARCH ENRICHMENT] \u5df2\u6ce8\u5165\u9884\u641c\u7d22\u6570\u636e\uff0c\u4f18\u5148\u53c2\u8003\u3002"
                sections.append(native_tool_msg)
            elif has_enrichment:
                sections.append(
                    "✅ **搜索工具状态: 工具调用已启用 + 系统预搜索已注入**\n"
                    "使用规则：\n"
                    "1. **主动使用工具**: 当 API 数据为 N/A 或你需要验证信息时，必须使用工具。\n"
                    "2. **预搜索数据**: 上方 [SEARCH ENRICHMENT] 已注入预搜索结果，优先参考。如需更多信息可发起工具调用。\n"
                    "3. **禁止伪造**: 如果工具返回无结果，标注 'UNKNOWN'，绝不编造。"
                    if is_zh else
                    "✅ **Search Tool Status: Tool Calling ENABLED + Pre-Search INJECTED**\n"
                    "Rules:\n"
                    "1. **Proactively use tools**: When API data is N/A or you need to verify info, use tools listed below.\n"
                    "2. **Pre-search data**: [SEARCH ENRICHMENT] above has pre-fetched results. Refer to those first.\n"
                    "3. **No fabrication**: If tool returns no results, state 'UNKNOWN'. Never fabricate."
                )
            else:
                sections.append(
                    "✅ **搜索工具状态: 工具调用已启用**\n"
                    "使用规则：\n"
                    "1. **主动使用工具**: 当 API 数据为 N/A 或需要实时数据验证时，你必须使用工具获取数据，严禁猜测。\n"
                    "2. **禁止伪造**: 如果工具返回无结果，标注 'UNKNOWN'，绝不编造。\n"
                    "3. **交叉验证**: 工具数据与 API 数据冲突时，以 API 数据为准。"
                    if is_zh else
                    "✅ **Search Tool Status: Tool Calling ENABLED**\n"
                    "Rules:\n"
                    "1. **Proactively use tools**: When API data is N/A or real-time validation needed, you MUST use tools.\n"
                    "2. **No fabrication**: If tool returns no results, state 'UNKNOWN'. Never fabricate.\n"
                    "3. **Cross-validate**: When tool data conflicts with API data, API takes priority."
                )
            
            if not use_native_tools:
                # Inject text-based tool call format instructions (not needed for native API function calling)
                sections.append("\n" + format_tool_descriptions(role=role, language=language))

        if history:
            sections.append("\\n--- PREVIOUS DISCUSSION (STRUCTURED JSON) ---")
            for agent_role, state_data in history.items():
                if isinstance(state_data, dict):
                    sections.append(f"[{agent_role}]: {json.dumps(state_data, ensure_ascii=False)}")
                else:
                    truncated = str(state_data)[-8000:] if len(str(state_data)) > 8000 else str(state_data)
                    sections.append(f"[{agent_role}]: {truncated}")

        sections.append(f"\nFinal Instruction: Respond in {'Simplified Chinese' if is_zh else 'English'}.")
        
        return "\n".join(sections)

import json
discussion_service = DiscussionService()
