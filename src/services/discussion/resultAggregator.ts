import type { AgentRole, AgentMessage, AgentDiscussion, ExpertOutput } from '../../types';
import type { BacktestResult } from '../backtestService';

export function aggregateResults(
  roundResults: Map<AgentRole, ExpertOutput>,
  backtest: BacktestResult | null,
  allMessages?: AgentMessage[],
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

  const discussion: AgentDiscussion = {
    messages,
    finalConclusion: chiefStrategist?.message.content ?? '',
    coreVariables: deepResearch?.structuredData?.coreVariables,
    businessModel: deepResearch?.structuredData?.businessModel,
    moatAnalysis: deepResearch?.structuredData?.moatAnalysis,
    industryAnchors: deepResearch?.structuredData?.industryAnchors,
    quantifiedRisks: mergedRisks.length > 0 ? mergedRisks : undefined,
    tradingPlan: chiefStrategist?.structuredData?.tradingPlan,
    scenarios: chiefStrategist?.structuredData?.scenarios,
    expectationGap: chiefStrategist?.structuredData?.expectationGap,
    expectedValueOutcome: chiefStrategist?.structuredData?.expectedValueOutcome,
    sensitivityMatrix: chiefStrategist?.structuredData?.sensitivityMatrix,
    controversialPoints: controversialPoints.length > 0 ? controversialPoints : undefined,
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
