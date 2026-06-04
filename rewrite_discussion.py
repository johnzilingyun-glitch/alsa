import re

with open(r'd:\zily\alsa\alsa\python_service\app\services\discussion_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace run_discussion
run_discussion_new = """    async def run_discussion(self, symbol: str, name: str, snapshot: Dict[str, Any], level: str = "standard", language: str = "zh-CN", model: str = None, on_progress: Optional[callable] = None, job_id: str = "temp_job_id", config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        \"\"\"
        Runs the full expert discussion flow using LangGraph.
        \"\"\"
        topology = self.build_topology(level)
        market = snapshot.get("market", "us")
        self._cumulative_count = 0  # Track total chars across all experts
        
        # Clear tool executor cache from previous jobs
        from .expert_tools import tool_executor
        tool_executor.clear_cache()
        
        # Pre-search enrichment: batch search ONCE before all experts
        search_results = {}
        try:
            from .search_toolkit import search_toolkit
            search_results = await search_toolkit.batch_search(symbol, name, snapshot)
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
            raise"""

run_discussion_pattern = re.compile(r'    async def run_discussion\(self, symbol.*?\n    async def _call_expert', re.DOTALL)
content = run_discussion_pattern.sub(run_discussion_new + '\n\n    async def _call_expert', content)

# Replace _call_expert signature
call_expert_pattern = re.compile(r'async def _call_expert\(self, role: str, symbol: str, name: str, snapshot: Dict\[str, Any\], history: List\[Dict\[str, Any\]\]')
content = call_expert_pattern.sub('async def _call_expert(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: Dict[str, Any]', content)

# Replace _assemble_prompt signature
assemble_prompt_pattern = re.compile(r'def _assemble_prompt\(self, role: str, symbol: str, name: str, snapshot: Dict\[str, Any\], history: List\[Dict\[str, Any\]\]')
content = assemble_prompt_pattern.sub('def _assemble_prompt(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: Dict[str, Any]', content)

# Replace history formatting in _assemble_prompt
history_format_old = r"""        if history:
            sections.append\("\\n--- PREVIOUS DISCUSSION \(STRUCTURED JSON\) ---"\)
            for msg in history:
                # For non-final rounds, history contains JSON state, no need to truncate brutally\.
                # However, to be safe, truncate to 8000 chars to avoid prompt bloat\.
                truncated = msg\['content'\]\[-8000:\] if len\(msg\['content'\]\) > 8000 else msg\['content'\]
                sections.append\(f"\[\{msg\['role'\]\}\]: \{truncated\}"\)"""

history_format_new = """        if history:
            sections.append("\\n--- PREVIOUS DISCUSSION (STRUCTURED JSON) ---")
            import json
            for agent_role, state_data in history.items():
                if isinstance(state_data, dict):
                    sections.append(f"[{agent_role}]: {json.dumps(state_data, ensure_ascii=False)}")
                else:
                    truncated = str(state_data)[-8000:] if len(str(state_data)) > 8000 else str(state_data)
                    sections.append(f"[{agent_role}]: {truncated}")"""

content = re.sub(history_format_old, history_format_new, content)

with open(r'd:\zily\alsa\alsa\python_service\app\services\discussion_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
