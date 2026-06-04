import { describe, it, expect, vi, beforeEach, type Mocked } from 'vitest';
import express from 'express';
import request from 'supertest';
import stockRoutes from '../stockRoutes';

import axios from 'axios';
vi.mock('axios');
const mockedAxios = axios as Mocked<typeof axios>;

vi.mock('yahoo-finance2', () => {
  const mockInstance = {
    setOptions: vi.fn(),
    quote: vi.fn(async (symbol) => {
      if (symbol === '00700.Fail') {
        throw new Error('Yahoo Fails');
      }
      return {
        regularMarketPrice: 400.0,
        regularMarketChange: 5.0,
        regularMarketChangePercent: 1.25,
        currency: 'HKD'
      };
    }),
    search: vi.fn(async () => ({ quotes: [] }))
  };
  
  return {
    default: class {
      constructor() {
        return mockInstance;
      }
      setOptions = mockInstance.setOptions;
      quote = mockInstance.quote;
      search = mockInstance.search;
    }
  };
});

const app = express();
app.use(express.json());
app.use('/api', stockRoutes); 

describe('stockRoutes /api/stock/realtime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it('should return valid data for HK-Share symbol', async () => {
    // This test verifies the realtime endpoint returns a valid response
    // for HK-Share symbols, regardless of which data source wins.
    // The source depends on Python microservice availability at test time.
    
    // Mock fetch for all internal calls
    const originalFetch = global.fetch;
    // @ts-ignore
    global.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      
      // EastMoney suggest API — return empty
      if (urlStr.includes('suggest.eastmoney.com') || urlStr.includes('suggest3.sinajs')) {
        return { ok: true, text: async () => 'var cb=""', arrayBuffer: async () => new ArrayBuffer(0) };
      }
      
      // Python HK spot
      if (urlStr.includes('127.0.0.1:8001') && urlStr.includes('hk_spot')) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: {
              "代码": "00700",
              "名称": "腾讯控股",
              "最新价": 412.5,
              "涨跌额": 12.5,
              "涨跌幅": 1.2,
              "昨收": 400,
              "今开": 402,
              "最高": 415,
              "最低": 399,
              "成交量": 12345
            }
          })
        };
      }
      
      // Default fallback
      return { ok: false, status: 404, text: async () => 'Not Found' };
    });

    // Mock axios to avoid real network calls
    mockedAxios.get.mockRejectedValue(new Error('Not available'));

    try {
      const res = await request(app).get('/api/stock/realtime?symbol=00700&market=HK-Share');
      
      expect(res.status).toBe(200);
      expect(res.body.price).toBeDefined();
      expect(res.body.price).toBeGreaterThan(0);
    } finally {
      global.fetch = originalFetch;
    }
  });

  it('should return 400 for empty symbol', async () => {
    const res = await request(app).get('/api/stock/realtime?symbol=&market=HK-Share');
    expect(res.status).toBe(400);
  });

  it('should return 400 for invalid symbol format', async () => {
    const res = await request(app).get('/api/stock/realtime?symbol=<script>&market=HK-Share');
    expect(res.status).toBe(400);
  });
});
