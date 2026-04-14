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

// ── Storage (localStorage-backed) ──────────────────────────────────

const STORAGE_KEY = 'reflection_memory';
const MAX_ENTRIES = 200;

function loadMemory(): ReflectionEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveMemory(entries: ReflectionEntry[]): void {
  // Keep only the latest MAX_ENTRIES
  const trimmed = entries.slice(-MAX_ENTRIES);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
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

// ── Memory Storage ─────────────────────────────────────────────────

export function storeReflection(entry: ReflectionEntry): void {
  const memory = loadMemory();
  memory.push(entry);
  saveMemory(memory);
}

// ── Memory Retrieval (BM25-inspired keyword matching) ──────────────

export function retrieveMemories(
  symbol: string,
  marketContext: string,
  maxResults: number = 3,
): MemoryMatch[] {
  const memory = loadMemory();
  if (memory.length === 0) return [];

  const queryTokens = new Set(tokenize(`${symbol} ${marketContext}`));

  const scored = memory.map(entry => {
    let score = 0;

    // Exact symbol match is highest priority
    if (entry.symbol === symbol) score += 10;

    // Keyword overlap with lessons and market context
    const docTokens = tokenize(
      `${entry.symbol} ${entry.lessons.join(' ')} ${entry.marketContext} ${entry.agentReflections.map(r => r.insight).join(' ')}`
    );

    for (const token of docTokens) {
      if (queryTokens.has(token)) score += 1;
    }

    // Recency bonus (newer entries rank higher)
    const ageMs = Date.now() - new Date(entry.date).getTime();
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
    const outcome = e.outcome.status === 'Target Hit' ? '✅ Target Hit' :
      e.outcome.status === 'Stop Loss Hit' ? '❌ Stop-Loss Hit' :
      `⏳ In Progress (${e.outcome.returnSincePrev})`;

    return `**Memory ${i + 1}** [${e.symbol} on ${e.date}]:
- Recommendation: ${e.recommendation} → ${outcome}
- Lessons: ${e.lessons.join('; ')}
- Key Insight: ${e.agentReflections[0]?.insight || 'N/A'}`;
  });

  return `
**REFLECTION MEMORY (Historical Lessons — Use to improve accuracy)**:
${lines.join('\n\n')}
**INSTRUCTION**: Consider these past outcomes when forming your analysis. Avoid repeating mistakes and reinforce patterns that worked.
`;
}

// ── Public API: Reflect & Remember (called after backtest) ─────────

export function reflectAndRemember(
  analysis: StockAnalysis,
  backtest: BacktestResult | null,
): void {
  if (!backtest) return;

  const entry = generateReflection(analysis, backtest);
  storeReflection(entry);
}
