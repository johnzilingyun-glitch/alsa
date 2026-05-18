"""Quick test of yfinance price enrichment for A-share stocks."""
import yfinance as yf

codes = ['300274', '601012', '600438', '002459', '300750']
for code in codes:
    suffix = '.SS' if code.startswith('6') else '.SZ'
    try:
        t = yf.Ticker(code + suffix)
        info = t.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        name = info.get('shortName') or info.get('longName') or 'N/A'
        pe = info.get('trailingPE')
        print(f'{code}: {name} = {price} CNY, PE={pe}')
    except Exception as e:
        print(f'{code}: ERROR - {e}')
