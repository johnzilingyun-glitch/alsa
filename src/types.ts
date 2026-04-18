export type Market = "A-Share" | "HK-Share" | "US-Share";
export type Language = "en" | "zh-CN";

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
}

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

export interface SectorAnalysis {
  name: string;
  trend: string;
  rotationStage?: string;
  upstreamImpact?: string;
  downstreamImpact?: string;
  conclusion: string;
}

export interface CommodityAnalysis {
  name: string;
  trend: string;
  expectation: string;
}

export interface Recommendation {
  type: "Stock" | "Sector";
  name: string;
  reason: string;
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
    warning?: string;
    details: string;
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
  cycleAnalysis?: {
    stage: "Early" | "Mid" | "Late" | "Bottom" | "Peak";
    logic: string;
    volatilityRisk: string;
  };
  legendaryInsights?: {
    valueSage?: { marginOfSafety: string; intrinsicValue: string; moatRating: string };
    growthVisionary?: { tamEstimate: string; innovationScore: number; disruptionPotential: string };
    macroTitan?: { macroSignal: string; liquidityStatus: string; systemicRiskLevel: string };
  };
  chatHistory?: { id: string; role: "user" | "ai"; content: string }[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
}

export type AgentRole =
  | "Technical Analyst"
  | "Fundamental Analyst"
  | "Sentiment Analyst"
  | "Risk Manager"
  | "Aggressive Risk Analyst"
  | "Conservative Risk Analyst"
  | "Neutral Risk Analyst"
  | "Bull Researcher"
  | "Bear Researcher"
  | "Contrarian Strategist"
  | "Deep Research Specialist"
  | "Professional Reviewer"
  | "Chief Strategist"
  | "Value Investing Sage"
  | "Growth Visionary"
  | "Macro Hedge Titan"
  | "Moderator";

export interface AgentMessage {
  id?: string;
  role: AgentRole;
  content: string;
  timestamp: string;
  type?: "discussion" | "research" | "review" | "user_question" | "fact_check";
  references?: { title: string; url: string }[];
  round?: number;
  logicFindings?: { rule: string; severity: string; finding: string }[];
}

export interface MultiRoundProgress {
  currentRound: number;
  totalRounds: number;
  activeExperts: string[]; // Support parallel experts
  currentStep?: 'grounding' | 'reasoning' | 'drafting' | 'reviewing' | 'auditing';
  messages: AgentMessage[];
  partialDiscussion?: Partial<AgentDiscussion>;
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

export interface AgentDiscussion {
  messages: AgentMessage[];
  finalConclusion: string;
  tradingPlan?: TradingPlan;
  tradingPlanHistory?: TradingPlanVersion[];
  controversialPoints?: string[];
  scenarios?: Scenario[];
  valuationMatrix?: Scenario[];
  stressTestLogic?: string;
  catalystList?: Catalyst[];
  sensitivityFactors?: SensitivityFactor[];
  expectationGap?: ExpectationGap;
  analystWeights?: AnalystWeight[];
  calculations?: CalculationResult[];
  dataFreshnessStatus?: "Fresh" | "Stale" | "Warning";
  dataVerification?: DataVerification[];
  coreVariables?: CoreVariable[];
  businessModel?: BusinessModel;
  moatAnalysis?: {
    type: string;
    strength: "Wide" | "Narrow" | "None";
    logic: string;
  };
  industryAnchors?: IndustryAnchor[];
  quantifiedRisks?: QuantifiedRisk[];
  riskAdjustedValuation?: number;
  expectedValueOutcome?: ExpectedValueOutcome;
  sensitivityMatrix?: SensitivityMatrixRow[];
  backtestResult?: {
    previousDate: string;
    previousRecommendation: string;
    actualReturn: string;
    learningPoint: string;
  };
  verificationMetrics?: {
    indicator: string;
    threshold: string;
    timeframe: string;
    logic: string;
  }[];
  capitalFlow?: {
    northboundFlow: string;
    institutionalHoldings: string;
    ahPremium?: string;
    marketSentiment: string;
  };
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
  legendaryInsights?: {
    valueSage?: { marginOfSafety: string; intrinsicValue: number; moatRating: string };
    growthVisionary?: { tamEstimate: string; innovationScore: number; disruptionPotential: string };
    macroTitan?: { macroSignal: string; liquidityStatus: string; systemicRiskLevel: string };
  };
  consensusBiasScore?: number; // 0-100 (Opinion Drift)
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

export type BusinessType = "manufacturing" | "saas" | "banking" | "retail" | "healthcare" | "tech" | "other";

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

export interface GeminiConfig {
  model: string;
  apiKey?: string;
  feishuWebhookUrl?: string;
  tier?: 'free' | 'paid';
  serviceMode?: 'byok' | 'managed_no_key' | 'copilot_local';
  enableCopilotFallback?: boolean;
}

export interface ReportPreference {
  detailLevel: 'executive' | 'analyst' | 'trader';
  focusAreas: ('fundamental' | 'technical' | 'risk' | 'scenario' | 'sentiment')[];
  includeBacktest: boolean;
  includeExpertDebate: boolean;
  maxLength: 'brief' | 'standard' | 'full';
}

// === 10.1 Data Freshness ===
export type FreshnessStatus = 'fresh' | 'delayed' | 'stale';

export interface FreshnessInfo {
  status: FreshnessStatus;
  label: string;     // "🟢 实时" | "🟡 延迟" | "🔴 过时"
  ageMinutes: number;
}

// === 10.2 Analysis Cache ===
export interface CachedAnalysis {
  data: StockAnalysis;
  timestamp: number;
}

// === OPT-1 Discussion Orchestrator ===
export interface DiscussionRound {
  round: number;
  experts: AgentRole[];
  parallel: boolean;
  dependsOn: number[];
}

export interface OrchestratorConfig {
  level: AnalysisLevel;
  assetType: 'stock' | 'etf' | 'index' | 'bond';
  skipRoles?: AgentRole[];
  maxConcurrency: number;
}

// === OPT-2 Backtest Enhancement ===
export interface BacktestTimeSeries {
  symbol: string;
  entries: BacktestEntry[];
  overallAccuracy: number;
  directionAccuracy: number;
  avgHoldingPeriodDays: number;
  profitFactor: number;
  maxConsecutiveLosses: number;
  longestWinStreak: number;
  sharpeRatio: number;
}

export interface BacktestEntry {
  date: string;
  recommendation: string;
  targetPrice: number;
  stopLoss: number;
  actualPrice: number;
  returnPercent: number;
  directionCorrect: boolean;
  targetHit: boolean;
}

export interface ExpertTrackRecord {
  role: AgentRole;
  totalCalls: number;
  directionAccuracy: number;
  targetHitRate: number;
  avgOvershoot: number;
  bestSector: string;
  worstSector: string;
  recentTrend: 'improving' | 'declining' | 'stable';
  last5Accuracy: number[];
}

export interface SystematicBias {
  hasBias: boolean;
  biasType: 'bullish_drift' | 'bearish_drift' | 'target_overshoot' | null;
  severity: 'low' | 'medium' | 'high';
  consecutiveCount: number;
}

// === OPT-6 Analysis Level ===
export type AnalysisLevel = 'quick' | 'standard' | 'deep';

// === OPT-1 Expert Output ===
export interface ExpertOutput {
  role: AgentRole;
  message: AgentMessage;
  structuredData?: {
    coreVariables?: CoreVariable[];
    quantifiedRisks?: QuantifiedRisk[];
    businessModel?: BusinessModel;
    scenarios?: Scenario[];
    tradingPlan?: TradingPlan;
    expectedValueOutcome?: ExpectedValueOutcome;
    sensitivityMatrix?: SensitivityMatrixRow[];
    moatAnalysis?: {
      type: string;
      strength: "Wide" | "Narrow" | "None";
      logic: string;
    };
    industryAnchors?: IndustryAnchor[];
    expectationGap?: ExpectationGap;
    marginOfSafety?: string;
    intrinsicValue?: string;
    moatRating?: string;
    tamEstimate?: string;
    innovationScore?: number;
    disruptionPotential?: string;
    macroSignal?: string;
    liquidityStatus?: string;
    systemicRiskLevel?: string;
  };
}

// === NEW-1 Watchlist ===
export interface WatchlistItem {
  id: string;
  symbol: string;
  name: string;
  market: Market;
  addedAt: string;
  notes: string;
  alertThreshold: number;
  scoreHistory: ScoreSnapshot[];
  lastQuickScan?: QuickScanResult;
  alertHistory: WatchlistAlert[];
}

export interface ScoreSnapshot {
  date: string;
  score: number;
  price: number;
  recommendation: string;
}

export interface QuickScanResult {
  score: number;
  sentiment: string;
  recommendation: string;
  summary: string;
  timestamp: string;
}

export interface WatchlistAlert {
  id: string;
  type: 'score_drop' | 'score_rise' | 'price_target' | 'stop_loss';
  message: string;
  triggeredAt: string;
  acknowledged: boolean;
}

// === NEW-2 Sector Rotation ===
export interface SectorRotation {
  sector: string;
  capitalFlowTrend: 'inflow' | 'outflow' | 'neutral';
  flowMagnitude: number;
  clockQuadrant: 'recovery' | 'expansion' | 'overheating' | 'stagflation';
  momentum30d: number;
  topStocks: { symbol: string; name: string; score: number }[];
  updatedAt: string;
}

export interface MarketCycle {
  currentPhase: 'recovery' | 'expansion' | 'overheating' | 'stagflation';
  phaseConfidence: number;
  recommendedSectors: string[];
  avoidSectors: string[];
  logic: string;
}

export interface SectorRotationData {
  rotations: SectorRotation[];
  cycle: MarketCycle;
  generatedAt: string;
}

// === NEW-4 Comparison ===
export interface ComparisonResult {
  stocks: ComparisonStock[];
  sharedIndustry: string;
  verdict: string;
  generatedAt: string;
}

export interface ComparisonStock {
  symbol: string;
  name: string;
  market: Market;
  score: number;
  recommendation: string;
  pe?: string;
  pb?: string;
  roe?: string;
  moatStrength?: 'Wide' | 'Narrow' | 'None';
  riskLevel: 'Low' | 'Medium' | 'High';
}

// === NEW-5 Decision Journal ===
export interface DecisionEntry {
  id: string;
  symbol: string;
  name: string;
  market: Market;
  analysisId: string;
  action: 'buy' | 'hold' | 'sell' | 'add' | 'reduce' | 'watch';
  reasoning: string;
  priceAtDecision: number;
  confidence: number;
  createdAt: string;
  reviewDate: string;
  priceAtReview?: number;
  actualReturn?: number;
  outcome?: 'correct' | 'incorrect' | 'neutral';
  reflection?: string;
  lessonsLearned?: string[];
  biasDetected?: string;
}

export interface DecisionStats {
  totalDecisions: number;
  correctRate: number;
  avgConfidence: number;
  overconfidenceBias: number;
  mostCommonBias: string;
  bestPerformingAction: string;
  worstPerformingAction: string;
  avgReturnByAction: Record<string, number>;
}
