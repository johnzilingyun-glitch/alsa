import type { SectorAnalysis, Recommendation, TechnicalIndicators } from './analysis';

export type Market = "A-Share" | "HK-Share" | "US-Share";
export interface StockInfo {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  market: Market;
  currency: string;
  lastUpdated: string;
  previousClose: number;
  dailyHigh?: number;
  dailyLow?: number;
  dataFreshness?: string; // Timestamp from MCP/API
  dataSource?: string; // e.g. "FMP", "Bloomberg"
  sourceWeight?: number; // 0.0 - 1.0
  dataQuality?: DataQuality;
  technicalIndicators?: TechnicalIndicators;
  fundamentalScores?: any;
  intrinsicValueEstimate?: number;
  pe?: number;
  pb?: number;
  dividendYield?: number;
}

export interface DataQuality {
  score: number; // 0-100
  lastSync: string;
  sourcePriority: "Official API" | "Search/Scraped" | "AI Estimated";
  isStale: boolean;
  missingFields: string[];
}

export interface NewsItem {
  title: string;
  source: string;
  time: string;
  url: string;
  summary: string;
}

export interface IndexInfo {
  name: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  previousClose: number;
}

export interface CommodityAnalysis {
  name: string;
  trend: string;
  expectation: string;
}

export interface MarketOverview {
  id?: string;
  generatedAt?: number;
  market?: string;
  indices: IndexInfo[];
  topNews: NewsItem[];
  sectorAnalysis: SectorAnalysis[];
  commodityAnalysis: CommodityAnalysis[];
  recommendations: Recommendation[];
  marketSummary: string;
}

export interface StockFundamentals {
  // Original
  pe: string;
  pb: string;
  roe: string;
  eps: string;
  revenueGrowth: string;
  valuationPercentile: string;
  netProfitGrowth?: string;
  debtToEquity?: string;
  grossMargin?: string;
  netMargin?: string;
  dividendYield?: string;
  // New
  marketCap?: string;
  revenue?: string;
  netProfit?: string;
  nonGaapNetProfit?: string;
  dividend?: string;
}

export interface FundamentalTableItem {
  indicator: string;
  value: string;
  consensus: string;
  deviation: string;
  remark: string;
}

export interface IndustryAnchor {
  variable: string;
  currentValue: string;
  weight: string;
  monthlyChange: string;
  logic: string;
}

export interface HistoricalData {
  yearHigh: string;
  yearLow: string;
  majorEvents: string[];
}

export interface ValuationAnalysis {
  comparison: string;
  marginOfSafetySummary: string;
}
