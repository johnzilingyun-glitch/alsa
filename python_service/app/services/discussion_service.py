import os
import json
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
        total_rounds = len(topology)
        
        # Pre-search enrichment: batch search ONCE before all experts
        # Report progress during search phase (stays between 30-35%)
        search_results = {}
        try:
            if on_progress:
                on_progress(0, total_rounds, "正在搜索市场数据...")
            # Timeout batch_search at 30s to prevent blocking forever on failing searches
            search_results = await asyncio.wait_for(
                search_toolkit.batch_search(symbol, name, snapshot),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            print("[DiscussionService] Pre-search enrichment TIMED OUT (30s) — continuing without search data")
        except Exception as e:
            print(f"[DiscussionService] Pre-search enrichment failed (non-fatal): {e}")
        
        from typing import TypedDict, Annotated
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

                    # Grounding verification: validate numeric claims against snapshot data
                    try:
                        from .grounding_verifier import grounding_verifier
                        verification = grounding_verifier.verify(content, snapshot)
                        if verification.flagged_count > 0:
                            print(f"[Grounding] {expert_role}: {verification.summary}")
                            content = grounding_verifier.annotate_output(content, verification)
                            msg["content"] = content
                            msg["grounding"] = {
                                "verified": verification.verified_count,
                                "flagged": verification.flagged_count,
                                "total": verification.total_count,
                                "coverage": verification.coverage_score,
                            }
                    except Exception as e:
                        print(f"[Grounding] Verification failed for {expert_role}: {e}")

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
                        import json
                        import re
                        # Summarize long text to prevent context bloat (Phase 4 Fix)
                        content_to_save = content
                        if len(content_to_save) > 2000:
                            print(f"[DiscussionService] Expert '{expert_role}' output exceeds 2000 chars, triggering summarizer...")
                            try:
                                content_to_save = await self._summarize_expert_output(expert_role, content_to_save, model, config)
                            except Exception as sum_e:
                                print(f"[DiscussionService] Summarization failed, truncating manually: {sum_e}")
                                content_to_save = content_to_save[:2000] + "\n...[Auto-Truncated]"

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
            "Conservative Risk Analyst", "Neutral Risk Analyst"
        )
        
        response_schema = None
        if not is_final and not is_sector_intermediate and not is_markdown_intermediate:
            from ..models.schemas import ExpertDiscussionResult
            response_schema = ExpertDiscussionResult

        if has_search_tools:
            # Gemini has native Google Search — use standard call (tools handled by model)
            try:
                content = await llm_gateway.generate_content(prompt, model=model, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None, cache_key=cache_key, prompt_version_id=pv_id, response_schema=response_schema)
            except Exception as e:
                logger.error(f"[DiscussionService] Gemini LLM generation failed for {role}: {e}")
                content = f"{role} 专家暂时无法提供分析。原因: 大语言模型请求异常 ({str(e)[:100]})。请其他专家忽略此错误并根据已有数据自行补全缺失视角的分析逻辑。"
        else:
            # No artificial limit on tool rounds — let the model decide when it has enough data
            effective_max_rounds = 20
            # Other models — use tool-calling loop (web_search, news_search, knowledge_search)
            try:
                content = await agent_orchestrator.generate_with_tools(prompt, model=model, role=role, max_tool_rounds=effective_max_rounds, on_chunk=_on_chunk, gemini_api_key=config.get("geminiApiKey") if config else None, deepseek_api_key=config.get("deepseekApiKey") if config else None, cache_key=cache_key, prompt_version_id=pv_id, response_schema=response_schema)
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

discussion_service = DiscussionService()
