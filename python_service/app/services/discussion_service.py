import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from ..prompting.runtime import prompt_runtime
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
    {"round": 9, "experts": ["Soros-style Financial Philosopher", "Growth Visionary", "Macro Hedge Titan", "Value Investing Sage"], "parallel": True},
    {"round": 10, "experts": ["Chief Strategist"], "parallel": False},
]

STANDARD_TOPOLOGY = [
    {"round": 1, "experts": ["Deep Research Specialist"], "parallel": False},
    {"round": 2, "experts": ["Technical Analyst", "Fundamental Analyst"], "parallel": True},
    {"round": 3, "experts": ["Bull Researcher", "Bear Researcher"], "parallel": True},
    {"round": 4, "experts": ["Risk Manager"], "parallel": False},
    {"round": 5, "experts": ["Professional Reviewer"], "parallel": False},
    {"round": 6, "experts": ["Soros-style Financial Philosopher", "Growth Visionary", "Macro Hedge Titan", "Value Investing Sage"], "parallel": True},
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

    async def _call_expert(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: List[Dict[str, Any]], language: str, job_id: str = "temp_job_id", prompt_version_id: str = "v1") -> Dict[str, Any]:
        """
        Assembles prompt and calls the LLM for a single expert role.
        """
        # 1. Fetch Template
        prompt_name = role.lower().replace(" ", "_")
        try:
            prompt_data = prompt_runtime.get_prompt(prompt_name, version="v1")
            template = prompt_data["template"]
        except:
            # Fallback to simple instruction if prompt not found in DB
            template = f"You are a {role}. Provide professional institutional research analysis for {symbol}."

        # 2. Get Brain Context
        brain_context = brain_manager.get_brain_context("default", query=f"{symbol} {name}", role=role.lower())
        
        # 3. Get Macro Data (Exchange Rates, etc.)
        from .macro_service import macro_service
        macro_data = await macro_service.get_latest_fx()

        # 4. Assemble Prompt
        prompt = self._assemble_prompt(role, symbol, name, snapshot, history, template, brain_context, language, macro_data)
        
        # 5. Call LLM
        model = "deepseek-v4-pro"

        start_time = datetime.now()
        content = await llm_gateway.generate_content(prompt, model=model)
        latency = (datetime.now() - start_time).total_seconds() * 1000

        # 5. Record Metrics
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

    def _assemble_prompt(self, role: str, symbol: str, name: str, snapshot: Dict[str, Any], history: List[Dict[str, Any]], template: str, brain_ctx: Dict[str, Any], language: str, macro_data: Dict[str, Any] = None) -> str:
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

        sections.append("\n--- REAL-TIME MACRO DATA ---")
        if macro_data:
            for k, v in macro_data.items():
                sections.append(f"{k}: {v}")
        else:
            sections.append("USD/CNY: 7.24 (Estimated)")

        sections.append("\n--- CONTEXT ---")
        sections.append(f"Current Date: {datetime.now().strftime('%Y-%m-%d')}")
        sections.append(f"Target: {symbol} ({name})")

        # Comprehensive Market Data Context
        market_context = {
            "quote": snapshot.get("quote", {}),
            "indicators": snapshot.get("indicators", {}),
            "financials": snapshot.get("financials", {}),
            "valuation": snapshot.get("valuation", {})
        }
        sections.append("\n--- [API DATA / MARKET SNAPSHOT] ---")
        sections.append(json.dumps(market_context, indent=2, default=str))
        
        if history:
            sections.append("\n--- PREVIOUS DISCUSSION ---")
            for msg in history:
                sections.append(f"[{msg['role']}]: {msg['content'][:1000]}...") # Truncate history for context window

        sections.append(f"\nFinal Instruction: Respond in {'Simplified Chinese' if is_zh else 'English'}.")
        
        return "\n".join(sections)

import json
discussion_service = DiscussionService()
