import { describe, it, expect, vi, beforeEach } from 'vitest';
import express from 'express';
import request from 'supertest';
import stockRoutes from '../stockRoutes';

import axios from 'axios';
vi.mock('axios');
const mockedAxios = axios as vi.Mocked<typeof axios>;

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
    })
  };
  
  return {
    default: class {
      constructor() {
        return mockInstance;
      }
      setOptions = mockInstance.setOptions;
      quote = mockInstance.quote;
    }
  };
});

const app = express();
app.use(express.json());
app.use('/api', stockRoutes); 

describe('stockRoutes /api/stock/realtime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should prioritize AkShare HK Spot for HK-Share and fallback to Yahoo if AkShare fails', async () => {
    mockedAxios.get.mockImplementation(async (url: string) => {
      if (url.includes('/api/stock/hk_spot')) {
        return { status: 500 };
      }
      return { 
        status: 200, 
        data: { success: true, data: { status: 'ok' } } // mock for sina fallback if it was axios
      };
    });
    // @ts-ignore
    global.fetch = vi.fn().mockResolvedValue({ 
      text: async () => 'var hq_str_rt_hk00700="腾讯控股,400.0,400.0,..."' 
    });

    const res = await request(app).get('/api/stock/realtime?symbol=00700&market=HK-Share');
    
    expect(res.status).toBe(200);
    expect(res.body.source).toContain('Yahoo');
  });

  it('should use AkShare HK Spot if it succeeds', async () => {
    // Mock fetch for the internal call to Python service
    // @ts-ignore
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          "代码": "00700",
          "名称": "腾讯控股",
          "最新价": 412.5,
          "涨跌幅": 1.2,
          "成交量": 12345,
          "昨收": 400
        }
      })
    });

    const res = await request(app).get('/api/stock/realtime?symbol=00700&market=HK-Share');
    
    expect(res.status).toBe(200);
    expect(res.body.source).toBe('AkShare (Local Python API)');
    expect(res.body.price).toBe(412.5);
  });
});
