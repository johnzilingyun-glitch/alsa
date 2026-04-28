import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from ..prompting.registry import prompt_registry
from .llm_gateway import llm_gateway
from .brain_manager import brain_manager

# --- Topologies (Ported from orchestrator.ts) ---

DEEP_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"], "parallel": False},
    {"round": 2, "experts": ["Technical Analyst", "Fundamental Analyst"], "parallel": True},
    {"round": 3, "experts": ["Sentiment Analyst"], "parallel": False},
    {"round": 4, "experts": ["Bull Researcher", "Bear Researcher"], "parallel": True},
    {"round": 5, "experts": ["Aggressive Risk Analyst", "Conservative Risk Analyst", "Neutral Risk Analyst"], "parallel": True},
    {"round": 6, "experts": ["Contrarian Strategist"], "parallel": False},
    {"round": 7, "experts": ["Professional Reviewer"], "parallel": False},
    {"round": 8, "experts": ["Bull Researcher", "Bear Researcher"], "parallel": True},
    {"round": 9, "experts": ["Value Investing Sage", "Growth Visionary", "Macro Hedge Titan"], "parallel": True},
    {"round": 10, "experts": ["Chief Strategist"], "parallel": False},
]

STANDARD_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"], "parallel": False},
    {"round": 2, "experts": ["Technical Analyst", "Fundamental Analyst"], "parallel": True},
    {"round": 3, "experts": ["Bull Researcher", "Bear Researcher"], "parallel": True},
    {"round": 4, "experts": ["Risk Manager"], "parallel": False},
    {"round": 5, "experts": ["Professional Reviewer"], "parallel": False},
    {"round": 6, "experts": ["Value Investing Sage", "Growth Visionary", "Macro Hedge Titan"], "parallel": True},
    {"round": 7, "experts": ["Chief Strategist"], "parallel": False},
]

QUICK_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"], "parallel": False},
    {"round": 2, "experts": ["Risk Manager"], "parallel": False},
    {"round": 3, "experts": ["Chief Strategist"], "parallel": False},
]

class DiscussionService:
    def __init__(self):
        pass

    def build_topology(self, level: str, asset_type: str = "equity") -> List[Dict[str, Any]]:
        if level == "quick":
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

    async def run_discussion(self, symbol: str, name: str, snapshot: Dict[str, Any], level: str = "standard", language: str = "zh-CN") -> List[Dict[str, Any]]:
        """
        Runs the full expert discussion flow.
        """
        topology = self.build_topology(level)
        messages = []
        
        for round_info in topology:
            print(f"Round {round_info['round']}: {', '.join(round_info['experts'])}")
            
            if round_info["parallel"]:
                tasks = [self._call_expert(expert, symbol, name, snapshot, messages, language) for expert in round_info["experts"]]
                results = await asyncio.gather(*tasks)
                messages.extend(results)
            else:
                for expert in round_info["experts"]:
                    result = await self._call_expert(expert, symbol, name, snapshot, messages, language)
                    messages.append(result)
        
        return messages

    async def _call_expert(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: List[Dict[str, Any]], language: str) -> Dict[str, Any]:
        """
        Assembles prompt and calls the LLM for a single expert role.
        """
        # 1. Get Template
        template = prompt_registry.get_template(role, language)
        
        # 2. Get Brain Context (evolved instructions + long-term memory)
        brain_context = brain_manager.get_brain_context("default", query=f"{symbol} {name}", role=role.lower())
        
        # 3. Assemble Prompt (simplified port of promptAssembler.ts)
        prompt = self._assemble_prompt(role, symbol, name, snapshot, history, template, brain_context, language)
        
        # 4. Call LLM
        # Default model logic
        model = "gemini-3.1-flash-lite-preview"
        
        # Expert-specific model selection
        if role == "Deep Research Specialist":
            # DeepSeek V4-Pro (successor to R1) is excellent for initial deep research
            model = "deepseek-v4-pro"
        elif role in ["Chief Strategist", "Risk Manager"]:
            model = "gemini-3.1-pro-preview" 
        elif os.getenv("DEFAULT_LLM_PROVIDER") == "deepseek":
            model = "deepseek-v4-flash"
            
        print(f"Calling expert: {role}...", flush=True)
        content = await llm_gateway.generate_content(prompt, model=model)
        print(f"Expert {role} responded.", flush=True)
        
        return {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }

    def _assemble_prompt(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: List[Dict[str, Any]], template: str, brain_ctx: Dict[str, Any], language: str) -> str:
        is_zh = language == "zh-CN"
        
        sections = []
        sections.append(f"Role: {role}")
        sections.append("\n--- SYSTEM INSTRUCTIONS ---")
        sections.append(template)
        
        if brain_ctx.get("instructions"):
            sections.append("\n--- EVOLVED GUIDELINES ---")
            sections.append(brain_ctx["instructions"])
            
        if brain_ctx.get("facts"):
            sections.append("\n--- LONG-TERM MEMORY ---")
            sections.append("\n".join(brain_ctx["facts"]))

        sections.append("\n--- CONTEXT ---")
        sections.append(f"Current Date: {datetime.now().strftime('%Y-%m-%d')}")
        sections.append(f"Target: {symbol} ({name})")
        sections.append(f"Price Snapshot: {json.dumps(snapshot.get('indicators', {}), indent=2, default=str)}")
        
        if history:
            sections.append("\n--- PREVIOUS DISCUSSION ---")
            for msg in history:
                sections.append(f"[{msg['role']}]: {msg['content'][:1000]}...") # Truncate history for context window

        sections.append(f"\nFinal Instruction: Respond in {'Simplified Chinese' if is_zh else 'English'}.")
        
        return "\n".join(sections)

import json
discussion_service = DiscussionService()
