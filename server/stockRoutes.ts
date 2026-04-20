import { Router } from 'express';
import { yf } from './lib/yahooFinance.js';
import axios from 'axios';
import { monitor } from './dataSourceHealth.js';
import { logDebug, logError } from './stockLogger.js';
import { calcIndicators } from './indicators/technicalCalc.js';
import { calculateVolatility, calculateVolatilityAdjustedLimit } from './indicators/riskMetrics.js';
import { calculateFundamentalScores, calculateIntrinsicValueEstimate } from './indicators/fundamentalScoring.js';

// [FIX]: Managed via hardened Sina fallback in stockRoutes.ts
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

async function fetchJsonWithTimeout(url: string, timeoutMs = 8000): Promise<any> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} for ${url}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function fetchAShareSpotFallbackFromSina(symbol: string): Promise<any | null> {
  const sinaCode = symbol.startsWith('6') ? `sh${symbol}` : `sz${symbol}`;
  const url = `https://hq.sinajs.cn/list=${sinaCode}`;
  const response = await fetch(url, {
    headers: { Referer: 'https://finance.sina.com.cn' }
  });
  const text = await response.text();
  const match = text.match(/="([^"]*)"/);
  if (!match?.[1]) return null;

  const parts = match[1].split(',');
  if (parts.length < 10) return null;

  const name = parts[0] || symbol;
  const open = Number(parts[1]);
  const prevClose = Number(parts[2]);
  const price = Number(parts[3]);
  const high = Number(parts[4]);
  const low = Number(parts[5]);
  const volume = Number(parts[8]);

  if (!Number.isFinite(price)) return null;

  const change = Number.isFinite(prevClose) ? (price - prevClose) : 0;
  const changePercent = Number.isFinite(prevClose) && prevClose !== 0 ? (change / prevClose) * 100 : 0;

  return {
    symbol,
    shortName: name,
    regularMarketPrice: price,
    regularMarketChange: change,
    regularMarketChangePercent: changePercent,
    regularMarketPreviousClose: Number.isFinite(prevClose) ? prevClose : undefined,
    regularMarketOpen: Number.isFinite(open) ? open : undefined,
    regularMarketDayHigh: Number.isFinite(high) ? high : undefined,
    regularMarketDayLow: Number.isFinite(low) ? low : undefined,
    regularMarketVolume: Number.isFinite(volume) ? volume : undefined,
    currency: 'CNY',
    fullExchangeName: 'CN',
    marketState: 'REGULAR',
    source: 'Sina Finance (Fallback)',
  };
}

async function fetchHKSpotFallbackFromSina(symbol: string): Promise<any | null> {
  // Sina HK codes are usually 'hk' + 5 digits (e.g., hk00700)
  const sinaCode = `hk${symbol.padStart(5, '0')}`;
  const url = `https://hq.sinajs.cn/list=${sinaCode}`;
  
  try {
    const response = await fetch(url, {
      headers: { Referer: 'https://finance.sina.com.cn' }
    });
    const text = await response.text();
    const match = text.match(/="([^"]*)"/);
    if (!match?.[1]) return null;

    const parts = match[1].split(',');
    if (parts.length < 10) return null;

    // Sina HK parts: 0=EngName, 1=ChiName, 2=Open, 3=PrevClose, 4=High, 5=Low, 6=Last, 7=Change, 8=Change%, 9=Buy, 10=Sell, 11=Volume, ...
    const name = parts[1] || symbol;
    
    // [HARDENING]: Check index 6 (last price) and fallback to index 3 (prev close) or index 2 (open)
    let price = Number(parts[6]);
    const prevClose = Number(parts[3]);
    const open = Number(parts[2]);
    const high = Number(parts[4]);
    const low = Number(parts[5]);
    const volume = Number(parts[12]);
    
    if ((!price || price === 0) && prevClose > 0) price = prevClose;
    if ((!price || price === 0) && open > 0) price = open;

    if (!Number.isFinite(price) || price === 0) return null;

    const change = Number(parts[7]);
    const changePercent = Number(parts[8]);

    return {
      symbol,
      shortName: name,
      regularMarketPrice: price,
      regularMarketChange: change,
      regularMarketChangePercent: changePercent,
      regularMarketPreviousClose: prevClose,
      regularMarketOpen: Number(parts[2]),
      regularMarketDayHigh: high,
      regularMarketDayLow: low,
      regularMarketVolume: volume,
      currency: 'HKD',
      fullExchangeName: 'HK',
      marketState: 'REGULAR',
      source: 'Sina Finance HK (Fallback)',
    };
  } catch (e) {
    console.warn(`[SinaHKFallback] Failed for ${symbol}:`, e);
    return null;
  }
}

async function fetchSectorFlowFromEastMoneyFallback(): Promise<{ topInflows: any[]; topOutflows: any[] } | null> {
  const url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1&ut=b2884a393a59ad64002292a3e90d46a5&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f2,f3,f62,f184';
  const data = await fetchJsonWithTimeout(url, 7000);
  const diff = data?.data?.diff;
  if (!Array.isArray(diff) || diff.length === 0) return null;

  const items = diff.map((item: any) => ({
    行业: item.f14,
    最新价: item.f2,
    涨跌幅: item.f3,
    '主力净流入-净额': item.f62,
    '主力净流入-净占比': item.f184,
  }));

  const sorted = items.sort((a: any, b: any) => (Number(b['主力净流入-净额']) || 0) - (Number(a['主力净流入-净额']) || 0));
  return {
    topInflows: sorted.slice(0, 5),
    topOutflows: sorted.slice(-3).reverse(),
  };
}

async function fetchNorthboundFromEastMoneyFallback(): Promise<any[] | null> {
  const url = 'https://push2.eastmoney.com/api/qt/kamt.rtmin/get?fields1=f1,f2,f3,f4&fields2=f51,f52,f54,f58,f56&ut=b2884a393a59ad64002292a3e90d46a5';
  const data = await fetchJsonWithTimeout(url, 7000);
  const s2n = data?.data?.s2n;
  if (!Array.isArray(s2n) || s2n.length === 0) return null;

  const latest = String(s2n[s2n.length - 1] || '');
  const parts = latest.split(',');
  if (parts.length < 3) return null;

  const sh = Number(parts[1]) || 0;
  const sz = Number(parts[2]) || 0;
  return [{
    时间: parts[0] || '',
    沪股通净流入: sh,
    深股通净流入: sz,
    北向资金净流入: sh + sz,
  }];
}
const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || 'http://127.0.0.1:8001';

// -----------------------------

// Market Indices
router.get('/stock/indices', async (req, res) => {
  const { market } = req.query;
  const marketKey = (market as string) || 'A-Share';
  const cacheKey = `indices_${marketKey}`;
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const startTime = Date.now();
    // Proxy to Python Microservice
    const pythonRes = await axios.get(`${PYTHON_SERVICE_URL}/api/market/indices?market=${marketKey}`);
    
    if (pythonRes.data.success && Array.isArray(pythonRes.data.data) && pythonRes.data.data.length > 0) {
      const data = pythonRes.data.data;
      setCache(cacheKey, data);
      monitor.recordSuccess('python_market', Date.now() - startTime);
      return res.json(data);
    }
    throw new Error('Python indices fetch failed or empty');
  } catch (error) {
    monitor.recordFailure('python_market');
    console.warn(`Indices fetch error for ${marketKey} (falling back to legacy yf):`, error instanceof Error ? error.message : error);
    
    // Legacy fallback (preserving minimal safety)
    try {
        const symbols = marketKey === 'HK-Share' ? ['^HSI', '^HSTECH'] : ['000001.SS', '399001.SZ', '^HSI'];
        const results = await yf.quote(symbols as any);
        if (results && results.length > 0) {
          return res.json(results);
        }
        throw new Error('Local Yahoo Finance also failed');
    } catch (e) {
        // ULTIMATE FAIL-SAFE: Return hardcoded stale defaults to prevent UI crash
        console.error('CRITICAL: All indices sources failed. Returning stale defaults.');
        const defaults = marketKey === 'HK-Share' ? [
          { symbol: '^HSI', shortName: '恒生指数', regularMarketPrice: 0, regularMarketChange: 0, regularMarketChangePercent: 0, status: 'stale' },
          { symbol: '^HSTECH', shortName: '恒生科技', regularMarketPrice: 0, regularMarketChange: 0, regularMarketChangePercent: 0, status: 'stale' }
        ] : [
          { symbol: '000001.SS', shortName: '上证指数', regularMarketPrice: 0, regularMarketChange: 0, regularMarketChangePercent: 0, status: 'stale' },
          { symbol: '399001.SZ', shortName: '深证成指', regularMarketPrice: 0, regularMarketChange: 0, regularMarketChangePercent: 0, status: 'stale' },
          { symbol: '^HSI', shortName: '恒生指数', regularMarketPrice: 0, regularMarketChange: 0, regularMarketChangePercent: 0, status: 'stale' }
        ];
        res.json(defaults);
    }
  }
});

// Commodities
router.get('/stock/commodities', async (req, res) => {
  const cacheKey = 'commodities';
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const pythonRes = await axios.get(`http://127.0.0.1:8001/api/market/commodities`, { timeout: 5000 });
    if (pythonRes.data.success) {
      const data = pythonRes.data.data;
      setCache(cacheKey, data);
      return res.json(data);
    }
    return res.json([]); // Fail gracefully with empty data
  } catch (error) {
    console.error('Commodities fetch error:', error);
    res.json([]); // Fail gracefully with empty data
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

  const startTime = Date.now();
  try {
    const news: any[] = [];
    
    // Support parallel fetching for all sources
    const fetchTasks: Promise<any>[] = [];

    // 0. Ticker-specific Yahoo Search
    if (symbolKey) {
      fetchTasks.push((async () => {
        const start = Date.now();
        try {
          // [OPTIMIZATION]: Wrap yf.search in a timeout to prevent hanging the whole news pipe
          const searchPromise = yf.search(yfSym, { newsCount: 8 });
          const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error('Yahoo Search Timeout')), 4000));
          const searchResult = await Promise.race([searchPromise, timeoutPromise]) as any;
          
          const items = (searchResult?.news || []).map((n: any) => ({
            title: n.title,
            url: n.link,
            time: new Date(n.providerPublishTime).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
            source: n.publisher || 'Yahoo Finance'
          }));
          logDebug('performance', { source: 'yahoo_ticker', latency: Date.now() - start, count: items.length });
          return items;
        } catch (e) {
          logError(e, `Ticker News Fetch Failed or Timed Out for ${symbolKey}`);
          return [];
        }
      })());
    }

    // 1. Python Microservice
    fetchTasks.push((async () => {
      const start = Date.now();
      try {
        const pythonRes = await fetch(`http://127.0.0.1:8001/api/market/news?market=${marketKey}`, { 
          signal: AbortSignal.timeout(4000) 
        });
        if (pythonRes.ok) {
          const pythonData = await pythonRes.json();
          const items = (pythonData.success && pythonData.data) ? pythonData.data : [];
          logDebug('performance', { source: 'python_news', latency: Date.now() - start, count: items.length });
          return items;
        }
      } catch (e) {
        logDebug('warning', `Python News MS slow or unavailable: ${e}`);
      }
      return [];
    })());

    // 2. Sina RSS Fallback
    if (marketKey === 'A-Share' || marketKey === 'HK-Share') {
      fetchTasks.push((async () => {
        const start = Date.now();
        try {
          const sinaUrl = 'https://finance.sina.com.cn/rss/roll.xml';
          const response = await fetch(sinaUrl, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' },
            signal: AbortSignal.timeout(3000)
          });
          const text = await response.text();
          const itemRegex = /<item>[\s\S]*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>[\s\S]*?<link>(.*?)<\/link>[\s\S]*?<pubDate>(.*?)<\/pubDate>[\s\S]*?<\/item>/g;
          let match;
          const items = [];
          while ((match = itemRegex.exec(text)) !== null && items.length < 8) {
            items.push({
              title: match[1].replace(/<!\[CDATA\[|\]\]>/g, '').trim(),
              url: match[2].trim(),
              time: new Date(match[3]).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
              source: 'Sina Finance'
            });
          }
          logDebug('performance', { source: 'sina_rss', latency: Date.now() - start, count: items.length });
          return items;
        } catch (e) {
          logError(e, 'Sina News Fetch Failed');
          return [];
        }
      })());
    }

    // 3. Global Yahoo Fallback (Parallel with others)
    fetchTasks.push((async () => {
      const start = Date.now();
      try {
        const query = marketKey === 'A-Share' ? '000001.SS' : marketKey === 'HK-Share' ? '0700.HK' : 'SPY';
        // [OPTIMIZATION]: Wrap global yf.search in a timeout
        const searchPromise = yf.search(query, { newsCount: 5 });
        const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error('Global Yahoo Search Timeout')), 3500));
        const searchResult = await Promise.race([searchPromise, timeoutPromise]) as any;
        
        const items = (searchResult?.news || []).map((n: any) => ({
          title: n.title,
          url: n.link,
          time: new Date(n.providerPublishTime).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
          source: n.publisher || 'Yahoo Finance'
        }));
        logDebug('performance', { source: 'yahoo_global', latency: Date.now() - start, count: items.length });
        return items;
      } catch (e) {
        return [];
      }
    })());

    const results = await Promise.all(fetchTasks);
    results.forEach(batch => news.push(...batch));

    // De-duplicate by title
    const uniqueNews = Array.from(new Map(news.map(item => [item.title, item])).values()).slice(0, 10);
    
    logDebug('performance', { endpoint: '/stock/news', totalLatency: Date.now() - startTime, finalCount: uniqueNews.length });
    
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
    const data = await fetchJsonWithTimeout('http://127.0.0.1:8001/api/market/sector_flow', 7000);
    
    if (data.success && data.data) {
      setCache(cacheKey, data.data);
      return res.json(data.data);
    }
  } catch (error) {
    console.warn('Sector flow fetch error (is Python backend running?):', error);
    const fallback = await fetchSectorFlowFromEastMoneyFallback().catch(() => null);
    if (fallback) {
      setCache(cacheKey, fallback);
      return res.json(fallback);
    }
    res.json({ topInflows: [], topOutflows: [] });
  }
});

// Northbound Capital Flows (Python Microservice Proxy)
router.get('/stock/northbound', async (req, res) => {
  const cacheKey = 'northbound_flow';
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const data = await fetchJsonWithTimeout('http://127.0.0.1:8001/api/market/northbound', 7000);
    
    if (data.success && data.data) {
      setCache(cacheKey, data.data);
      return res.json(data.data);
    }
  } catch (error) {
    console.warn('Northbound flow fetch error (is Python backend running?):', error);
    const fallback = await fetchNorthboundFromEastMoneyFallback().catch(() => null);
    if (fallback) {
      setCache(cacheKey, fallback);
      return res.json(fallback);
    }
    res.json([]);
  }
});

// LHB (Dragon-Tiger List)
router.get('/stock/lhb', async (req, res) => {
  const { symbol, date } = req.query;
  try {
    // [HARDENING]: Only attempt LHB for A-Shares (6 digits)
    if (!/^\d{6}$/.test(symbol as string)) {
      return res.json({ success: true, data: [], message: 'LHB not applicable for this market' });
    }
    const url = `http://127.0.0.1:8001/api/stock/lhb?symbol=${symbol}${date ? `&date=${date}` : ''}`;
    const data = await fetchJsonWithTimeout(url, 7000);
    res.json(data);
  } catch (error) {
    console.warn(`LHB fetch failed for ${symbol}:`, error instanceof Error ? error.message : String(error));
    res.json({ success: false, data: [], error: 'Failed to fetch LHB' });
  }
});

// Margin trading
router.get('/stock/margin', async (req, res) => {
  const { symbol } = req.query;
  try {
    const url = `http://127.0.0.1:8001/api/stock/margin?symbol=${symbol}`;
    const data = await fetchJsonWithTimeout(url, 7000);
    res.json(data);
  } catch (error) {
    console.warn(`Margin fetch failed for ${symbol}:`, error instanceof Error ? error.message : String(error));
    res.json({ success: false, data: [] });
  }
});

// Corporate Announcements
router.get('/stock/announcements', async (req, res) => {
  const { symbol } = req.query;
  try {
    const url = `http://127.0.0.1:8001/api/stock/notices?symbol=${symbol}`;
    const data = await fetchJsonWithTimeout(url, 7000);
    res.json(data);
  } catch (error) {
    console.warn(`Announcements fetch failed for ${symbol}:`, error instanceof Error ? error.message : String(error));
    res.json({ success: false, data: [] });
  }
});

// Social Trends
router.get('/market/social-trends', async (req, res) => {
  try {
    const data = await fetchJsonWithTimeout('http://127.0.0.1:8001/api/market/social_trends', 7000);
    res.json(data);
  } catch (error) {
    res.status(500).json({ success: false, error: 'Failed to fetch social trends' });
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
      const emText = await fetchJsonWithTimeout(emUrl, 4000).then(t => typeof t === 'string' ? t : JSON.stringify(t)).catch(() => '');
      
      // EastMoney usually returns plain text like: var cb="...";
      // If fetchJsonWithTimeout returns parsed JSON (rare for this API), we handle it
      let text = emText;
      if (!text.includes('var cb')) {
        const rawRes = await fetch(emUrl, { signal: AbortSignal.timeout(4000) }).catch(() => null);
        text = rawRes ? await rawRes.text() : '';
      }

      const emMatch = text.match(/var cb\s*=\s*"(.*)"/);
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
        const sinaRes = await fetch(sinaUrl, { signal: AbortSignal.timeout(4000) }).catch(() => null);
        if (!sinaRes) throw new Error('Sina Timeout');
        
        // Sina returns GBK-encoded text, decode properly
        const sinaBuffer = await sinaRes.arrayBuffer();
        const sinaText = new TextDecoder('gbk').decode(sinaBuffer);
        const sinaMatch = sinaText.match(/="([^"]+)"/) || sinaText.match(/=\s*"([^"]+)"/);
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
        const yahooRes = await yf.search(input.trim());
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
      const results = await yf.quote(symbolList as any) as any[];
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
          fetchJsonWithTimeout(`http://127.0.0.1:8001/api/stock/a_spot?symbol=${resolution.symbol}`, 7000).catch(() => ({ success: false })),
          fetchJsonWithTimeout(`http://127.0.0.1:8001/api/stock/a_history?symbol=${resolution.symbol}`, 9000).catch(() => ({ success: false })),
          fetchJsonWithTimeout(`http://127.0.0.1:8001/api/stock/a_valuation?symbol=${resolution.symbol}`, 7000).catch(() => ({ success: false })),
          fetchJsonWithTimeout(`http://127.0.0.1:8001/api/technicals/${resolution.symbol}`, 9000).catch(() => ({ success: false }))
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

        // Backup API: if AkShare spot fails, fallback to Sina quote to avoid infinite loading UX.
        if (!result) {
          const fallbackSpot = await fetchAShareSpotFallbackFromSina(resolution.symbol).catch(() => null);
          if (fallbackSpot) {
            result = fallbackSpot;
            source = fallbackSpot.source;
          }
        }
      } catch (e) {
        logDebug('AkShare Fetch failed', e instanceof Error ? e.message : String(e));
      }
    }

    // HK-Share: Prioritize Python Microservice (AkShare HK Spot)
    if (!result && resolution.market === 'HK-Share' && /^\d{1,5}$/.test(resolution.symbol)) {
      try {
        const spotRes = await fetchJsonWithTimeout(`http://127.0.0.1:8001/api/stock/hk_spot?symbol=${resolution.symbol}`, 7000).catch(() => ({ success: false }));
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
            currency: 'HKD',
            fullExchangeName: 'HK',
            marketState: 'REGULAR',
            source: 'AkShare (Local Python API)'
          };
          source = 'AkShare (Local Python API)';
        }
      } catch(e) {
        logDebug('AkShare HK Fetch failed', e instanceof Error ? e.message : String(e));
      }
    }

    // Step 2: Fallback or Non-A-Share: Use Python Yahoo Proxy
    if (!result || result.regularMarketPrice === 0 || result.regularMarketPrice === undefined) {
      try {
        const symWithSuffix = appendMarketSuffix(resolution.symbol, resolution.market);
        const pythonQuote = await axios.get(`${PYTHON_SERVICE_URL}/api/market/quote/${symWithSuffix}`);
        if (pythonQuote.data.success && pythonQuote.data.data) {
           result = pythonQuote.data.data;
           source = 'Yahoo Finance (via Python MS)';
        }
      } catch (e) {
        logDebug('Python Quote Fallback failed', e instanceof Error ? e.message : String(e));
      }
      
      // If Python fails, last resort local legacy yf
      if (!result) {
        const yahooResult = await tryQuoteEx(resolution.symbol, input, resolution.market, isDebug);
        if (yahooResult) {
            result = yahooResult;
            if (isDebug) logDebug('REALTIME', `Resolved ${resolution.symbol} via Legacy Local Yahoo: ${result.regularMarketPrice}`);
        }
      }

      // If Yahoo fails or returns 0/undefined for HK, try Sina HK Fallback
      if ((!result || !result.regularMarketPrice) && resolution.market === 'HK-Share') {
        logDebug('HK_FALLBACK', `All sources returned 0 for HK stock ${resolution.symbol}. Attempting Sina fallback...`);
        const hkFallback = await fetchHKSpotFallbackFromSina(resolution.symbol);
        if (hkFallback && hkFallback.regularMarketPrice > 0) {
          logDebug('HK_FALLBACK', `Sina fallback SUCCEEDED for ${resolution.symbol}: ${hkFallback.regularMarketPrice}`);
          result = hkFallback;
          source = hkFallback.source;
        }
      }

      if (result) {
        // Fetch indicators for result (could be Yahoo or Sina HK) if not already fetched
        if (!indicators) {
           try {
              // Indicators still best fetched via Yahoo Chart or similar
              // Fetch technical indicators/history via Python Proxy
              const pythonHist = await axios.get(`${PYTHON_SERVICE_URL}/api/market/history/${symWithSuffix}?period=120d&interval=1d`);
              
              if (pythonHist.data.success && pythonHist.data.data.length > 0) {
                const history = pythonHist.data.data;
                const prices = history.map((q: any) => q.Close).filter((p: any) => p != null);
                const volumes = history.map((q: any) => q.Volume).filter((v: any) => v != null);
                const highs = history.map((q: any) => q.High).filter((h: any) => h != null);
                const lows = history.map((q: any) => q.Low).filter((l: any) => l != null);

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
    const emResponse = await fetch(`https://suggest.eastmoney.com/suggest/default.aspx?name=cb&input=${encodedInput}`, { signal: AbortSignal.timeout(3000) });
    const emText = await emResponse.text();
    // Support both string style: var cb="..." and array style: var cb=[...]
    const emMatch = emText.match(/var cb\s*=\s*"(.*)"/) || emText.match(/var cb\s*=\s*(\[.*\])/);
    if (emMatch?.[1]) {
      const matched = emMatch[1];
      const isArrayStyle = matched.startsWith('[');
      const data = isArrayStyle ? JSON.parse(matched) : matched.split(';').filter(Boolean);
      
      if (Array.isArray(data) && data.length > 0) {
        let bestMatch = null;
        for (const item of data) {
          const parts = isArrayStyle ? item.split(',') : item.split(',');
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
        const result = await yf.quote(symWithSuffix);
        if (result) return result;
    } catch {}

    try {
        const search = await yf.search(input);
        if (search?.quotes?.length) {
            return await yf.quote(search.quotes[0].symbol as any);
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
