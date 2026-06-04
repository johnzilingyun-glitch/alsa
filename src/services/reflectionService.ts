/**
 * Reflection & Memory System
 * 
 * After each analysis, compares with historical outcomes and stores structured
 * lessons. Uses BM25-like keyword matching for retrieval — no external dependencies.
 * 
 * Inspired by TradingAgents' reflect_and_remember pattern:
 * - Each agent role gets reflected on independently
 * - Lessons are stored per-symbol and cross-symbol
 * - Memory is retrieved at analysis time to inform prompts
 */

import type { StockAnalysis, AgentRole } from '../types';
import type { BacktestResult } from './backtestService';

// ── Types ──────────────────────────────────────────────────────────

export interface ReflectionEntry {
  id: string;
  symbol: string;
  date: string;
  recommendation: string;
  score: number;
  outcome: BacktestResult;
  lessons: string[];
  agentReflections: AgentReflection[];
  marketContext: string; // brief market snapshot
}

export interface AgentReflection {
  role: AgentRole | 'System';
  wasCorrect: boolean;
  insight: string; // what worked or failed
  improvementAction: string;
}

export interface MemoryMatch {
  entry: ReflectionEntry;
  relevanceScore: number;
}

async function loadMemory(): Promise<ReflectionEntry[]> {
  try {
    const res = await fetch('/api/reflections/?limit=100');
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

async function saveMemory(entry: ReflectionEntry): Promise<void> {
  try {
    const payload = {
      symbol: entry.symbol,
      date: entry.date,
      score: entry.score,
      recommendation: entry.recommendation,
      outcome_status: entry.outcome.status,
      outcome_return: entry.outcome.returnSincePrev,
      lessons: entry.lessons,
      agent_reflections: entry.agentReflections,
      market_context: entry.marketContext
    };

    await fetch('/api/reflections/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  } catch (e) {
    console.error('Failed to save reflection memory:', e);
  }
}

// ── Tokenizer (simple BM25-compatible) ─────────────────────────────

function tokenize(text: string): string[] {
  return text.toLowerCase().match(/\b\w+\b/g) || [];
}

// ── Reflection Generation ──────────────────────────────────────────

export function generateReflection(
  analysis: StockAnalysis,
  backtest: BacktestResult,
): ReflectionEntry {
  const agentReflections: AgentReflection[] = [];

  // Reflect on the overall system
  const directionCorrect = backtest.status === 'Target Hit' ||
    (backtest.accuracy >= 50);

  agentReflections.push({
    role: 'System',
    wasCorrect: directionCorrect,
    insight: directionCorrect
      ? `Recommendation ${backtest.previousRecommendation} was directionally correct. Return: ${backtest.returnSincePrev}`
      : `Recommendation ${backtest.previousRecommendation} was incorrect. Return: ${backtest.returnSincePrev}. Status: ${backtest.status}`,
    improvementAction: directionCorrect
      ? 'Continue current analytical framework for this market regime.'
      : backtest.status === 'Stop Loss Hit'
        ? 'Risk management triggered — review entry timing and stop-loss placement.'
        : 'Re-examine core thesis drivers; check if key assumptions still hold.',
  });

  // Reflect on discussion agents if available
  if (analysis.discussion) {
    for (const msg of analysis.discussion) {
      const role = msg.role as AgentRole;
      if (role === 'Moderator') continue;

      agentReflections.push({
        role,
        wasCorrect: directionCorrect,
        insight: `${role}'s analysis ${directionCorrect ? 'aligned with' : 'diverged from'} actual outcome.`,
        improvementAction: directionCorrect
          ? `${role}'s methodology was effective this round.`
          : `${role} should re-examine assumptions for ${analysis.stockInfo.symbol}.`,
      });
    }
  }

  const lessons: string[] = [];
  if (backtest.status === 'Target Hit') {
    lessons.push(`${analysis.stockInfo.symbol}: Target reached. Core thesis validated.`);
  } else if (backtest.status === 'Stop Loss Hit') {
    lessons.push(`${analysis.stockInfo.symbol}: Stop-loss triggered. Key variable deviated.`);
    if (analysis.keyRisks.length > 0) {
      lessons.push(`Materialized risk: ${analysis.keyRisks[0]}`);
    }
  } else {
    lessons.push(`${analysis.stockInfo.symbol}: In progress (${backtest.returnSincePrev}). Monitor core drivers.`);
  }

  return {
    id: `ref-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    symbol: analysis.stockInfo.symbol,
    date: new Date().toISOString().split('T')[0],
    recommendation: analysis.recommendation,
    score: analysis.score,
    outcome: backtest,
    lessons,
    agentReflections,
    marketContext: `${analysis.stockInfo.symbol} @ ${analysis.stockInfo.price} (${analysis.sentiment})`,
  };
}

export async function storeReflection(entry: ReflectionEntry): Promise<void> {
  await saveMemory(entry);
}

import { alertsClient } from './api/alertsClient';

// ── Memory Retrieval (BM25-inspired keyword matching) ──────────────

export async function retrieveMemories(
  symbol: string,
  marketContext: string,
  maxResults: number = 3,
): Promise<MemoryMatch[]> {
  const memory = await loadMemory();
  
  // Also fetch manual postmortems
  let manualMemories: any[] = [];
  try {
    const closedAlerts = await alertsClient.listClosed();
    manualMemories = closedAlerts
      .filter((a: any) => a.symbol === symbol && a.postmortem_notes)
      .map((a: any) => ({
        id: a.alert_id,
        symbol: a.symbol,
        date: a.exit_date || a.created_at,
        recommendation: a.outcome_category || 'MANUAL_TRADE',
        score: a.decision_quality_score || 5,
        outcome: { status: 'Closed', returnSincePrev: a.realized_return_pct ? `${a.realized_return_pct}%` : 'N/A' },
        lessons: [a.lessons_learned || '', a.postmortem_notes || ''].filter(Boolean),
        agentReflections: [{ insight: 'Manual Trader Postmortem' }],
        marketContext: a.market
      }));
  } catch (e) {
    console.error('Failed to fetch manual postmortems:', e);
  }

  const allMemories = [...memory, ...manualMemories];
  if (allMemories.length === 0) return [];

  const queryTokens = new Set(tokenize(`${symbol} ${marketContext}`));

  const scored = allMemories.map(entry => {
    let score = 0;

    // Exact symbol match is highest priority
    if (entry.symbol === symbol) score += 10;

    // Keyword overlap with lessons and market context
    const lessons = Array.isArray(entry.lessons) ? entry.lessons : [];
    const agentReflections = Array.isArray(entry.agentReflections) ? entry.agentReflections : [];
    const docTokens = tokenize(
      `${entry.symbol} ${lessons.join(' ')} ${entry.marketContext || ''} ${agentReflections.map((r: any) => r?.insight || '').join(' ')}`
    );

    for (const token of docTokens) {
      if (queryTokens.has(token)) score += 1;
    }

    // Recency bonus (newer entries rank higher)
    const entryDate = (entry as any).date || (entry as any).timestamp || new Date().toISOString();
    const ageMs = Date.now() - new Date(entryDate).getTime();
    const ageDays = ageMs / (1000 * 60 * 60 * 24);
    if (ageDays < 7) score += 3;
    else if (ageDays < 30) score += 1;

    return { entry, relevanceScore: score };
  });

  return scored
    .filter(m => m.relevanceScore > 0)
    .sort((a, b) => b.relevanceScore - a.relevanceScore)
    .slice(0, maxResults);
}

// ── Format for Prompt Injection ────────────────────────────────────

export function formatMemoryForPrompt(matches: MemoryMatch[]): string {
  if (matches.length === 0) return '';

  const lines = matches.map((m, i) => {
    const e = m.entry;
    const outcomeData = e.outcome || { status: 'In Progress', returnSincePrev: 'N/A' };
    const lessons = Array.isArray(e.lessons) ? e.lessons : [];
    const agentReflections = Array.isArray(e.agentReflections) ? e.agentReflections : [];
    const entryDate = (e as any).date || (e as any).timestamp || 'N/A';
    const outcome = outcomeData.status === 'Target Hit' ? 'Target Hit' :
      outcomeData.status === 'Stop Loss Hit' ? 'Stop-Loss Hit' :
      `In Progress (${outcomeData.returnSincePrev || 'N/A'})`;

    return `**Memory ${i + 1}** [${e.symbol} on ${entryDate}]:
- Recommendation: ${e.recommendation || 'N/A'} -> ${outcome}
- Lessons: ${lessons.join('; ') || 'N/A'}
- Key Insight: ${agentReflections[0]?.insight || 'N/A'}`;
  });

  return `
**REFLECTION MEMORY (Historical Lessons — Use to improve accuracy)**:
${lines.join('\n\n')}
**INSTRUCTION**: Consider these past outcomes when forming your analysis. Avoid repeating mistakes and reinforce patterns that worked.
`;
}

// ── Public API: Reflect & Remember (called after backtest) ─────────

export async function reflectAndRemember(
  analysis: StockAnalysis,
  backtest: BacktestResult | null,
): Promise<void> {
  if (!backtest) return;

  const entry = generateReflection(analysis, backtest);
  await storeReflection(entry);
}
