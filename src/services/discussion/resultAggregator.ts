import type { AgentRole, AgentMessage, AgentDiscussion, ExpertOutput, StockAnalysis } from '../../types';
import type { BacktestResult } from '../backtestService';

export function aggregateResults(
  roundResults: Map<AgentRole, ExpertOutput>,
  backtest: BacktestResult | null,
  allMessages?: AgentMessage[],
  baseline?: Partial<StockAnalysis>
): AgentDiscussion {
  // Use allMessages if provided (multi-round), otherwise extract from Map (single-round)
  const messages = allMessages
    ? allMessages.map((msg, idx) => ({
        ...msg,
        id: msg.id || `msg-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 11)}`,
      }))
    : Array.from(roundResults.values()).map((output, idx) => ({
        ...output.message,
        id: output.message.id || `msg-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 11)}`,
      }));

  // Extract structured data from specific experts
  const deepResearch = roundResults.get('Deep Research Specialist');
  const riskManager = roundResults.get('Risk Manager') || roundResults.get('Neutral Risk Analyst');
  const chiefStrategist = roundResults.get('Chief Strategist');
  const contrarian = roundResults.get('Contrarian Strategist');
  const bearResearcher = roundResults.get('Bear Researcher');
  const valueSage = roundResults.get('Value Investing Sage');
  const growthVisionary = roundResults.get('Growth Visionary');
  const macroTitan = roundResults.get('Macro Hedge Titan');
  const fundamentalAnalyst = roundResults.get('Fundamental Analyst');

  // Collect controversial points from both contrarian and bear researcher
  const controversialPoints: string[] = [];
  if (contrarian?.message.content) controversialPoints.push(contrarian.message.content.slice(0, 200));
  if (bearResearcher?.message.content) controversialPoints.push(bearResearcher.message.content.slice(0, 200));

  // Merge quantified risks from Risk Manager and risk triad
  const aggressiveRisk = roundResults.get('Aggressive Risk Analyst');
  const conservativeRisk = roundResults.get('Conservative Risk Analyst');
  const mergedRisks = [
    ...(riskManager?.structuredData?.quantifiedRisks || []),
    ...(aggressiveRisk?.structuredData?.quantifiedRisks || []),
    ...(conservativeRisk?.structuredData?.quantifiedRisks || []),
  ];

  const valueSageInsights = valueSage?.structuredData?.marginOfSafety
    && valueSage.structuredData.intrinsicValue
    && valueSage.structuredData.moatRating
      ? {
          marginOfSafety: valueSage.structuredData.marginOfSafety || '',
          intrinsicValue: String(valueSage.structuredData.intrinsicValue || ''),
          moatRating: valueSage.structuredData.moatRating || '',
        }
      : undefined;

  const growthVisionaryInsights = growthVisionary?.structuredData?.tamEstimate
    && growthVisionary.structuredData.innovationScore !== undefined
    && growthVisionary.structuredData.disruptionPotential
      ? {
          tamEstimate: growthVisionary.structuredData.tamEstimate || '',
          innovationScore: String(growthVisionary.structuredData.innovationScore || ''),
          disruptionPotential: growthVisionary.structuredData.disruptionPotential || '',
        }
      : undefined;

  const macroTitanInsights = macroTitan?.structuredData?.macroSignal
    && macroTitan.structuredData.liquidityStatus
    && macroTitan.structuredData.systemicRiskLevel
      ? {
          macroSignal: macroTitan.structuredData.macroSignal,
          liquidityStatus: macroTitan.structuredData.liquidityStatus,
          systemicRiskLevel: macroTitan.structuredData.systemicRiskLevel,
        }
      : undefined;

  // 1. Calculate Consensus Bias (Opinion Drift)
  let consensusBiasScore = 0;
  if (chiefStrategist?.structuredData?.expectedValueOutcome?.expectedPrice && baseline?.stockInfo?.price) {
    const aiExpected = chiefStrategist.structuredData.expectedValueOutcome.expectedPrice;
    const baselinePrice = baseline.stockInfo.price;
    // Drift is the % difference between AI expectation and current market anchor
    const drift = Math.abs((aiExpected - baselinePrice) / baselinePrice) * 100;
    consensusBiasScore = Math.min(100, Math.round(drift * 2)); // Scaled: 25% drift = 50 bias score
  }

  // 2. Aggregate SOTP Matrix
  const sotpMatrix = chiefStrategist?.structuredData?.sotpMatrix 
    || fundamentalAnalyst?.structuredData?.sotpMatrix 
    || [];

  const discussion: AgentDiscussion = {
    messages,
    finalConclusion: chiefStrategist?.message.content ?? '',
    coreVariables: deepResearch?.structuredData?.coreVariables || baseline?.coreVariables,
    businessModel: deepResearch?.structuredData?.businessModel || baseline?.businessModel,
    moatAnalysis: deepResearch?.structuredData?.moatAnalysis || baseline?.moatAnalysis,
    industryAnchors: deepResearch?.structuredData?.industryAnchors || baseline?.industryAnchors,
    quantifiedRisks: mergedRisks.length > 0 ? mergedRisks : (baseline?.quantifiedRisks || []),
    tradingPlan: chiefStrategist?.structuredData?.tradingPlan || baseline?.tradingPlan,
    scenarios: chiefStrategist?.structuredData?.scenarios || baseline?.scenarios,
    expectationGap: chiefStrategist?.structuredData?.expectationGap || baseline?.expectationGap,
    expectedValueOutcome: chiefStrategist?.structuredData?.expectedValueOutcome || baseline?.expectedValueOutcome,
    sensitivityMatrix: chiefStrategist?.structuredData?.sensitivityMatrix || baseline?.sensitivityMatrix,
    controversialPoints: controversialPoints.length > 0 ? controversialPoints : undefined,
    legendaryInsights: {
      valueSage: valueSageInsights,
      growthVisionary: growthVisionaryInsights,
      macroTitan: macroTitanInsights,
    },
    consensusBiasScore,
    sotpMatrix: sotpMatrix.length > 0 ? sotpMatrix : undefined,
    monteCarloData: baseline?.monteCarloData,
    institutionalRisk: baseline?.institutionalRisk
  };

  if (backtest) {
    discussion.backtestResult = {
      previousDate: backtest.previousDate,
      previousRecommendation: backtest.previousRecommendation,
      actualReturn: backtest.returnSincePrev,
      learningPoint: backtest.learningPoint,
    };
  }

  return discussion;
}
