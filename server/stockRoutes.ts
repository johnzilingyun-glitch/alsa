import { Router } from 'express';
import { yf } from './lib/yahooFinance.js';
import axios from 'axios';
import { monitor } from './dataSourceHealth.js';
import { logDebug, logError } from './stockLogger.js';
import fs from 'fs';
import path from 'path';
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

import { getPythonAuthHeaders } from './securityConfig.js';

async function fetchJsonWithTimeout(url: string, timeoutMs = 8000, options: RequestInit = {}): Promise<any> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { 
      ...options,
      signal: controller.signal,
      headers: { ...getPythonAuthHeaders(), ...options.headers }
    });
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
  
  // Sina returns GBK-encoded text, decode properly
  const buffer = await response.arrayBuffer();
  const text = new TextDecoder('gbk').decode(buffer);
  
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
    
    // Sina returns GBK-encoded text, decode properly
    const buffer = await response.arrayBuffer();
    const text = new TextDecoder('gbk').decode(buffer);
    
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

async function fetchIndicesFromSinaFallback(market: string): Promise<any[] | null> {
  const INDEX_SINA_MAP: Record<string, Array<{ sinaCode: string; name: string }> | null> = {
    'A-Share': [
      { sinaCode: 'sh000001', name: '上证指数' },
      { sinaCode: 'sz399001', name: '深证成指' },
      { sinaCode: 'sz399006', name: '创业板指' },
    ],
    'HK-Share': [
      { sinaCode: 'hkHSI', name: '恒生指数' },
      { sinaCode: 'hkHSTECH', name: '恒生科技' },
      { sinaCode: 'hkHSCEI', name: '恒生国企' },
      { sinaCode: 'hkHSCCI', name: '红筹指数' },
    ],
    'US-Share': null,
  };

  const indices = INDEX_SINA_MAP[market];
  if (!indices) return null;

  const sinaCodes = indices.map(i => i.sinaCode).join(',');
  const url = `https://hq.sinajs.cn/list=${sinaCodes}`;

  try {
    const response = await fetch(url, {
      headers: { Referer: 'https://finance.sina.com.cn' }
    });
    const buffer = await response.arrayBuffer();
    const text = new TextDecoder('gbk').decode(buffer);

    const results: any[] = [];
    for (const idx of indices) {
      const regex = new RegExp(`${idx.sinaCode}="([^"]*)"`);
      const match = text.match(regex);
      if (!match?.[1]) continue;

      const parts = match[1].split(',');
      if (parts.length < 10) continue;

      if (market === 'HK-Share') {
        const name = parts[1] || idx.name;
        const price = Number(parts[6]);
        const prevClose = Number(parts[3]);
        const change = Number(parts[7]);
        const changePercent = Number(parts[8]);
        if (!price || price === 0) continue;
        results.push({ symbol: idx.sinaCode.replace('hk', '^'), name, price, change, changePercent });
      } else {
        const name = parts[0] || idx.name;
        const open = Number(parts[1]);
        const prevClose = Number(parts[2]);
        const price = Number(parts[3]);
        const high = Number(parts[4]);
        const low = Number(parts[5]);
        if (!price || price === 0) continue;
        const change = Number.isFinite(prevClose) ? price - prevClose : 0;
        const changePercent = Number.isFinite(prevClose) && prevClose !== 0 ? (change / prevClose) * 100 : 0;
        results.push({
          symbol: idx.sinaCode.replace('sh', '').replace('sz', ''),
          name,
          price,
          change: parseFloat(change.toFixed(2)),
          changePercent: parseFloat(changePercent.toFixed(2))
        });
      }
    }

    return results.length > 0 ? results : null;
  } catch (e) {
    console.warn(`[SinaIndicesFallback] Failed for ${market}:`, e);
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

// Market Dashboard — single aggregated endpoint (no AI, pure data)
router.get('/market/dashboard', async (req, res) => {
  const market = (req.query.market as string) || 'A-Share';
  const cacheKey = `dashboard_${market}`;
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const resp = await axios.get(`${PYTHON_SERVICE_URL}/api/market/dashboard?market=${encodeURIComponent(market)}`, {
      timeout: 15000,
      headers: getPythonAuthHeaders(),
    });
    if (resp.data.success) {
      setCache(cacheKey, resp.data.data);
      return res.json(resp.data.data);
    }
    throw new Error('dashboard fetch failed');
  } catch (e: any) {
    console.warn('Dashboard aggregation failed, falling back to individual endpoints:', e.message || e);
    // Fallback: assemble from individual routes
    const fetchPy = async (path: string) => {
      try {
        const r = await axios.get(`${PYTHON_SERVICE_URL}${path}`, { timeout: 8000, headers: getPythonAuthHeaders() });
        return r.data.success ? r.data.data : null;
      } catch { return null; }
    };

    const [indices, commodities, news, sectorFlow, northbound] = await Promise.all([
      fetchPy(`/api/market/indices?market=${market}`),
      fetchPy('/api/market/commodities'),
      fetchPy(`/api/market/news?market=${market}`),
      market !== 'US-Share' ? fetchPy('/api/market/sector_flow') : Promise.resolve(null),
      market === 'A-Share' ? fetchPy('/api/market/northbound') : Promise.resolve(null),
    ]);

    const sf = sectorFlow || { topInflows: [], topOutflows: [] };
    const hotSectors = (sf.topInflows || []).slice(0, 5).map((s: any) => ({
      name: s['行业'] || '', inflow: s['主力净流入-净额'] || 0, changePct: s['涨跌幅'] || 0,
      companyCount: s['公司家数'] || 0, leadStock: s['领涨股'] || '', leadStockPct: s['领涨股-涨跌幅'] || 0,
    }));
    const recommendations = (sf.topInflows || [])
      .filter((s: any) => (s['涨跌幅'] || 0) > 0).slice(0, 3)
      .map((s: any) => ({ type: 'Sector', name: s['行业'] || '', reason: `主力净流入${((s['主力净流入-净额'] || 0) / 1e8).toFixed(2)}亿，涨跌幅${s['涨跌幅'] || 0}%` }));

    const fallbackData = {
      indices: indices || [], commodities: commodities || [], news: news || [],
      sectorFlow: sf, northbound: northbound || [], hotSectors, recommendations,
      updatedAt: new Date().toISOString(),
    };
    
    // Only cache if we actually have some data
    if (fallbackData.indices.length > 0) {
      setCache(cacheKey, fallbackData);
    }
    
    return res.json(fallbackData);
  }
});

// Market Indices
const INDEX_NAME_MAP: Record<string, string> = {
  '000001.SS': '上证指数',
  '399001.SZ': '深证成指',
  '399006.SZ': '创业板指',
  '000300.SS': '沪深300',
  '^HSI': '恒生指数',
  '^HSTECH': '恒生科技',
  '^HSCE': '恒生国企',
  '^HSCCI': '红筹指数',
  '^GSPC': '标普500',
  '^IXIC': '纳斯达克',
  '^DJI': '道琼斯',
};

// ── THS (同花顺) Proxy ──────────────────────────────────────
router.get('/ths/*', async (req, res) => {
  const pyPath = req.path;  // e.g. /ths/search
  const qs = new URLSearchParams(req.query as any).toString();
  const url = `${PYTHON_SERVICE_URL}/api${pyPath}${qs ? '?' + qs : ''}`;
  try {
    const resp = await axios.get(url, {
      timeout: 20000,
      headers: getPythonAuthHeaders(),
    });
    res.json(resp.data);
  } catch (e: any) {
    const msg = e?.response?.data?.error?.message || e?.message || 'THS proxy failed';
    res.status(502).json({ success: false, error: { code: 'THS_PROXY_ERROR', message: msg } });
  }
});

router.get('/stock/indices', async (req, res) => {
  const { market } = req.query;
  const marketKey = (market as string) || 'A-Share';
  const cacheKey = `indices_${marketKey}`;
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const startTime = Date.now();
    // Proxy to Python Microservice (4s timeout to avoid blocking UI)
    const pythonRes = await axios.get(`${PYTHON_SERVICE_URL}/api/market/indices?market=${marketKey}`, { 
      timeout: 4000,
      headers: getPythonAuthHeaders()
    });
    
    if (pythonRes.data.success && Array.isArray(pythonRes.data.data) && pythonRes.data.data.length > 0) {
      const validData = pythonRes.data.data.filter((d: any) => !d.error && d.price != null && d.price !== 0);
      if (validData.length > 0) {
        const data = validData.map((d: any) => ({
          ...d,
          name: INDEX_NAME_MAP[d.symbol] || d.name
        }));
        setCache(cacheKey, data);
        monitor.recordSuccess('python_market', Date.now() - startTime);
        return res.json(data);
      }
    }
    throw new Error('Python indices fetch failed or empty');
  } catch (error) {
    monitor.recordFailure('python_market');
    console.warn(`Indices fetch error for ${marketKey} (falling back to legacy yf):`, error.response ? error.response.data : error.message);
    
    // Legacy fallback (preserving minimal safety)
    try {
        const symbols = marketKey === 'HK-Share' ? ['^HSI', '^HSTECH', '^HSCE', '^HSCCI'] : 
                        marketKey === 'US-Share' ? ['^GSPC', '^IXIC', '^DJI'] : 
                        ['000001.SS', '399001.SZ', '399006.SZ'];
        const results = await yf.quote(symbols as any);
        if (results && results.length > 0) {
          const mappedResults = results.map(r => ({
            symbol: r.symbol,
            name: INDEX_NAME_MAP[r.symbol] || r.shortName || r.longName || r.symbol,
            price: r.regularMarketPrice,
            change: r.regularMarketChange,
            changePercent: r.regularMarketChangePercent
          }));
          return res.json(mappedResults);
        }
        throw new Error('Local Yahoo Finance also failed');
    } catch (e) {
        console.warn('Yahoo Finance also failed, trying Sina fallback...');
        const sinaFallback = await fetchIndicesFromSinaFallback(marketKey).catch(() => null);
        if (sinaFallback) {
          setCache(cacheKey, sinaFallback);
          return res.json(sinaFallback);
        }

        console.error('CRITICAL: All indices sources failed. Returning stale defaults.');
        const defaults = marketKey === 'HK-Share' ? [
          { symbol: '^HSI', name: '恒生指数', price: 0, change: 0, changePercent: 0, status: 'stale' },
          { symbol: '^HSTECH', name: '恒生科技', price: 0, change: 0, changePercent: 0, status: 'stale' },
          { symbol: '^HSCE', name: '恒生国企', price: 0, change: 0, changePercent: 0, status: 'stale' },
          { symbol: '^HSCCI', name: '红筹指数', price: 0, change: 0, changePercent: 0, status: 'stale' }
        ] : marketKey === 'US-Share' ? [
          { symbol: '^GSPC', name: '标普500', price: 0, change: 0, changePercent: 0, status: 'stale' },
          { symbol: '^IXIC', name: '纳斯达克', price: 0, change: 0, changePercent: 0, status: 'stale' },
          { symbol: '^DJI', name: '道琼斯', price: 0, change: 0, changePercent: 0, status: 'stale' }
        ] : [
          { symbol: '000001.SS', name: '上证指数', price: 0, change: 0, changePercent: 0, status: 'stale' },
          { symbol: '399001.SZ', name: '深证成指', price: 0, change: 0, changePercent: 0, status: 'stale' },
          { symbol: '399006.SZ', name: '创业板指', price: 0, change: 0, changePercent: 0, status: 'stale' }
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
    const pythonRes = await axios.get(`http://127.0.0.1:8001/api/market/commodities`, { 
      timeout: 5000,
      headers: getPythonAuthHeaders()
    });
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
          const searchPromise = yf.search(symbolKey, { newsCount: 8 });
          const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error('Yahoo Search Timeout')), 4000));
          const searchResult = await Promise.race([searchPromise, timeoutPromise]) as any;
          
          const items = (searchResult?.news || []).map((n: any) => ({
            title: n.title,
            url: n.link,
            time: new Date(n.providerPublishTime).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
            timestamp: new Date(n.providerPublishTime).getTime(),
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
          signal: AbortSignal.timeout(4000),
          headers: getPythonAuthHeaders()
        });
        if (pythonRes.ok) {
          const pythonData = await pythonRes.json();
          const items = (pythonData.success && pythonData.data) ? pythonData.data : [];
          // Python MS doesn't return timestamp, generate it from 'time'
          items.forEach((item: any) => {
             item.timestamp = new Date(item.time.replace(/\//g, '-')).getTime();
          });
          logDebug('performance', { source: 'python_news', latency: Date.now() - start, count: items.length });
          return items;
        }
      } catch (e) {
        logDebug('warning', `Python News MS slow or unavailable: ${e}`);
      }
      return [];
    })());

    // 2. Sina News API (replaces deprecated RSS)
    if (marketKey === 'A-Share' || marketKey === 'HK-Share') {
      fetchTasks.push((async () => {
        const start = Date.now();
        try {
          const lid = marketKey === 'HK-Share' ? '2517' : '2516';
          const sinaUrl = `https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=${lid}&num=10&page=1`;
          const res = await fetch(sinaUrl, {
            headers: { 'Referer': 'https://finance.sina.com.cn' },
            signal: AbortSignal.timeout(4000)
          });
          const json = await res.json();
          const data = json?.result?.data || [];
          const items = data.slice(0, 8).map((item: any) => ({
            title: item.title,
            url: item.url,
            time: item.ctime ? new Date(item.ctime * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '',
            timestamp: item.ctime ? item.ctime * 1000 : 0,
            source: 'Sina Finance'
          }));
          logDebug('performance', { source: 'sina_news_api', latency: Date.now() - start, count: items.length });
          return items;
        } catch (e) {
          logError(e, 'Sina News API Failed');
          return [];
        }
      })());
    }

    // 3. Global Google News Fallback (Parallel with others)
    fetchTasks.push((async () => {
      const start = Date.now();
      try {
        const query = marketKey === 'A-Share' ? 'A股+股市' : marketKey === 'HK-Share' ? '港股+股市' : '美股+股市';
        const axios = (await import('axios')).default;
        const gnewsUrl = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans`;
        const response = await axios.get(gnewsUrl, {
          headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' },
          timeout: 3500
        });
        
        const text = response.data;
        const itemRegex = /<item>[\s\S]*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/title>[\s\S]*?<link>(.*?)<\/link>[\s\S]*?<pubDate>(.*?)<\/pubDate>[\s\S]*?<source.*?>(.*?)<\/source>[\s\S]*?<\/item>/g;
        let match;
        const items = [];
        while ((match = itemRegex.exec(text)) !== null && items.length < 5) {
          const pubDate = new Date(match[3]);
          items.push({
            title: match[1].replace(/<!\[CDATA\[|\]\]>/g, '').trim(),
            url: match[2].trim(),
            time: pubDate.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
            timestamp: pubDate.getTime(),
            source: match[4].trim() || 'Google News'
          });
        }
        logDebug('performance', { source: 'google_news', latency: Date.now() - start, count: items.length });
        return items;
      } catch (e) {
        return [];
      }
    })());

    const results = await Promise.all(fetchTasks);
    results.forEach(batch => news.push(...batch));

    // Sort by timestamp DESC (newest first)
    news.sort((a, b) => b.timestamp - a.timestamp);

    // De-duplicate by title
    const uniqueNews = Array.from(new Map(news.map(item => [item.title, item])).values()).slice(0, 10);
    
    // Clean up internal timestamp property before sending to client
    const finalNews = uniqueNews.map(({ timestamp, ...rest }) => rest);
    
    logDebug('performance', { endpoint: '/stock/news', totalLatency: Date.now() - startTime, finalCount: finalNews.length });
    
    setCache(cacheKey, finalNews);
    res.json(finalNews);
  } catch (error) {
    console.error('News fetch error:', error);
    res.status(500).json({ error: 'Failed to fetch news data' });
  }
});

// Trending Search
router.get('/stock/trending', async (req, res) => {
  const market = req.query.market as string || 'A-Share';
  const cacheKey = `trending_${market}`;
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    let symbols = [];
    if (market === 'A-Share') {
      // CSI 300 Components
      symbols = ['600519', '300750', '601318', '600036', '000858', '601012', '002594', '600900', '601166', '000333', '601899', '600030', '000001', '600276', '601398', '601288', '600919', '002415', '000568', '601816', '601988', '600887', '600028', '601088', '002304', '601628', '601857', '601601', '600048', '300059', '601888', '300122', '000002', '002714', '603259', '601138', '002475', '601668', '601328', '601939', '600016', '000651', '603288', '002142', '002271', '600104', '601319', '001979', '300760', '002812'];
    } else if (market === 'HK-Share') {
      // Hang Seng Index Components
      symbols = ['0700', '3690', '9988', '1299', '0941', '0883', '0005', '0388', '9618', '1810', '9999', '1024', '1211', '0857', '2015', '0011', '0002', '0016', '1928', '0027', '0823', '0001', '2318', '3968', '0939', '1398', '3988', '0267', '2388', '1109', '0003', '0006', '0836', '1038', '1044', '1113', '0012', '0017', '0066', '0101', '0288', '0386', '0688', '0762', '0868', '1088', '1093', '1177', '1997', '2007', '2269', '2313', '2319', '2382'];
    } else {
      // Nasdaq 100 Components
      symbols = ['NVDA', 'TSLA', 'AAPL', 'MSFT', 'AMD', 'AMZN', 'META', 'GOOGL', 'GOOG', 'SMCI', 'COIN', 'PLTR', 'ARM', 'MU', 'AVGO', 'MSTR', 'NFLX', 'INTC', 'CSCO', 'CMCSA', 'PEP', 'ADBE', 'COST', 'TXN', 'AMGN', 'TMUS', 'QCOM', 'HON', 'INTU', 'ISRG', 'SBUX', 'GILD', 'MDLZ', 'AMAT', 'BKNG', 'ADI', 'ADP', 'VRTX', 'REGN', 'PANW', 'SNPS', 'KLAC', 'CDNS', 'CRWD', 'MAR', 'CTAS', 'LRCX', 'NXPI', 'CSX', 'ORLY', 'MELI', 'PCAR', 'MNST', 'FTNT', 'WDAY', 'KDP', 'ROST'];
    }

    const pythonRes = await fetch(`http://127.0.0.1:8001/api/market/quotes?symbols=${symbols.join(',')}`, { 
      signal: AbortSignal.timeout(15000),
      headers: getPythonAuthHeaders()
    });
    
    if (!pythonRes.ok) throw new Error('Failed to fetch quotes for trending');
    
    const pyData = await pythonRes.json();
    const quotes = pyData.success && pyData.data ? pyData.data : [];
    
    // Calculate volume ratio (异常放量程度) or fallback to turnover/volume
    quotes.forEach((q: any) => {
      if (q.volume && q.averageVolume) {
        q.volumeRatio = q.volume / q.averageVolume;
      } else {
        q.volumeRatio = q.volume ? q.volume / 1000000 : 0; // fallback arbitrary sorting
      }
    });

    const sorted = quotes.sort((a: any, b: any) => (b.volumeRatio || 0) - (a.volumeRatio || 0)).slice(0, 4);
    
    const results = sorted.map((q: any) => ({
      symbol: q.symbol,
      name: q.name,
      market: market,
      changePercent: q.changePercent
    }));
    
    setCache(cacheKey, results);
    res.json(results);
  } catch (error) {
    console.error('Trending fetch error:', error);
    // Fallback if failing
    res.json(
      market === 'A-Share' ? [
        { symbol: '600519', name: '贵州茅台', market: 'A-Share', changePercent: 0 },
        { symbol: '300750', name: '宁德时代', market: 'A-Share', changePercent: 0 },
        { symbol: '601318', name: '中国平安', market: 'A-Share', changePercent: 0 },
        { symbol: '002594', name: '比亚迪', market: 'A-Share', changePercent: 0 }
      ] : market === 'HK-Share' ? [
        { symbol: '0700', name: '腾讯控股', market: 'HK-Share', changePercent: 0 },
        { symbol: '3690', name: '美团-W', market: 'HK-Share', changePercent: 0 },
        { symbol: '9988', name: '阿里巴巴-SW', market: 'HK-Share', changePercent: 0 },
        { symbol: '0883', name: '中国海洋石油', market: 'HK-Share', changePercent: 0 }
      ] : [
        { symbol: 'NVDA', name: '英伟达', market: 'US-Share', changePercent: 0 },
        { symbol: 'TSLA', name: '特斯拉', market: 'US-Share', changePercent: 0 },
        { symbol: 'AAPL', name: '苹果', market: 'US-Share', changePercent: 0 },
        { symbol: 'MSFT', name: '微软', market: 'US-Share', changePercent: 0 }
      ]
    );
  }
});
// ── Disk-persisted cache for sector flow ─────────────────────────
const SECTOR_DISK_PATH = path.join(process.cwd(), 'data', 'sector_flow_cache.json');
function loadSectorDiskCache(): { topInflows: any[]; topOutflows: any[] } | null {
  try { return JSON.parse(fs.readFileSync(SECTOR_DISK_PATH, 'utf-8')); } catch { return null; }
}
function saveSectorDiskCache(data: { topInflows: any[]; topOutflows: any[] }) {
  try { fs.mkdirSync(path.dirname(SECTOR_DISK_PATH), { recursive: true }); fs.writeFileSync(SECTOR_DISK_PATH, JSON.stringify(data)); } catch {}
}

// Institutional Sector Flows (Python Microservice Proxy)
router.get('/stock/sectors', async (req, res) => {
  const cacheKey = 'sector_flow';
  const cached = getCached(cacheKey);
  if (cached) return res.json(cached);

  try {
    const data = await fetchJsonWithTimeout('http://127.0.0.1:8001/api/market/sector_flow', 15000);

    if (data.success && data.data) {
      const flowData = data.data;
      for (const rec of [...(flowData.topInflows || []), ...(flowData.topOutflows || [])]) {
        if (rec['涨跌幅'] == null) rec['涨跌幅'] = 0;
        if (rec['主力净流入-净额'] == null) rec['主力净流入-净额'] = 0;
      }
      setCache(cacheKey, flowData);
      saveSectorDiskCache(flowData);
      return res.json(flowData);
    }
    throw new Error('Python API returned success: false or empty data');
  } catch (error) {
    console.warn('Sector flow fetch error (is Python backend running?):', error);
    const fallback = await fetchSectorFlowFromEastMoneyFallback().catch(() => null);
    if (fallback) {
      setCache(cacheKey, fallback);
      saveSectorDiskCache(fallback);
      return res.json(fallback);
    }
    const diskCache = loadSectorDiskCache();
    if (diskCache && diskCache.topInflows?.length) {
      setCache(cacheKey, diskCache);
      return res.json(diskCache);
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
    const data = await fetchJsonWithTimeout('http://127.0.0.1:8001/api/market/northbound', 15000);
    
    if (data.success && data.data) {
      setCache(cacheKey, data.data);
      return res.json(data.data);
    }
    throw new Error('Python API returned success: false or empty data');
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
    try {
      const emUrl = `https://suggest.eastmoney.com/suggest/default.aspx?name=cb&input=${encodedInput}`;
      const rawRes = await fetch(emUrl, { 
        signal: AbortSignal.timeout(4000),
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
      }).catch(() => null);
      
      const text = rawRes ? await rawRes.text() : '';

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
        const sinaRes = await fetch(sinaUrl, { 
          signal: AbortSignal.timeout(4000),
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn/'
          }
        }).catch(() => null);
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
  const { symbol, market, symbols, debug, force } = req.query;
  const isDebug = debug === 'true';
  const isForce = force === 'true';

  const cacheKey = symbols ? `batch:${symbols}` : `${market}:${symbol}`;
  if (!isForce && !isDebug) {
    const cached = getCached(cacheKey);
    if (cached) {
      console.log(`[CACHE HIT] ${cacheKey}`);
      return res.json(cached);
    }
  }

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
      const formatted = results.map(r => formatQuoteResult(r));
      setCache(cacheKey, formatted);
      return res.json(formatted);
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

    // Use Unified Python DataRouter for ALL markets
    try {
      const symWithSuffix = appendMarketSuffix(resolution.symbol, resolution.market);
      const [spotRes, histRes, finRes, techRes] = await Promise.all([
        axios.get(`${PYTHON_SERVICE_URL}/api/market/quote/${resolution.symbol}?market=${resolution.market}`, {
          headers: getPythonAuthHeaders(),
          timeout: 7000
        }).catch(() => null),
        axios.get(`${PYTHON_SERVICE_URL}/api/market/history/${symWithSuffix}?period=120d&interval=1d`, {
          headers: getPythonAuthHeaders(),
          timeout: 9000
        }).catch(() => null),
        axios.get(`${PYTHON_SERVICE_URL}/api/stock/comprehensive_financials?symbol=${resolution.symbol}&market=${resolution.market}`, {
          headers: getPythonAuthHeaders(),
          timeout: 8000
        }).catch(() => null),
        axios.get(`${PYTHON_SERVICE_URL}/api/technicals/${symWithSuffix}`, {
          headers: getPythonAuthHeaders(),
          timeout: 9000
        }).catch(() => null)
      ]);

      if (spotRes && spotRes.data && spotRes.data.success && spotRes.data.data) {
        const d = spotRes.data.data;
        result = {
          symbol: d.symbol,
          shortName: d.name,
          regularMarketPrice: d.price,
          regularMarketChange: d.change,
          regularMarketChangePercent: d.changePercent || d.change_percent,
          regularMarketPreviousClose: d.previousClose || d.previous_close,
          regularMarketOpen: d.open,
          regularMarketDayHigh: d.dayHigh || d.day_high,
          regularMarketDayLow: d.dayLow || d.day_low,
          regularMarketVolume: d.volume,
          marketCap: d.marketCap || d.market_cap,
          trailingPE: d.trailingPE || d.trailing_pe,
          currency: d.currency || (resolution.market === 'A-Share' ? 'CNY' : resolution.market === 'HK-Share' ? 'HKD' : 'USD'),
          fullExchangeName: resolution.market === 'A-Share' ? 'CN' : resolution.market === 'HK-Share' ? 'HK' : 'US',
          marketState: 'REGULAR'
        };
        source = 'Unified Market Data (Python MS)';

        if (finRes && finRes.data && finRes.data.success && finRes.data.data) {
          const f = finRes.data.data;
          result.fundamentals = {
            marketCap: f.marketCap,
            pe: f.pe,
            pb: f.pb,
            roe: f.roe,
            grossMargin: f.grossMargin,
            revenue: f.revenue,
            netProfit: f.netProfit,
            netProfitGrowth: f.netProfitGrowth,
            dividend: f.dividend,
            dividendYield: f.dividendYield,
            valuationPercentile: f.valuationPercentile,
            valuationExplanation: f.valuationExplanation
          };

          const pe = parseFloat(f.pe) || 0;
          const pb = parseFloat(f.pb) || 0;
          const roe = parseFloat(f.roe) || 12;
          const growth = parseFloat(f.netProfitGrowth) || 10;
          const margin = parseFloat(f.grossMargin) || 20;
          const debtRatio = parseFloat(f.debtRatio) || 50;
          
          result.fundamentalScores = calculateFundamentalScores({
            pe, pb, roe, grossMargin: margin, netProfitGrowth: growth, debtToEquity: debtRatio / 100
          });
          
          const intrinsicResult = calculateIntrinsicValueEstimate(result.regularMarketPrice, roe, growth);
          result.intrinsicValueEstimate = intrinsicResult.value;
          result.intrinsicValueMethodology = intrinsicResult.methodology;
        }
      }

      if (histRes && histRes.data && histRes.data.success && Array.isArray(histRes.data.data) && histRes.data.data.length > 0) {
        const history = histRes.data.data;
        const prices = history.map((q: any) => q.close || q.Close).filter((p: any) => p != null);
        const volumes = history.map((q: any) => q.volume || q.Volume).filter((v: any) => v != null);
        const highs = history.map((q: any) => q.high || q.High).filter((h: any) => h != null);
        const lows = history.map((q: any) => q.low || q.Low).filter((l: any) => l != null);

        indicators = calcIndicators(prices, volumes, highs, lows, { roundVolume: true });
        
        if (techRes && techRes.data && techRes.data.success && techRes.data.data) {
          const t = techRes.data.data;
          indicators.quantSignals = t;
          if (t.ma5) indicators.ma5 = t.ma5;
          if (t.ma20) indicators.ma20 = t.ma20;
          if (t.ma60) indicators.ma60 = t.ma60;
        }

        if (prices.length > 0) {
           const annVol = calculateVolatility(prices, 60);
           const volLimit = calculateVolatilityAdjustedLimit(annVol);
           indicators.riskMetrics = {
             annualizedVolatility: annVol,
             maxPositionLimit: volLimit.limit,
             volatilityRegime: volLimit.regime
           };
        }
      }
    } catch (e) {
      logDebug('Unified Fetch failed', e instanceof Error ? e.message : String(e));
    }

    // Fallbacks if Python fails
    if (!result) {
      const yahooResult = await tryQuoteEx(resolution.symbol, input, resolution.market, isDebug);
      if (yahooResult) {
          result = yahooResult;
          if (isDebug) logDebug('REALTIME', `Resolved ${resolution.symbol} via Legacy Local Yahoo: ${result.regularMarketPrice}`);
      }
    }
    if ((!result || !result.regularMarketPrice) && resolution.market === 'HK-Share') {
      logDebug('HK_FALLBACK', `All sources returned 0 for HK stock ${resolution.symbol}. Attempting Sina fallback...`);
      const hkFallback = await fetchHKSpotFallbackFromSina(resolution.symbol).catch(() => null);
      if (hkFallback && hkFallback.regularMarketPrice > 0) {
        result = hkFallback;
        source = hkFallback.source;
      }
    }
    if ((!result || !result.regularMarketPrice) && resolution.market === 'A-Share') {
      const aFallback = await fetchAShareSpotFallbackFromSina(resolution.symbol).catch(() => null);
      if (aFallback && aFallback.regularMarketPrice > 0) {
        result = aFallback;
        source = aFallback.source;
      }
    }

    if (!result) {
      return res.status(404).json({ error: `无法找到代码 "${symbol}" 的相关数据。` });
    }

    const formatted = formatQuoteResult(result);
    if (source) {
      formatted.source = source;
    }

    const finalResponse = {
      ...formatted,
      resolvedMarket: resolution.market,
      technicalIndicators: indicators
    };

    setCache(cacheKey, finalResponse);
    res.json(finalResponse);
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
