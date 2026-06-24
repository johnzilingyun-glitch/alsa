with open("app/services/expert_tools.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace properties with await asyncio.to_thread(getattr, ticker, ...)
replacements = [
    ("bs = ticker.balance_sheet", 'bs = await asyncio.to_thread(getattr, ticker, "balance_sheet")'),
    ("cf = ticker.cashflow", 'cf = await asyncio.to_thread(getattr, ticker, "cashflow")'),
    ("fin = ticker.financials", 'fin = await asyncio.to_thread(getattr, ticker, "financials")'),
    ("info = ticker.info", 'info = await asyncio.to_thread(getattr, ticker, "info")'),
    ("qf = ticker.quarterly_financials", 'qf = await asyncio.to_thread(getattr, ticker, "quarterly_financials")'),
    ("divs = ticker.dividends", 'divs = await asyncio.to_thread(getattr, ticker, "dividends")'),
]

for target, rep in replacements:
    assert target in content, f"Could not find exact target content: {target}"
    content = content.replace(target, rep)

with open("app/services/expert_tools.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully refactored app/services/expert_tools.py")
