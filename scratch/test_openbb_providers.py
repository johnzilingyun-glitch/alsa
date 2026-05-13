"""Test which OpenBB providers are available for key endpoints."""
from openbb import obb
import inspect

tests = [
    ('equity.fundamental.income', obb.equity.fundamental.income),
    ('equity.fundamental.balance', obb.equity.fundamental.balance),
    ('equity.fundamental.cash', obb.equity.fundamental.cash),
    ('equity.fundamental.metrics', obb.equity.fundamental.metrics),
    ('equity.estimates.consensus', obb.equity.estimates.consensus),
    ('equity.estimates.price_target', obb.equity.estimates.price_target),
    ('equity.estimates.forward_eps', obb.equity.estimates.forward_eps),
    ('equity.ownership.insider_trading', obb.equity.ownership.insider_trading),
    ('equity.ownership.institutional', obb.equity.ownership.institutional),
    ('equity.fundamental.filings', obb.equity.fundamental.filings),
    ('equity.fundamental.transcript', obb.equity.fundamental.transcript),
    ('equity.fundamental.revenue_per_segment', obb.equity.fundamental.revenue_per_segment),
    ('equity.fundamental.revenue_per_geography', obb.equity.fundamental.revenue_per_geography),
    ('equity.compare.peers', obb.equity.compare.peers),
    ('economy.fred_search', obb.economy.fred_search),
    ('economy.fred_series', obb.economy.fred_series),
    ('economy.cpi', obb.economy.cpi),
    ('economy.gdp', obb.economy.gdp.nominal if hasattr(obb.economy.gdp, 'nominal') else obb.economy.gdp),
    ('news.company', obb.news.company),
    ('news.world', obb.news.world),
]

for name, func in tests:
    try:
        sig = inspect.signature(func)
        p = sig.parameters.get('provider')
        if p and hasattr(p, 'annotation') and hasattr(p.annotation, '__args__'):
            options = [str(a) for a in p.annotation.__args__ if 'None' not in str(a)]
            print(f'{name}: {options}')
        elif p:
            print(f'{name}: default={p.default}')
        else:
            print(f'{name}: no provider')
    except Exception as e:
        print(f'{name}: ERR {e}')
