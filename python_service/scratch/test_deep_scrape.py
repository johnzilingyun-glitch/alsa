"""Quick test for optimized deep_scrape with anti-bot config."""
import asyncio
import sys
sys.path.insert(0, '.')
from app.services.expert_tools import tool_executor

async def test():
    # Test with Yahoo Finance - aggressive anti-bot
    print("Testing deep_scrape with stealth mode on Yahoo Finance...")
    result = await tool_executor.execute({
        'tool': 'deep_scrape',
        'reason': 'Need NVO stock price and financials',
        'url': 'https://finance.yahoo.com/quote/NVO/',
        'query': 'NVO stock price market cap revenue'
    })
    print(f"Result length: {len(result)} chars")
    has_error = "error" in result.lower()[:150] or "failed" in result.lower()[:150]
    print(f"Has error: {has_error}")
    # Print first 1000 chars
    print("--- First 1000 chars ---")
    print(result[:1000])

asyncio.run(test())
