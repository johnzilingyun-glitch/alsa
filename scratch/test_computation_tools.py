"""Quick test for computation tools end-to-end."""
import asyncio
from python_service.app.services.expert_tools import parse_tool_calls, tool_executor

test_text = """
<tool_call>
tool: dcf_calculator
reason: Calculate MSFT intrinsic value
params: {"fcf_base": 85000, "growth_rates": [0.15, 0.12, 0.10, 0.08, 0.06], "terminal_growth": 0.03, "wacc": 0.09, "shares_outstanding": 7440, "net_debt": -45000, "currency": "USD"}
</tool_call>

<tool_call>
tool: position_sizer
reason: Calculate position for entry at 410
params: {"account_size": 100000, "entry_price": 410, "stop_price": 385, "risk_pct": 1.0, "currency": "USD"}
</tool_call>

<tool_call>
tool: kelly_calculator
reason: Determine optimal position
params: {"win_rate": 0.55, "avg_win": 2.0, "avg_loss": 1.0, "fraction": 0.5}
</tool_call>

<tool_call>
tool: pillar_scorer
reason: Check thesis health
params: {"pillars": [{"name": "Revenue growth", "status": "on_track", "weight": 30, "evidence": "+22% YoY"}, {"name": "Margin expansion", "status": "mixed", "weight": 25, "evidence": "Flat QoQ"}, {"name": "Market share", "status": "on_track", "weight": 20, "evidence": "Gaining"}], "kill_switches": ["Revenue growth"]}
</tool_call>
"""

calls = parse_tool_calls(test_text)
print(f"Parsed {len(calls)} tool calls:")
for c in calls:
    print(f"  - {c['tool']}: {c.get('reason', '')[:50]}")

async def test():
    for call in calls:
        result = await tool_executor.execute(call)
        print(f"\n{'='*60}")
        print(f"=== {call['tool']} ===")
        print(f"{'='*60}")
        print(result)

asyncio.run(test())
