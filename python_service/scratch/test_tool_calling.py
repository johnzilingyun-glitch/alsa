"""
Test the tool-calling pipeline: parse → execute → format.
Run: python scratch/test_tool_calling.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.expert_tools import (
    parse_tool_calls, has_tool_calls, tool_executor,
    format_tool_descriptions, TOOL_DEFINITIONS
)

def test_parse():
    print("=" * 60)
    print("TEST 1: Parse tool calls from LLM output")
    print("=" * 60)
    
    sample = """
    Based on the API data, NVO's trailing PE is 25.3. However, I need to check the latest earnings guidance.
    
    <tool_call>
    tool: web_search
    reason: Need latest Q1 2025 earnings results
    query: Novo Nordisk NVO Q1 2025 earnings revenue profit
    </tool_call>
    
    I also want to check recent news:
    
    <tool_call>
    tool: news_search
    reason: Check for regulatory updates
    query: Novo Nordisk FDA regulatory update 2025
    </tool_call>
    """
    
    assert has_tool_calls(sample), "Should detect tool calls"
    calls = parse_tool_calls(sample)
    assert len(calls) == 2, f"Expected 2 tool calls, got {len(calls)}"
    
    print(f"  Parsed {len(calls)} tool calls:")
    for tc in calls:
        print(f"    {tc['tool']}: {tc['query']}")
        print(f"    Reason: {tc['reason']}")
    
    # Test no tool calls
    assert not has_tool_calls("Just a regular response without tools"), "Should not detect tool calls"
    assert len(parse_tool_calls("No tools here")) == 0, "Should parse 0 calls"
    
    print("  ✅ Parse tests passed")

def test_parse_deep_scrape():
    print("\n" + "=" * 60)
    print("TEST 1b: Parse deep_scrape tool calls")
    print("=" * 60)
    
    sample = """
    I found a relevant article. Let me extract the full content.
    
    <tool_call>
    tool: deep_scrape
    reason: Need full earnings details from this article
    url: https://seekingalpha.com/article/nvo-earnings
    query: NVO Q1 2025 revenue profit EPS guidance
    </tool_call>
    
    And also search for more:
    
    <tool_call>
    tool: web_search
    reason: Need analyst consensus
    query: NVO analyst price target 2025
    </tool_call>
    """
    
    calls = parse_tool_calls(sample)
    assert len(calls) == 2, f"Expected 2 tool calls, got {len(calls)}"
    
    deep = [c for c in calls if c['tool'] == 'deep_scrape']
    assert len(deep) == 1, "Should have 1 deep_scrape call"
    assert deep[0]['url'] == "https://seekingalpha.com/article/nvo-earnings"
    assert deep[0]['query'] == "NVO Q1 2025 revenue profit EPS guidance"
    
    web = [c for c in calls if c['tool'] == 'web_search']
    assert len(web) == 1, "Should have 1 web_search call"
    
    print(f"  Parsed {len(calls)} tool calls:")
    for tc in calls:
        if 'url' in tc:
            print(f"    {tc['tool']}: url={tc['url']}, query={tc['query']}")
        else:
            print(f"    {tc['tool']}: {tc['query']}")
    print("  ✅ deep_scrape parse tests passed")

def test_format():
    print("\n" + "=" * 60)
    print("TEST 2: Format tool descriptions")
    print("=" * 60)
    
    desc = format_tool_descriptions("zh-CN")
    print(f"  Tool descriptions length: {len(desc)} chars")
    assert "web_search" in desc
    assert "news_search" in desc
    assert "knowledge_search" in desc
    assert "deep_scrape" in desc
    assert "<tool_call>" in desc
    print("  ✅ Format test passed")

async def test_execute():
    print("\n" + "=" * 60)
    print("TEST 3: Execute tool calls (live search)")
    print("=" * 60)
    
    # Test web_search
    result = await tool_executor.execute({
        "tool": "web_search",
        "reason": "test",
        "query": "Novo Nordisk NVO stock price 2025"
    })
    print(f"  web_search result length: {len(result)} chars")
    assert "<tool_observation>" in result
    assert "</tool_observation>" in result
    print(f"  First 200 chars: {result[:200]}")
    
    # Test unknown tool
    result = await tool_executor.execute({
        "tool": "unknown_tool",
        "reason": "test",
        "query": "test"
    })
    assert "Unknown tool" in result
    print("  ✅ Unknown tool handled correctly")
    
    # Test empty query
    result = await tool_executor.execute({
        "tool": "web_search",
        "reason": "test",
        "query": ""
    })
    assert "Empty query" in result
    print("  ✅ Empty query handled correctly")
    
    print("  ✅ Execute tests passed")

async def test_deep_scrape():
    print("\n" + "=" * 60)
    print("TEST 3b: Execute deep_scrape (crawl4ai)")
    print("=" * 60)
    
    result = await tool_executor.execute({
        "tool": "deep_scrape",
        "reason": "Need full page content",
        "url": "https://finance.yahoo.com/quote/NVO/",
        "query": "NVO stock price market cap PE ratio"
    })
    print(f"  deep_scrape result length: {len(result)} chars")
    assert "<tool_observation>" in result
    assert "</tool_observation>" in result
    # Show first 500 chars
    print(f"  First 500 chars:\n{result[:500]}")
    
    # Test missing URL
    result = await tool_executor.execute({
        "tool": "deep_scrape",
        "reason": "test",
        "url": "",
        "query": "test"
    })
    assert "requires" in result
    print("  ✅ Missing URL handled correctly")
    
    print("  ✅ deep_scrape tests passed")

async def test_knowledge_search():
    print("\n" + "=" * 60)
    print("TEST 4: Knowledge search (brain manager)")
    print("=" * 60)
    
    result = await tool_executor.execute({
        "tool": "knowledge_search",
        "reason": "Check historical analysis",
        "query": "NVO valuation analysis"
    })
    print(f"  knowledge_search result length: {len(result)} chars")
    print(f"  First 200 chars: {result[:200]}")
    print("  ✅ Knowledge search executed")

if __name__ == "__main__":
    test_parse()
    test_parse_deep_scrape()
    test_format()
    asyncio.run(test_execute())
    asyncio.run(test_deep_scrape())
    asyncio.run(test_knowledge_search())
    print("\n✅ All tool-calling tests passed!")
