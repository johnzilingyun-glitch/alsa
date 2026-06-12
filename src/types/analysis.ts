import type { IndustryAnchor, DataQuality, StockFundamentals, FundamentalTableItem, HistoricalData, NewsItem, StockInfo, ValuationAnalysis } from './market';
import type { BusinessType, AgentRole } from './common';

export interface TechnicalIndicators {
  ma5: number | null;
  ma20: number | null;
  ma60: number | null;
  avgVolume5: number | null;
  avgVolume20: number | null;
  resistanceShort: number | null;
  supportShort: number | null;
  resistanceLong: number | null;
  supportLong: number | null;
  lastClose?: number;
  quantSignals?: any;
  riskMetrics?: RiskMetrics;
}

export interface RiskMetrics {
  annualizedVolatility: number;
  maxPositionLimit: number;
  volatilityRegime: string;
}

export interface SectorAnalysis {
  name: string;
  trend: string;
  rotationStage?: string;
  upstreamImpact?: string;
  downstreamImpact?: string;
  conclusion: string;
}

export interface Recommendation {
  type: "Stock" | "Sector";
  name: string;
  reason: string;
}

export interface TradingPlan {
  entryPrice: string;
  targetPrice: string;
  stopLoss: string;
  strategy: string;
  strategyRisks: string;
  positionPlan?: { price: string; positionPercent: number }[]; // 分层建仓
  logicBasedStopLoss?: string; // 基于逻辑证伪的止损条件
  riskRewardRatio?: number;
}

export interface TradingPlanVersion {
  version: string;
  timestamp: string;
  changeReason: string;
  plan: TradingPlan;
}

export interface StockAnalysis {
  id?: string;
  stockInfo: StockInfo;
  fundamentals?: StockFundamentals;
  historicalData?: HistoricalData;
  valuationAnalysis?: ValuationAnalysis;
  news: NewsItem[];
  summary: string;
  technicalAnalysis: string;
  technicalIndicators?: TechnicalIndicators;
  fundamentalAnalysis: string;
  fundamentalTable?: FundamentalTableItem[];
  industryAnchors?: IndustryAnchor[];
  sentiment: "Bullish" | "Bearish" | "Neutral";
  score: number;
  recommendation: "Buy" | "Overweight" | "Hold" | "Underweight" | "Sell";
  keyRisks: string[];
  keyOpportunities: string[];
  discussion?: AgentMessage[];
  finalConclusion?: string;
  tradingPlan?: TradingPlan;
  tradingPlanHistory?: TradingPlanVersion[];
  scenarios?: Scenario[];
  coreVariables?: CoreVariable[];
  businessModel?: BusinessModel;
  quantifiedRisks?: QuantifiedRisk[];
  riskAdjustedValuation?: number;
  dataQuality?: DataQuality;
  expectedValueOutcome?: ExpectedValueOutcome;
  sensitivityMatrix?: SensitivityMatrixRow[];
  backtestResult?: {
    previousDate: string;
    previousRecommendation: string;
    actualReturn: string;
    learningPoint: string;
  };
  valuationMatrix?: Scenario[];
  stressTestLogic?: string;
  catalystList?: Catalyst[];
  sensitivityFactors?: SensitivityFactor[];
  expectationGap?: ExpectationGap;
  analystWeights?: AnalystWeight[];
  calculations?: CalculationResult[];
  controversialPoints?: string[];
  positionManagement?: {
    layeredEntry: string[];
    sizingLogic: string;
    riskAdjustedStance: string;
  };
  timeDimension?: {
    expectedDuration: string;
    keyMilestones: string[];
    exitTriggers: string[];
  };
  moatAnalysis?: {
    type: string;
    strength: "Wide" | "Narrow" | "None";
    logic: string;
  };
  narrativeConsistency?: {
    score: number; // 0-100
    logic: string;
  };
  cycleAnalysis?: {
    stage: "Early" | "Mid" | "Late" | "Bottom" | "Peak";
    logic: string;
    volatilityRisk: string;
  };
  consensusBiasScore?: number;
  logicFindings?: { role: string; rule: string; severity: string; finding: string }[];
  sotpMatrix?: SegmentValuation[];
  monteCarloData?: {
    p5: number;
    p50: number;
    p95: number;
    distribution: { price: number; probability: number }[];
  };
  institutionalRisk?: {
    beta: number;
    sharpeProxy: number;
    var95: number;
  };
  netNetValue?: number;
  isDeepValue?: boolean;
  verificationMetrics?: {
    indicator: string;
    threshold: string;
    timeframe: string;
    logic: string;
  }[];
  dataVerification?: DataVerification[];
  capitalFlow?: {
    northboundFlow: string;
    institutionalHoldings: string;
    ahPremium?: string;
    marketSentiment: string;
  };
  legendaryInsights?: {
    valueSage?: { marginOfSafety: string; intrinsicValue: string; moatRating: string };
    growthVisionary?: { tamEstimate: string; innovationScore: string; disruptionPotential: string };
    macroTitan?: { macroSignal: string; liquidityStatus: string; systemicRiskLevel: string };
  };
  // Flat fields for expert insight aggregation
  intrinsicValue?: string | number;
  marginOfSafety?: string;
  moatRating?: string;
  tamEstimate?: string;
  innovationScore?: string | number;
  disruptionPotential?: string;
  macroSignal?: string;
  liquidityStatus?: string;
  systemicRiskLevel?: string;
  chatHistory?: { id: string; role: "user" | "ai"; content: string }[];
  extendedMarketData?: any;
}

export interface AgentMessage {
  id?: string;
  role: AgentRole;
  content: string;
  timestamp: string;
  model?: string;
  type?: "discussion" | "research" | "review" | "user_question" | "fact_check";
  references?: { title: string; url: string }[];
  round?: number;
  logicFindings?: { rule: string; severity: string; finding: string }[];
}

export interface Scenario {
  case: "Bull" | "Base" | "Stress";
  probability: number; // 0-100
  keyInputs: string;
  targetPrice: string;
  marginOfSafety: string;
  expectedReturn: string; // e.g. "18%"
  logic: string;
}

export interface Catalyst {
  event: string;
  probability: number;
  impact: string; // e.g. "±5% 股价"
}

export interface SensitivityFactor {
  factor: string; // e.g. "金价"
  change: string; // e.g. "±5%"
  impact: string; // e.g. "±3.2% 目标价"
  logic: string;
  formula?: string; // The standardized formula used
}

export interface SensitivityMatrixRow {
  variable: string;    // e.g. "Silicon Price"
  change: string;      // e.g. "-10%"
  profitImpact: string; // e.g. "-1.2B CNY"
  timeLag: string;     // e.g. "Immediate" vs "18-24mo"
}

export interface ExpectedValueOutcome {
  expectedPrice: number;
  calculationLogic: string; // "Σ(P_i * Price_i)"
  confidenceInterval: string; // e.g. "[25, 30]"
}

export interface ExpectationGap {
  marketConsensus: string;
  ourView: string;
  gapReason: string; // Alpha source explanation
  isSignificant: boolean;
  confidenceScore?: number; // 0-100
}

export interface AnalystWeight {
  role: AgentRole;
  weight: number; // 0-1
  isExpert: boolean;
  expertiseArea?: string; // e.g. "Tech", "Commodities"
}

export interface CalculationResult {
  formulaName: string;
  inputs: Record<string, any>;
  output: any;
  timestamp: string;
}

export interface SegmentValuation {
  segmentName: string;
  valuationMethod: string;
  multiplier: string;
  fairValue: string;
  anchorPeer?: string;
}

export interface DataVerification {
  source: string;
  isVerified: boolean;
  discrepancy?: string;
  confidence: number; // 0-100
  lastChecked: string;
}

// === 阶段 1：核心变量体系 (Core Variable System) ===
export interface CoreVariable {
  name: string;            // 变量名，如"出货量"、"碳酸锂价格"
  value: number | string;  // 当前值
  unit: string;            // 单位，如 GWh、元/吨
  marketExpect: number | string; // 市场一致预期
  delta: string;           // 偏离说明，如 "+5% vs 预期"
  reason: string;          // 偏离原因
  evidenceLevel: "财报" | "研报共识" | "第三方监控" | "推算" | "信息缺失";
  source?: string;         // 数据来源，如 "Wind", "东方财富", "LME"
  dataDate?: string;       // 数据日期，如 "2026-04-03"
}

export interface BusinessModel {
  businessType: BusinessType;         // 行业类型
  formula: string;                     // 利润公式，如 "利润 = 产量 × (售价 - 成本)"
  drivers: Record<string, string>;     // 关键因子，如 { volume: "40 GWh", price: "5000 元/GWh" }
  projectedProfit: string;             // 预测利润
  confidenceScore: number;             // 0-100 置信度
}

// === 阶段 2：风险概率化 (Quantified Risk) ===
export interface QuantifiedRisk {
  name: string;            // 风险名称
  probability: number;     // 发生概率 0-100
  impactPercent: number;   // 对利润的影响幅度 (负数表示损失)
  expectedLoss: number;    // 期望损失 = probability × impactPercent / 100
  mitigation: string;      // 对冲/缓释手段
}

export type AnalysisLevel = 'quick' | 'standard' | 'deep';

// === OPT-1 Expert Output ===