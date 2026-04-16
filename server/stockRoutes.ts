import { Router } from 'express';
import YahooFinance from 'yahoo-finance2';
import { monitor } from './dataSourceHealth.js';
import { logDebug, logError } from './stockLogger.js';
import { calcIndicators } from './indicators/technicalCalc.js';
import { calculateVolatility, calculateVolatilityAdjustedLimit } from './indicators/riskMetrics.js';
import { calculateFundamentalScores, calculateIntrinsicValueEstimate } from './indicators/fundamentalScoring.js';

const yahooFinance = new YahooFinance();
const router = Router();

// --- Simple InMemory Cache ---
const apiCache = new Map<string, { data: any, timestamp: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function getCached(key: string) {
  const item = apiCache.get(key);
  if (item && Date.now() - item.timestamp < CACHE_TTL) return item.data;
  return null;
}
function setCache(key: string, data: any) {
  apiCache.set(key, { data, timestamp: Date.now() });
}
// -----------------------------

// Market Indices
router.get('/stock/indices', async (req, res) => {
  const { market } = req.query;

  const indexSymbols: Record<string, { symbol: string; name: string }[]> = {
    'A-Share': [
      { symbol: '000001.SS', name: '上证综指' },
      { symbol: '399001.SZ', name: '深证成指' },
      { symbol: '399006.SZ', name: '创业板指' },
      { symbol: '000300.SS', name: '沪深300' },
      { symbol: '^HSI', name: '恒生指数' },
    ],
    'HK-Share': [
      { symbol: '^HSI', name: '恒生指数' },
      { symbol: '^HSTECH', name: '恒生科技指数' },
      { symbol: '^HSCE', name: '国企指数' },
      { symbol: '^HSCCI', name: '红筹指数' },
      { symbol: '^S&P/HKEX GEM', name: '创业板指数' },
    ],
    'US-Share': [
      { symbol: '^GSPC', name: 'S&P 500' },
      { symbol: '^IXIC', name: '纳斯达克综合' },
      { symbol: '^DJI', name: '道琼斯工业' },
      { symbol: '^RUT', name: '罗素2000' },
      { symbol: '^SOX', name: '费城半导体' },
    ],
  };

  const marketKey = (market as string) || 'A-Share';
  const validMarkets = ['A-Share', 'HK-Share', 'US-Share'];
  const symbols = indexSymbols[validMarkets.includes(marketKey) ? marketKey : 'A-Share'];

  const cacheKey = `indices_${marketKey}`;
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const startTime = Date.now();
    // Use parallel fetching to avoid long sequential waits
    const results = await Promise.all(symbols.map(async (idx) => {
      try {
        const quote = await yahooFinance.quote(idx.symbol as any) as any;
        if (quote) {
          const price = quote.regularMarketPrice;
          const prevClose = quote.regularMarketPreviousClose;
          let change = quote.regularMarketChange;
          let changePercent = quote.regularMarketChangePercent;

          if (change === undefined && price !== undefined && prevClose !== undefined) {
            change = price - prevClose;
          }
          if (changePercent === undefined && change !== undefined && prevClose !== undefined && prevClose !== 0) {
            changePercent = (change / prevClose) * 100;
          }

          const marketTime = quote.regularMarketTime ? new Date(quote.regularMarketTime) : new Date();
          const formattedTime = marketTime.toLocaleString('zh-CN', {
            timeZone: 'Asia/Shanghai',
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
          });

          return {
            name: idx.name,
            symbol: idx.symbol,
            price,
            change: change !== undefined ? parseFloat(change.toFixed(2)) : 0,
            changePercent: changePercent !== undefined ? parseFloat(changePercent.toFixed(2)) : 0,
            previousClose: prevClose,
            lastUpdated: formattedTime + ' CST',
            source: 'Yahoo Finance API',
            marketState: quote.marketState,
          };
        }
      } catch (e) {
        logDebug(`Yahoo Index Fetch`, `Failed for ${idx.symbol}: ${e instanceof Error ? e.message : String(e)}`);
      }
      return null;
    }));

    let filteredResults = results.filter(r => r !== null);

    // Fallback for A-Share if Yahoo returned too few results
    if (marketKey === 'A-Share' && filteredResults.length < 3) {
      logDebug(`A-Share Fallback`, `Yahoo results too low (${filteredResults.length}), triggering Sina fallback...`);
      try {
        const sinaIndices = [
          { s: 's_sh000001', name: '上证综指', sym: '000001.SS' },
          { s: 's_sz399001', name: '深证成指', sym: '399001.SZ' },
          { s: 's_sz399006', name: '创业板指', sym: '399006.SZ' },
          { s: 's_sh000300', name: '沪深300', sym: '000300.SS' }
        ];
        
        const sinaUrl = `https://hq.sinajs.cn/list=${sinaIndices.map(i => i.s).join(',')}`;
        const response = await fetch(sinaUrl, { headers: { 'Referer': 'https://finance.sina.com.cn' } });
        const text = await response.text();
        
        sinaIndices.forEach(idx => {
          const match = text.match(new RegExp(`hq_str_${idx.s}="([^"]+)"`));
          if (match?.[1]) {
            const parts = match[1].split(',');
            if (parts.length >= 4) {
              const price = parseFloat(parts[1]);
              const change = parseFloat(parts[2]);
              const changePercent = parseFloat(parts[3]);
              
              // Only add if not already present from Yahoo
              if (!filteredResults.find(r => r.symbol === idx.sym)) {
                filteredResults.push({
                  name: idx.name,
                  symbol: idx.sym,
                  price,
                  change: parseFloat(change.toFixed(2)),
                  changePercent: parseFloat(changePercent.toFixed(2)),
                  previousClose: parseFloat((price - change).toFixed(2)),
                  lastUpdated: new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) + ' CST',
                  source: 'Sina Finance (Fallback)',
                  marketState: 'REGULAR'
                });
              }
            }
          }
        });
      } catch (sinaErr) {
        logError(sinaErr, `Sina Fallback failed`);
      }
    }

    monitor.recordSuccess('yahoo', Date.now() - startTime);
    setCache(cacheKey, filteredResults);
    res.json(filteredResults);
  } catch (error) {
    monitor.recordFailure('yahoo');
    console.error('Indices fetch error:', error);
    res.status(500).json({ error: 'Failed to fetch indices data' });
  }
});

// Commodities
router.get('/stock/commodities', async (req, res) => {
  const commoditySymbols = [
    { symbol: 'GC=F', name: '伦敦金 (XAU)', unit: '$/oz' },
    { symbol: 'HG=F', name: 'LME铜 (HG)', unit: '$/lb' },
    { symbol: 'CL=F', name: '原油 (WTI)', unit: '$/bbl' },
    { symbol: 'SI=F', name: '白银', unit: '$/oz' },
    { symbol: 'USDCNY=X', name: '美元/人民币', unit: 'CNY' },
  ];

  const cacheKey = 'commodities';
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    // Parallel fetch — ~5x faster than sequential for..of loop
    const results = (await Promise.all(commoditySymbols.map(async (item) => {
      try {
        const quote = await yahooFinance.quote(item.symbol) as any;
        if (quote) {
          return {
            name: item.name,
            symbol: item.symbol,
            price: quote.regularMarketPrice,
            changePercent: quote.regularMarketChangePercent !== undefined ? parseFloat(quote.regularMarketChangePercent.toFixed(2)) : 0,
            unit: item.unit,
            source: 'Yahoo Finance API',
            lastUpdated: new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) + ' CST'
          };
        }
      } catch (e) {
        console.warn(`Failed to fetch commodity ${item.symbol}:`, e instanceof Error ? e.message : String(e));
      }
      return null;
    }))).filter(r => r !== null);
    setCache(cacheKey, results);
    res.json(results);
  } catch (error) {
    console.error('Commodities fetch error:', error);
    res.status(500).json({ error: 'Failed to fetch commodities data' });
  }
});

// Financial News (Backend deterministic fetch to save AI tokens)
router.get('/stock/news', async (req, res) => {
  const { market, symbol } = req.query;
  const marketKey = (market as string) || 'A-Share';
  const symbolKey = symbol ? (symbol as string).toUpperCase() : null;
  const cacheKey = symbolKey ? `news_${marketKey}_${symbolKey}` : `news_${marketKey}`;
  
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const news: any[] = [];
    
    // 0. Ticker-specific search (Priority if symbol exists)
    if (symbolKey) {
      try {
        const yfSym = appendMarketSuffix(symbolKey, marketKey);
        const searchResult = await yahooFinance.search(yfSym, { newsCount: 8 });
        if (searchResult?.news && searchResult.news.length > 0) {
          searchResult.news.forEach((n: any) => {
            news.push({
              title: n.title,
              url: n.link,
              time: new Date(n.providerPublishTime).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
              source: n.publisher || 'Yahoo Finance'
            });
          });
        }
      } catch (e) {
        logError(e, `Ticker News Fetch Failed for ${symbolKey}`);
      }
    }

    // 1. Primary Top-Tier Fetch via Python Microservice (AkShare / FinNLP style) - Only for general market news or if ticker news is empty
    if (news.length < 3) {
      try {
        const pythonRes = await fetch(`http://127.0.0.1:8000/api/market/news?market=${marketKey}`);
        if (pythonRes.ok) {
          const pythonData = await pythonRes.json();
          if (pythonData.success && pythonData.data && pythonData.data.length > 0) {
            news.push(...pythonData.data);
          }
        }
      } catch (e) {
        console.warn("Python News MS unavailable, falling back to Node fetchers:", e);
      }
    }
    
    // 2. Fallback simple fetch for Sina Roll News (if A-share/HK-share)
    if (news.length < 5 && (marketKey === 'A-Share' || marketKey === 'HK-Share')) {
      try {
        const sinaUrl = 'https://finance.sina.com.cn/rss/roll.xml';
        const response = await fetch(sinaUrl, {
          headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
        });
        const text = await response.text();
        
        // Flexible regex for RSS items, handling both CDATA and plain text titles
        const itemRegex = /<item>[\s\S]*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>[\s\S]*?<link>(.*?)<\/link>[\s\S]*?<pubDate>(.*?)<\/pubDate>[\s\S]*?<\/item>/g;
        let match;
        let count = 0;
        
        while ((match = itemRegex.exec(text)) !== null && count < (8 - news.length)) {
          news.push({
            title: match[1].replace(/<!\[CDATA\[|\]\]>/g, '').trim(),
            url: match[2].trim(),
            time: new Date(match[3]).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
            source: 'Sina Finance'
          });
          count++;
        }
      } catch (e) {
        logError(e, 'Sina News Fetch Failed');
      }
    }

    // Always fetch some global Yahoo news (Guaranteed Fallback)
    if (news.length < 5 || marketKey === 'US-Share') {
      try {
        const query = marketKey === 'A-Share' ? '000001.SS' : marketKey === 'HK-Share' ? '0700.HK' : 'SPY';
        const query2 = marketKey === 'A-Share' ? 'BABA' : marketKey === 'HK-Share' ? 'BABA' : 'QQQ';
        
        const [yahooNews1, yahooNews2] = await Promise.all([
          yahooFinance.search(query, { newsCount: 4 }),
          yahooFinance.search(query2, { newsCount: 4 })
        ]);
        
        const combinedNews = [...(yahooNews1?.news || []), ...(yahooNews2?.news || [])];
        
        if (combinedNews.length > 0) {
          combinedNews.forEach((n: any) => {
            news.push({
              title: n.title,
              url: n.link,
              time: new Date(n.providerPublishTime).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
              source: n.publisher || 'Yahoo Finance'
            });
          });
        }
      } catch (e) {
        logError(e, 'Yahoo News Fetch Failed');
      }
    }

    // De-duplicate by title
    const uniqueNews = Array.from(new Map(news.map(item => [item.title, item])).values()).slice(0, 8);
    
    setCache(cacheKey, uniqueNews);
    res.json(uniqueNews);
  } catch (error) {
    console.error('News fetch error:', error);
    res.status(500).json({ error: 'Failed to fetch news data' });
  }
});

// Institutional Sector Flows (Python Microservice Proxy)
router.get('/stock/sectors', async (req, res) => {
  const cacheKey = 'sector_flow';
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const response = await fetch('http://127.0.0.1:8000/api/market/sector_flow');
    if (!response.ok) throw new Error(`Python service failed: ${response.status}`);
    const data = await response.json();
    
    if (data.success && data.data) {
      setCache(cacheKey, data.data);
      return res.json(data.data);
    }
  } catch (error) {
    console.warn('Sector flow fetch error (is Python backend running?):', error);
    res.json({ topInflows: [], topOutflows: [] });
  }
});

// Northbound Capital Flows (Python Microservice Proxy)
router.get('/stock/northbound', async (req, res) => {
  const cacheKey = 'northbound_flow';
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const response = await fetch('http://127.0.0.1:8000/api/market/northbound');
    if (!response.ok) throw new Error(`Python service failed: ${response.status}`);
    const data = await response.json();
    
    if (data.success && data.data) {
      setCache(cacheKey, data.data);
      return res.json(data.data);
    }
  } catch (error) {
    console.warn('Northbound flow fetch error (is Python backend running?):', error);
    res.json([]);
  }
});

// Stock Suggestion / Autocomplete (Universal)
router.get('/stock/suggest', async (req, res) => {
  const { input, market: currentMarket } = req.query;
  if (!input || typeof input !== 'string' || input.trim().length < 1) {
    return res.json([]);
  }

  const suggestions: any[] = [];
  const encodedInput = encodeURIComponent(input.trim());

  try {
    // 1. Try EastMoney Suggest API
    // Response format: var cb = "code,symbol,marketType,pinyin,name,category,flag;..."
    try {
      const emUrl = `https://suggest.eastmoney.com/suggest/default.aspx?name=cb&input=${encodedInput}`;
      const emResponse = await fetch(emUrl);
      const emText = await emResponse.text();
      const emMatch = emText.match(/var cb\s*=\s*"(.*)"/);
      if (emMatch?.[1]) {
        const items = emMatch[1].split(';').filter(Boolean);
        for (const item of items) {
          const parts = item.split(',');
          if (parts.length >= 5) {
            const code = parts[1];
            const emMarketType = parts[2];
            const pinyin = parts[3];
            const name = parts[4];
            let marketId = '';
            let exchange = '';
            // Market type mapping: 1=SZ, 2=SH, 21=HK, 31=US
            if (emMarketType === '1') { marketId = 'A-Share'; exchange = 'SZ'; }
            else if (emMarketType === '2') { marketId = 'A-Share'; exchange = 'SH'; }
            else if (emMarketType === '21') { marketId = 'HK-Share'; exchange = 'HK'; }
            else if (emMarketType === '31') { marketId = 'US-Share'; exchange = 'US'; }
            // Skip funds (11), indices (40), etc.
            
            if (marketId) {
              suggestions.push({
                symbol: code,
                name: name,
                pinyin: pinyin,
                exchange: exchange,
                market: marketId,
                source: 'EastMoney'
              });
            }
          }
        }
      }
    } catch {}

    // 2. Try Sina Suggest API
    if (suggestions.length < 5) {
      try {
        const sinaUrl = `https://suggest3.sinajs.cn/suggest/type=&key=${encodedInput}`;
        const sinaRes = await fetch(sinaUrl);
        // Sina returns GBK-encoded text, decode properly
        const sinaBuffer = await sinaRes.arrayBuffer();
        const sinaText = new TextDecoder('gbk').decode(sinaBuffer);
        const sinaMatch = sinaText.match(/="([^"]+)"/);
        if (sinaMatch?.[1]) {
          const parts = sinaMatch[1].split(';').filter(Boolean);
          for (const part of parts) {
            const details = part.split(',');
            if (details.length >= 5) {
              const compositeCode = details[0]; // e.g. "sh000001", "sz000001"
              const code = details[2];
              const name = details[4]; // actual stock name
              let marketId = '';
              let exchange = '';
              // Derive market from composite code prefix
              const prefix = compositeCode.substring(0, 2).toLowerCase();
              if (prefix === 'sh') { marketId = 'A-Share'; exchange = 'SH'; }
              else if (prefix === 'sz') { marketId = 'A-Share'; exchange = 'SZ'; }
              else if (prefix === 'hk') { marketId = 'HK-Share'; exchange = 'HK'; }
              else if (prefix === 'us') { marketId = 'US-Share'; exchange = 'US'; }
              if (marketId && !suggestions.find(s => s.symbol === code)) {
                suggestions.push({ symbol: code, name, exchange, market: marketId, source: 'Sina' });
              }
            }
          }
        }
      } catch {}
    }

    // 3. Yahoo Search Fallback
    if (suggestions.length === 0) {
      try {
        const yahooRes = await yahooFinance.search(input.trim());
        if (yahooRes?.quotes) {
          for (const q of yahooRes.quotes as any[]) {
            const s = (q.symbol || '').toUpperCase();
            let marketId = 'US-Share';
            if (s.endsWith('.SS') || s.endsWith('.SZ') || s.endsWith('.BJ')) marketId = 'A-Share';
            else if (s.endsWith('.HK')) marketId = 'HK-Share';
            if (!suggestions.find(subs => subs.symbol === q.symbol)) {
              suggestions.push({
                symbol: q.symbol.split('.')[0],
                fullSymbol: q.symbol,
                name: q.shortname || q.longname || q.symbol,
                exchange: q.exchange,
                market: marketId,
                source: 'Yahoo'
              });
            }
            if (suggestions.length >= 8) break;
          }
        }
      } catch {}
    }

    // Sort: Prioritize current market
    const sorted = suggestions.sort((a, b) => {
      if (a.market === currentMarket && b.market !== currentMarket) return -1;
      if (a.market !== currentMarket && b.market === currentMarket) return 1;
      return 0;
    });

    res.json(sorted.slice(0, 10));
  } catch (error) {
    console.error('Suggest API error:', error);
    res.status(500).json({ error: 'Failed to fetch suggestions' });
  }
});

// Real-time Stock Data (Universal)
router.get('/stock/realtime', async (req, res) => {
  const { symbol, market, symbols, debug } = req.query;
  const isDebug = debug === 'true';

  if (isDebug) logDebug('incoming_request', { symbol, market, symbols, path: '/stock/realtime' });

  // Batch logic
  if (symbols && typeof symbols === 'string' && symbols.trim()) {
    try {
      const rawSymbolList = symbols.split(',').map(s => s.trim()).filter(s => !!s).slice(0, 20); // Limit batch size
      const symbolList = rawSymbolList.map(s => {
        let sym = s.toUpperCase();
        if (sym.endsWith('.SH')) sym = sym.replace('.SH', '.SS');
        if (sym.length === 6) {
          if (sym.startsWith('60') || sym.startsWith('68')) return `${sym}.SS`;
          if (sym.startsWith('00') || sym.startsWith('30')) return `${sym}.SZ`;
          if (sym.startsWith('8') || sym.startsWith('4')) return `${sym}.BJ`;
        }
        return sym;
      });
      const results = await yahooFinance.quote(symbolList as any) as any[];
      return res.json(results.map(r => formatQuoteResult(r)));
    } catch {
      return res.status(500).json({ error: 'Failed' });
    }
  }

  if (!symbol || typeof symbol !== 'string' || !symbol.trim()) {
    return res.status(400).json({ error: 'Symbol is required' });
  }

  // Validate symbol format: alphanumeric, dots, hyphens, carets, slashes, equals (for Yahoo Finance symbols)
  const symbolStr = (symbol as string).trim();
  if (!/^[A-Za-z0-9.\-^/=]{1,20}$/.test(symbolStr)) {
    return res.status(400).json({ error: 'Invalid symbol format' });
  }

  try {
    const input = symbolStr;
    // Step 1: Broad Resolution
    const resolution = await resolveSymbolEx(input, market as string, isDebug);
    
    let result: any = null;
    let indicators: any = null;
    let source = 'Yahoo Finance API';

    // A-Share: Prioritize Python Microservice (AkShare)
    if (resolution.market === 'A-Share' && /^\d{6}$/.test(resolution.symbol)) {
      try {
        const [spotRes, histRes, valRes, techRes] = await Promise.all([
          fetch(`http://127.0.0.1:8000/api/stock/a_spot?symbol=${resolution.symbol}`).then(r => r.json()),
          fetch(`http://127.0.0.1:8000/api/stock/a_history?symbol=${resolution.symbol}`).then(r => r.json()),
          fetch(`http://127.0.0.1:8000/api/stock/a_valuation?symbol=${resolution.symbol}`).then(r => r.json()),
          fetch(`http://127.0.0.1:8000/api/technicals/${resolution.symbol}`).then(r => r.json()).catch(() => ({ success: false }))
        ]);

        if (spotRes.success && spotRes.data) {
          const d = spotRes.data;
          result = {
            symbol: d['代码'],
            shortName: d['名称'],
            regularMarketPrice: d['最新价'],
            regularMarketChange: d['涨跌额'],
            regularMarketChangePercent: d['涨跌幅'],
            regularMarketPreviousClose: d['昨收'],
            regularMarketOpen: d['今开'],
            regularMarketDayHigh: d['最高'],
            regularMarketDayLow: d['最低'],
            regularMarketVolume: d['成交量'],
            marketCap: d['总市值'],
            trailingPE: d['动态市盈率'],
            currency: 'CNY',
            fullExchangeName: 'CN',
            marketState: 'REGULAR'
          };
          source = 'AkShare (Local Python API)';

          // Enrich with valuation data (already fetched, previously unused)
          if (valRes.success && valRes.data) {
            const v = valRes.data;
            if (v['行业']) result.industry = v['行业'];
            if (v['总股本']) result.sharesOutstanding = v['总股本'];

            // Calculate quantitative fundamental scores
            const pe = parseFloat(v['动态市盈率']) || 0;
            const pb = parseFloat(v['市净率']) || 0;
            const roe = parseFloat(v['加权净资产收益率']) || parseFloat(v['净资产收益率']) || 10; // Default 10%
            const growth = parseFloat(v['净利润同期预计增幅']) || 10; // Default 10%
            const margin = parseFloat(v['毛利率']) || 20; // Default 20%
            const d2e = 0.5; // Placeholder for Debt-to-Equity if not easily available from spot

            result.fundamentalScores = calculateFundamentalScores({
              pe, pb, roe, grossMargin: margin, netProfitGrowth: growth, debtToEquity: d2e
            });
            result.intrinsicValueEstimate = calculateIntrinsicValueEstimate(result.regularMarketPrice, roe, growth);
          }
        }

        if (histRes.success && histRes.data) {
          const history = histRes.data;
          const prices = history.map((q: any) => q['收盘']);
          const volumes = history.map((q: any) => q['成交量']);
          const highs = history.map((q: any) => q['最高']);
          const lows = history.map((q: any) => q['最低']);

          indicators = calcIndicators(prices, volumes, highs, lows);
          
          // Add the 5-strategy quantitative technical ensemble if available
          if (techRes.success && techRes.data) {
            indicators.quantSignals = techRes.data;
          }

          // Calculate quantitative risk metrics
          const annVol = calculateVolatility(prices, 60);
          const volLimit = calculateVolatilityAdjustedLimit(annVol);
          indicators.riskMetrics = {
            annualizedVolatility: annVol,
            maxPositionLimit: volLimit.limit,
            volatilityRegime: volLimit.regime
          };
        }
      } catch (e) {
        logDebug('AkShare Fetch failed', e instanceof Error ? e.message : String(e));
      }
    }

    // Fallback or Non-A-Share: Use Yahoo Finance
    if (!result) {
      result = await tryQuoteEx(resolution.symbol, input, resolution.market, isDebug);
      if (result) {
        // Fetch indicators for Yahoo if not already fetched from AkShare
        if (!indicators) {
           try {
              const symWithSuffix = appendMarketSuffix(resolution.symbol, resolution.market);
              const now = new Date();
              const startDate = new Date();
              startDate.setDate(now.getDate() - 120); 
              
              const historyRes = await yahooFinance.chart(symWithSuffix, { 
                period1: startDate, 
                interval: '1d' 
              });

              if (historyRes?.quotes && historyRes.quotes.length > 0) {
                const prices = historyRes.quotes.map((q: any) => q.close).filter((p: any) => p != null);
                const volumes = historyRes.quotes.map((q: any) => q.volume).filter((v: any) => v != null);
                const highs = historyRes.quotes.map((q: any) => q.high).filter((h: any) => h != null);
                const lows = historyRes.quotes.map((q: any) => q.low).filter((l: any) => l != null);

                indicators = calcIndicators(prices, volumes, highs, lows, { roundVolume: true });
              }
           } catch {}
        }
      }
    }

    if (!result) {
      return res.status(404).json({ error: `无法找到代码 "${symbol}" 的相关数据。` });
    }

    const formatted = formatQuoteResult(result);
    if (source === 'AkShare (Local Python API)') {
      formatted.source = source;
    }

    res.json({
      ...formatted,
      resolvedMarket: resolution.market,
      technicalIndicators: indicators
    });
  } catch (error) {
    logError(error, 'realtime_total_error');
    res.status(500).json({ error: 'Failed' });
  }
});

// --- Helpers ---

async function resolveSymbolEx(input: string, preferredMarket: string, isDebug: boolean): Promise<{ symbol: string; market: string }> {
  const upperInput = input.toUpperCase();
  
  const CROSS_MAPPING: Record<string, { symbol: string, market: string }> = {
    'BABA': { symbol: '9988', market: 'HK-Share' },
    'TCEHY': { symbol: '700', market: 'HK-Share' },
    'JD': { symbol: '9618', market: 'HK-Share' },
    'MEITUAN': { symbol: '3690', market: 'HK-Share' },
    'TENCENT': { symbol: '700', market: 'HK-Share' },
    'PPMT': { symbol: '9992', market: 'HK-Share' },
  };

  if (CROSS_MAPPING[upperInput]) return CROSS_MAPPING[upperInput];

  try {
    const encodedInput = encodeURIComponent(input);
    const emResponse = await fetch(`https://suggest.eastmoney.com/suggest/default.aspx?name=cb&input=${encodedInput}`);
    const emText = await emResponse.text();
    const emMatch = emText.match(/^var cb = (\[.*\]);?$/);
    if (emMatch?.[1]) {
      const data = JSON.parse(emMatch[1]);
      if (Array.isArray(data) && data.length > 0) {
        let bestMatch = null;
        for (const item of data) {
          const parts = item.split(',');
          if (parts.length >= 7) {
            const code = parts[1];
            const emMarketName = parts[6];
            let marketId = '';
            if (['SH', 'SZ', 'BJ'].includes(emMarketName)) marketId = 'A-Share';
            else if (emMarketName === 'HK') marketId = 'HK-Share';
            else if (emMarketName === 'US') marketId = 'US-Share';
            if (marketId) {
              if (marketId === preferredMarket) return { symbol: code, market: marketId };
              if (!bestMatch) bestMatch = { symbol: code, market: marketId };
            }
          }
        }
        if (bestMatch) return bestMatch;
      }
    }
  } catch {}

  let resolvedSym = upperInput;
  let resolvedMarket = preferredMarket;
  if (/^\d{6}$/.test(upperInput)) resolvedMarket = 'A-Share';
  else if (/^\d{1,5}$/.test(upperInput)) resolvedMarket = 'HK-Share';
  else if (/^[A-Z]{1,5}$/.test(upperInput)) resolvedMarket = 'US-Share';

  return { symbol: resolvedSym, market: resolvedMarket };
}

async function tryQuoteEx(yfSymbol: string, input: string, market: string, isDebug: boolean): Promise<any> {
    const symWithSuffix = appendMarketSuffix(yfSymbol, market);
    try {
        const result = await yahooFinance.quote(symWithSuffix);
        if (result) return result;
    } catch {}

    try {
        const search = await yahooFinance.search(input);
        if (search?.quotes?.length) {
            return await yahooFinance.quote(search.quotes[0].symbol as any);
        }
    } catch {}
    
    return null;
}

function appendMarketSuffix(symbol: string, market: string): string {
  if (symbol.includes('.') || symbol.startsWith('^')) return symbol;
  if (market === 'A-Share' && /^\d{6}$/.test(symbol)) {
    if (symbol.startsWith('60') || symbol.startsWith('68')) return `${symbol}.SS`;
    if (symbol.startsWith('00') || symbol.startsWith('30')) return `${symbol}.SZ`;
    if (symbol.startsWith('43') || symbol.startsWith('83') || symbol.startsWith('87')) return `${symbol}.BJ`;
    return `${symbol.startsWith('6') ? symbol + '.SS' : symbol + '.SZ'}`;
  }
  if (market === 'HK-Share' && /^\d+$/.test(symbol)) return `${symbol.padStart(5, '0')}.HK`;
  return symbol;
}

function formatQuoteResult(result: any) {
  let changePercent = result.regularMarketChangePercent;
  let change = result.regularMarketChange;
  const price = result.regularMarketPrice;
  const prevClose = result.regularMarketPreviousClose;

  if (change === undefined && price !== undefined && prevClose !== undefined) {
    change = price - prevClose;
  }
  if (changePercent === undefined && change !== undefined && prevClose !== undefined && prevClose !== 0) {
    changePercent = (change / prevClose) * 100;
  }
  
  const dataTime = result.regularMarketTime ? new Date(result.regularMarketTime) : new Date();
  const formattedTime = dataTime.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }) + ' CST';

  return {
    symbol: result.symbol,
    name: result.shortName || result.longName || result.symbol,
    price,
    change: change !== undefined ? parseFloat(change.toFixed(2)) : 0,
    changePercent: changePercent !== undefined ? parseFloat(changePercent.toFixed(2)) : 0,
    previousClose: prevClose,
    open: result.regularMarketOpen,
    dayHigh: result.regularMarketDayHigh,
    dayLow: result.regularMarketDayLow,
    volume: result.regularMarketVolume,
    marketCap: result.marketCap,
    pe: result.trailingPE,
    currency: result.currency,
    lastUpdated: formattedTime,
    source: 'Yahoo Finance API',
    exchange: result.fullExchangeName || result.exchange,
    marketState: result.marketState,
    quoteDelay: result.exchangeDataDelayedBy || 0
  };
}

export default router;
