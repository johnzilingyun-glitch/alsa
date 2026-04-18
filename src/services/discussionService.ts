import { createAI, withRetry, generateContentWithUsage, GEMINI_MODEL, delay, generateAndParseJsonWithRetry, QuotaError } from "./geminiService";
import { StockAnalysis, AgentMessage, AgentDiscussion, GeminiConfig, AnalysisLevel, AgentRole, ExpertOutput, Language, MultiRoundProgress, DataVerification } from "../types";
import { useConfigStore } from "../stores/useConfigStore";
import { getCommoditiesData } from "./marketService";
import { getPreviousStockAnalysis } from "./adminService";
import { performBacktest } from "./backtestService";
import { AgentDiscussionSchema, validateResponse } from "./schemas";
import { getDiscussionPrompt, getTranslationPrompt } from "./prompts";
import { buildTopology } from "./discussion/orchestrator";
import { getExpertPrompt, getExpertResponseSchema } from "./discussion/expertPrompts";
import { aggregateResults } from "./discussion/resultAggregator";
import { normalizeCoreVariablesByPriority } from "./coreVariablePriority";
import { reflectAndRemember, retrieveMemories, formatMemoryForPrompt } from "./reflectionService";
import { generateQuantitativeBaseline } from "./quantitativeModeling";
import { assembleExpertPrompt } from "./discussion/promptAssembler";
import { discoverIndustryAnchors } from "./discussion/anchorDiscovery";
import { getJudgePrompt } from "./prompts";
import { auditExpertLogic } from "./discussion/guardrails";

/**
 * [PHASE 2 OPTIMIZATION] - THE JUDGE AGENT
 * Cross-verifies expert messages against raw quantitative data.
 */
async function runJudgeAgent(
  ai: any, 
  analysis: StockAnalysis, 
  discussion: AgentDiscussion, 
  config?: GeminiConfig,
  language: Language = "en"
): Promise<DataVerification[]> {
  try {
    const prompt = getJudgePrompt(analysis, discussion, language);
    const raw = await generateAndParseJsonWithRetry<any>(ai, {
      model: CRITICAL_MODEL, // Always use high-logic model for auditing
      contents: prompt,
    }, { 
      responseMimeType: "application/json",
      role: 'Professional Reviewer'
    });

    const results: any[] = raw.verificationResults || [];
    return results.map(r => ({
      source: r.subject,
      isVerified: r.isVerified,
      discrepancy: r.severity !== 'none' ? r.finding : undefined,
      confidence: r.confidence,
      lastChecked: new Date().toISOString()
    }));
  } catch (err) {
    console.error("[JudgeAgent] Failed to audit discussion:", err);
    return [];
  }
}

/**
 * Compacts historical messages to reduce token usage in multi-round discussions.
 */
function compactMessages(messages: AgentMessage[], currentRound: number): AgentMessage[] {
  return messages.map((msg) => {
    if (msg.round === currentRound - 1 || msg.role === 'Deep Research Specialist' || msg.role === 'Chief Strategist') {
      return msg;
    }
    if (msg.content.length > 300) {
      return {
        ...msg,
        content: msg.content.substring(0, 300) + '... [Content compacted]'
      };
    }
    return msg;
  });
}

/**
 * Deterministic Pre-fill: Skips LLM call if data is insufficient.
 */
function getDeterministicPrefill(role: AgentRole, analysis: StockAnalysis): string | null {
  if (role === 'Technical Analyst' && analysis.stockInfo.price === 0) {
    return "由于标的当前处于停牌或数据缺失状态，无法进行有效技术面形态分析。";
  }
  if (role === 'Fundamental Analyst' && !analysis.fundamentals && !analysis.stockInfo.fundamentalScores) {
    return "当前财务数据缺失，无法进行深度定量分析。建议等待财报披露。";
  }
  return null;
}

/**
 * Default Factory for role-specific fallbacks.
 */
function getDefaultExpertOutput(role: AgentRole): string {
  const defaults: Partial<Record<AgentRole, string>> = {
    'Technical Analyst': "技术面分析暂时不可用。建议参考关键支撑位进行博弈。",
    'Fundamental Analyst': "基本面评估暂时不可用。建议关注行业平均收益率。",
    'Risk Manager': "风险评估暂时受限。建议维持审慎限仓。",
  };
  return defaults[role] || "分析生成异常，建议参考其他专家意见。";
}

// Iteration count per analysis level
const ITERATION_COUNT: Record<AnalysisLevel, number> = {
  quick: 0,
  standard: 1,
  deep: 1, 
};

// Tiered model configuration
const DRAFTING_MODEL = "gemini-3.1-flash-lite-preview"; // Fast, high-throughput
const CRITICAL_MODEL = "gemini-3.1-pro-preview";       // Deep reasoning, high logic


function hasQuantData(text: string): boolean {
  return /\d/.test(text);
}

function hasSourceHints(text: string): boolean {
  return /(API|Source|来源|Wind|东方财富|同花顺|交易所|Reuters|Bloomberg|Google Search|路透|彭博)/i.test(text);
}

function isLowQualityExpertContent(role: AgentRole, content: string): boolean {
  const t = (content || '').trim();
  if (t.length < 8) return true;

  // For SA/CS/DR, enforce stronger data density + source attribution
  if (role === 'Sentiment Analyst' || role === 'Contrarian Strategist' || role === 'Deep Research Specialist') {
    if (!hasQuantData(t) && !hasSourceHints(t)) return true;
  }

  return false;
}

/** For DR only: check that coreVariables have source+dataDate fields set */
function drCoreVarsMissingSourceDate(role: AgentRole, parsed: any): boolean {
  if (role !== 'Deep Research Specialist') return false;
  const vars: any[] = parsed?.coreVariables;
  if (!Array.isArray(vars) || vars.length === 0) return false;
  const missing = vars.filter((v: any) => !v.source || !v.dataDate).length;
  // Trigger retry if more than half the variables are missing source or date
  return missing > vars.length / 2;
}

export async function startMultiRoundDiscussion(
  analysis: StockAnalysis,
  level: AnalysisLevel,
  config?: GeminiConfig,
  onProgress?: (progress: MultiRoundProgress) => void,
  abortSignal?: AbortSignal,
): Promise<AgentDiscussion> {
  const ai = createAI(config);
  const commoditiesData = await getCommoditiesData();
  const language = useConfigStore.getState().language;
  const previousAnalysis = await getPreviousStockAnalysis(analysis.stockInfo.symbol);
  const backtest = performBacktest(analysis, previousAnalysis);

  // Store reflection from backtest outcomes for future retrieval
  reflectAndRemember(analysis, backtest);

  // --- NEW: Generate Quantitative Baseline ---
  const { coreVariables: discoveredVars, industryAnchors: discoveredAnchors } = discoverIndustryAnchors(analysis, commoditiesData);
  const baselineAnalysis = generateQuantitativeBaseline({
    ...analysis,
    coreVariables: [...(analysis.coreVariables || []), ...discoveredVars],
    industryAnchors: discoveredAnchors
  });
  
  // Update analysis with baseline data for prompt injection
  Object.assign(analysis, baselineAnalysis);
  // -------------------------------------------

  const iterations = ITERATION_COUNT[level];

  // Build iterative topology:
  // DR → [TA+FA → SA+RM+CS → Reviewer] × iterations → CS
  const topology = buildTopology({
    level,
    assetType: 'stock',
    maxConcurrency: 3,
  });

  // Expand middle rounds for iterations > 1
  const expandedTopology = buildIterativeTopology(topology, iterations);
  const totalRounds = expandedTopology.length;

  const allMessages: AgentMessage[] = [];
  const expertResults = new Map<AgentRole, ExpertOutput>();
  let roundNum = 0;

  for (const round of expandedTopology) {
    if (abortSignal?.aborted) break;
    roundNum++;

    // Helper to call a single expert
    const callExpert = async (role: AgentRole): Promise<ExpertOutput | null> => {
      if (abortSignal?.aborted) return null;

      onProgress?.({
        currentRound: roundNum,
        totalRounds,
        activeExperts: [role],
        currentStep: 'reasoning',
        messages: [...allMessages],
        partialDiscussion: {
          messages: [...allMessages],
          coreVariables: Array.from(expertResults.values()).flatMap(r => r.structuredData?.coreVariables || []),
          quantifiedRisks: Array.from(expertResults.values()).flatMap(r => r.structuredData?.quantifiedRisks || []),
        }
      });

      // Optimization 1: Deterministic Pre-fill
      const prefill = getDeterministicPrefill(role, analysis);
      if (prefill) {
        return {
          role,
          message: {
            id: `msg-prefill-${Date.now()}`,
            role,
            content: `[系统预填] ${prefill}`,
            timestamp: new Date().toISOString(),
            type: 'discussion',
            round: roundNum,
          },
          structuredData: {}
        };
      }

      // Optimization 2: Context Compaction
      const compactedContext = compactMessages(allMessages, roundNum);
      const prompt = await assembleExpertPrompt(role, analysis, compactedContext, commoditiesData, {
        language,
        includeExamples: true
      });

      // Only roles that explicitly need Google Search get the tool.
      // When tools are present, the SDK drops responseMimeType + responseSchema,
      // causing the model to return free-form text instead of structured JSON.
      const SEARCH_ROLES: Set<AgentRole> = new Set([
        'Deep Research Specialist',
        'Fundamental Analyst',
        'Sentiment Analyst',
        'Contrarian Strategist',
        'Macro Hedge Titan',
        'Value Investing Sage',
        'Growth Visionary',
      ]);
      const needsSearch = SEARCH_ROLES.has(role);

      const invokeExpert = async (inputPrompt: string) => {
        // Determine model based on role criticality
        const CRITICAL_ROLES: Set<AgentRole> = new Set([
          'Professional Reviewer',
          'Chief Strategist',
          'Risk Manager',
          'Macro Hedge Titan'
        ]);
        const model = CRITICAL_ROLES.has(role) ? CRITICAL_MODEL : (config?.model || DRAFTING_MODEL);

        return generateAndParseJsonWithRetry<any>(ai, {
          model: model, 
          contents: inputPrompt,
        }, { 
          transportRetries: 2, 
          baseDelayMs: 3000,
          responseMimeType: "application/json",
          responseSchema: getExpertResponseSchema(role),
          ...(needsSearch ? { tools: [{ googleSearch: {} }] } : {}),
          role
        });
      };
      let parsed = await invokeExpert(prompt);
      let content = String(parsed?.content || '').trim();

      // When tools (googleSearch) strip the schema, the model may use a different
      // field name for its text analysis. Try common alternatives before giving up.
      if (!content && parsed && typeof parsed === 'object') {
        const textCandidates = ['analysis', 'response', 'text', 'summary', 'answer', 'analysis_text', 'result'];
        for (const key of textCandidates) {
          if (typeof parsed[key] === 'string' && parsed[key].trim().length > 10) {
            content = parsed[key].trim();
            break;
          }
        }
        // Last resort: concatenate all string values that look like analysis text
        if (!content) {
          const longStrings = Object.values(parsed)
            .filter((v): v is string => typeof v === 'string' && v.trim().length > 50)
            .join('\n\n');
          if (longStrings.length > 50) content = longStrings;
        }
      }

      // One-shot corrective retry when content quality is insufficient
      const needsRetry =
        isLowQualityExpertContent(role, content) ||
        drCoreVarsMissingSourceDate(role, parsed);

      if (!abortSignal?.aborted && needsRetry) {
        const correction = `\n\n【警告：输出不合格，必须重答】\n` +
          `- 你的 "content" 字段内容太少或缺失（当前长度: ${content.length}）。\n` +
          `- 你必须提供至少 200 字的详细文字分析，解释你的逻辑和数据来源。\n` +
          `- 严禁仅返回空字符串或极短的内容。\n` +
          `- 必须包含至少 3 个具体量化指标（价格/比例/概率等）。\n` +
          `- 必须显式标注来源优先级和数据日期。\n` +
          `- 仅返回 JSON 格式。`;

        parsed = await invokeExpert(prompt + correction);
        content = String(parsed?.content || '').trim();
      }

      // Final fallback if content is still empty after retry
      if (!content || content.length < 10) {
        if (parsed?.coreVariables || parsed?.quantifiedRisks || parsed?.tradingPlan) {
          const dataSummary = [];
          if (parsed.coreVariables) dataSummary.push(`核心变量: ${parsed.coreVariables.length}项`);
          if (parsed.quantifiedRisks) dataSummary.push(`量化风险: ${parsed.quantifiedRisks.length}项`);
          if (parsed.tradingPlan) dataSummary.push(`交易计划已就绪`);
          
          content = `[系统摘要] ${role} 已完成深度分析并提交了结构化数据（${dataSummary.join('、')}）。虽然详细文字说明生成异常，但其量化结论已同步至决策引擎。建议关注后续轮次的交叉验证。`;
        } else {
          // If absolutely no data, try one last time with a very simple text-only prompt
          const prefix = `[系统紧急修复: 结构化数据解析异常，已切换至纯文本分析模式] `;
          try {
            const lastDitch = await generateContentWithUsage(ai, {
              model: GEMINI_MODEL, // Always use default model — user's model may have zero quota
              contents: `你是${role}。请针对 ${analysis.stockInfo.name} (${analysis.stockInfo.symbol}) 给出一段 150 字左右的专业分析结论。严禁返回空内容。`,
            });
            content = prefix + (lastDitch.text || `${role} 认为当前市场环境下，该标的展现出复杂的博弈特征，建议维持审慎态度并关注量化指标的动态变化。`);
          } catch {
            content = prefix + `${role} 认为当前市场环境下，该标的展现出复杂的博弈特征，建议维持审慎态度并关注量化指标的动态变化。`;
          }
        }
      }

      const message: AgentMessage = {
        id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
        role,
        content,
        timestamp: new Date().toISOString(),
        type: 'discussion',
        round: roundNum,
      };

      const output: ExpertOutput = {
        role,
        message,
        structuredData: {
          coreVariables: parsed?.coreVariables,
          quantifiedRisks: parsed?.quantifiedRisks,
          businessModel: parsed?.businessModel,
          tradingPlan: parsed?.tradingPlan,
          scenarios: parsed?.scenarios,
          expectedValueOutcome: parsed?.expectedValueOutcome,
          sensitivityMatrix: parsed?.sensitivityMatrix,
          moatAnalysis: parsed?.moatAnalysis,
          industryAnchors: parsed?.industryAnchors,
          expectationGap: parsed?.expectationGap,
        },
      };

      return output;
    };

    let results: (ExpertOutput | null)[] = [];

    // Execute experts based on round's parallel flag.
    // Parallel rounds: experts share the same prior context and run concurrently
    // (API calls are still throttled by the scheduler at 4.2s intervals, but LLM
    // processing overlaps server-side — cutting wall-clock time significantly).
    // Sequential rounds: experts see each preceding expert's output immediately.
    if (round.parallel && round.experts.length > 1) {
      // Parallel execution — all experts see the same allMessages snapshot
      const parallelOutputs = await Promise.all(
        round.experts.map(async (expertRole) => {
          if (abortSignal?.aborted) return null;
          
          // Local progress for parallel roles
          onProgress?.({
            currentRound: roundNum,
            totalRounds,
            activeExperts: round.experts,
            currentStep: 'grounding',
            messages: [...allMessages],
          });

          let output: ExpertOutput | null = null;
          try {
            output = await callExpert(expertRole);
          } catch (expertErr) {
            if (expertErr instanceof QuotaError) {
              throw expertErr; // Bubble up quota errors to stop the discussion loop
            }
            console.error(`[Discussion] Expert ${expertRole} failed:`, expertErr);
            const errorMsg = expertErr instanceof Error ? expertErr.message : String(expertErr);
            output = {
              role: expertRole,
              message: {
                id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
                role: expertRole,
                content: `[${expertRole} 分析暂时不可用] ${errorMsg.includes('quota') || errorMsg.includes('配额') ? '因 API 配额限制，该专家暂时无法提供分析。' : '该专家分析生成过程中出现异常回报。'}\n\n${getDefaultExpertOutput(expertRole)}`,
                timestamp: new Date().toISOString(),
                type: 'discussion',
                round: roundNum,
              },
              structuredData: {},
            };
          }
          return output;
        })
      );
      // Batch-add all parallel results after completion
      for (const output of parallelOutputs) {
        if (output) {
          results.push(output);
          allMessages.push(output.message);
          expertResults.set(output.role, output);
        }
      }
    } else {
      // Sequential execution — each expert sees the previous one's output
      for (let i = 0; i < round.experts.length; i++) {
        if (abortSignal?.aborted) break;
        if (i > 0) await delay(400);

        let output: ExpertOutput | null = null;
        try {
          output = await callExpert(round.experts[i]);
        } catch (expertErr) {
          if (expertErr instanceof QuotaError) {
            throw expertErr; // Bubble up quota errors to stop the discussion loop
          }
          console.error(`[Discussion] Expert ${round.experts[i]} failed:`, expertErr);
          const errorMsg = expertErr instanceof Error ? expertErr.message : String(expertErr);
          output = {
            role: round.experts[i],
            message: {
              id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
              role: round.experts[i],
              content: `[${round.experts[i]} 分析暂时不可用] ${errorMsg.includes('quota') || errorMsg.includes('配额') ? '因 API 配额限制，该专家暂时无法提供分析。' : '该专家分析生成过程中出现异常汇报。'}\n\n${getDefaultExpertOutput(round.experts[i])}`,
              timestamp: new Date().toISOString(),
              type: 'discussion',
              round: roundNum,
            },
            structuredData: {},
          };
        }
        if (output) {
          results.push(output);
          allMessages.push(output.message);
          expertResults.set(output.role, output);
        }
      }
    }
  }

  const multiRoundResult = aggregateResults(expertResults, backtest, allMessages, analysis);

  // --- [PHASE 2 OPTIMIZATION]: Run Judge Agent ---
  onProgress?.({
    currentRound: totalRounds,
    totalRounds,
    activeExperts: [language === 'zh-CN' ? '逻辑审计引擎' : 'Fact Check Auditor'],
    currentStep: 'auditing',
    messages: [...allMessages],
  });
  const verificationResults = await runJudgeAgent(ai, analysis, multiRoundResult, config, language);
  multiRoundResult.dataVerification = verificationResults;
  // ----------------------------------------------

  // Final synthesis: use the standard discussion prompt with multi-round history
  // to generate complete dashboard data (expectedValueOutcome, dataVerification, etc.)
  if (!abortSignal?.aborted) {
    onProgress?.({
      currentRound: totalRounds,
      totalRounds,
      activeExperts: ['综合研判引擎'],
      currentStep: 'reviewing',
      messages: [...allMessages],
    });

    try {
      const synthesis = await startAgentDiscussion(analysis, config, allMessages, {
          commoditiesData,
          backtest,
      }, language);
      // Merge: multi-round messages + synthesis structured data
      const merged = {
        ...synthesis,
        messages: multiRoundResult.messages, // keep all multi-round messages
        finalConclusion: synthesis.finalConclusion || multiRoundResult.finalConclusion,
        tradingPlan: synthesis.tradingPlan || multiRoundResult.tradingPlan,
        coreVariables: multiRoundResult.coreVariables || synthesis.coreVariables,
        quantifiedRisks: multiRoundResult.quantifiedRisks || synthesis.quantifiedRisks,
        scenarios: synthesis.scenarios || multiRoundResult.scenarios,
        controversialPoints: multiRoundResult.controversialPoints || synthesis.controversialPoints,
        backtestResult: multiRoundResult.backtestResult || synthesis.backtestResult,
      };

      merged.coreVariables = normalizeCoreVariablesByPriority(merged.coreVariables, analysis);
      return merged;
    } catch (err) {
      console.error('Synthesis step failed, using multi-round results:', err);
      return {
        ...multiRoundResult,
        coreVariables: normalizeCoreVariablesByPriority(multiRoundResult.coreVariables, analysis),
      };
    }
  }

  return {
    ...multiRoundResult,
    coreVariables: normalizeCoreVariablesByPriority(multiRoundResult.coreVariables, analysis),
  };
}

/**
 * Expand topology for iterative multi-round discussions.
 * Keeps only last round (CS) fixed,
 * repeats all other rounds (including DR) N times.
 * Pattern: [DR → TA+FA → SA+RM+CS → Reviewer] × N → CS
 */
function buildIterativeTopology(
  topology: { round: number; experts: AgentRole[]; parallel: boolean; dependsOn: number[] }[],
  iterations: number,
) {
  if (iterations <= 1 || topology.length <= 2) return topology;

  const last = topology[topology.length - 1];
  const cycle = topology.slice(0, -1); // Everything except CS

  const expanded: typeof topology = [];
  for (let i = 0; i < iterations; i++) {
    for (const round of cycle) {
      expanded.push({ ...round });
    }
  }
  expanded.push(last);

  // Re-number rounds
  return expanded.map((round, idx) => ({
    ...round,
    round: idx + 1,
  }));
}

/**
 * AI-powered router to select the most appropriate expert for a user's question.
 */
export async function routeUserQuestion(
  question: string,
  analysis: StockAnalysis,
  history: AgentMessage[],
  config?: GeminiConfig
): Promise<AgentRole> {
  const ai = createAI(config);
  
  const rolesInfo = `
  1. Technical Analyst: 技术面、K线、指标、量价关系、趋势预测。
  2. Fundamental Analyst: 基本面、财报、估值、行业竞争、盈利模式。
  3. Sentiment Analyst: 市场情绪、舆情分析、恐慌贪婪度。
  4. Risk Manager: 宏观风险、合规、黑天鹅、止损逻辑。
  5. Contrarian Strategist: 逆向思维、共识偏差、反向博弈。
  6. Deep Research Specialist: 产业链深度细节、核心变量追踪（如锂价、出货量）。
  7. Professional Reviewer: 逻辑审阅、逻辑缺陷查找、严谨性评估。
  8. Chief Strategist: 宏观策略、资产配置建议。
  `;

  const routingPrompt = `
  作为研讨会主持人，请根据用户的提问，从以下专家组中选择一位最适合回答该问题的专家。
  当前分析的股票：${analysis.stockInfo.name} (${analysis.stockInfo.symbol})
  
  【专家列表】
  ${rolesInfo}
  
  【用户提问】
  ${question}
  
  请基于问题的内容深度和专业度进行匹配。如果问题比较空泛，请默认分配给 "Professional Reviewer"。
  仅返回 JSON 格式，包含 role 字段，值为上述英文角色名称之一。
  `;

  const raw = await generateAndParseJsonWithRetry<any>(ai, {
    model: config?.model || GEMINI_MODEL,
    contents: routingPrompt,
    config: {
      responseMimeType: "application/json"
    }
  });

  const validRoles: AgentRole[] = [
    "Technical Analyst", "Fundamental Analyst", "Sentiment Analyst", 
    "Risk Manager", "Contrarian Strategist", "Deep Research Specialist", 
    "Professional Reviewer", "Chief Strategist"
  ];

  if (raw.role && validRoles.includes(raw.role as AgentRole)) {
    return raw.role as AgentRole;
  }

  return "Professional Reviewer";
}


// Simple in-memory cache for data and results
const discussionCache = {
  commodities: null as any,
  commoditiesTimestamp: 0,
  CACHE_DURATION: 15 * 60 * 1000 // 15 mins
};

async function getCachedCommodities() {
  const now = Date.now();
  if (discussionCache.commodities && (now - discussionCache.commoditiesTimestamp < discussionCache.CACHE_DURATION)) {
    return discussionCache.commodities;
  }
  
  const data = await getCommoditiesData();
  discussionCache.commodities = data;
  discussionCache.commoditiesTimestamp = now;
  return data;
}

export async function answerDiscussionQuestion(
  analysis: StockAnalysis,
  question: string,
  expertRole: AgentRole,
  history: AgentMessage[],
  config?: GeminiConfig
): Promise<AgentMessage> {
  const ai = createAI(config);
  const commoditiesData = await getCachedCommodities();
  const previousAnalysis = await getPreviousStockAnalysis(analysis.stockInfo.symbol);
  const backtest = performBacktest(analysis, previousAnalysis);
  const language = useConfigStore.getState().language;
  const prompt = getExpertPrompt(expertRole, analysis, history, commoditiesData, backtest, language);
  
  const additionalContext = `
【用户提问】
用户提出了一个新的问题，请你作为 ${expertRole} 针对该问题进行回答。
问题内容：${question}

请结合你之前的分析和上述问题，给出你的专业解答。仅返回 JSON 格式，包含 content 字段。
`;

  const raw = await generateAndParseJsonWithRetry<any>(ai, {
    model: config?.model || GEMINI_MODEL,
    contents: prompt + additionalContext,
    config: {
      responseMimeType: "application/json",
      tools: [{ googleSearch: {} }]
    }
  });

  return {
    id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    role: expertRole,
    content: raw.content || "未提供回答",
    timestamp: new Date().toISOString(),
    type: "user_question"
  };
}

export async function generateNewConclusion(
  analysis: StockAnalysis,
  history: AgentMessage[],
  config?: GeminiConfig
): Promise<{ message: AgentMessage, finalConclusion: string }> {
  const ai = createAI(config);
  const commoditiesData = await getCachedCommodities();
  const previousAnalysis = await getPreviousStockAnalysis(analysis.stockInfo.symbol);
  const backtest = performBacktest(analysis, previousAnalysis);

  const language = useConfigStore.getState().language;
  const prompt = getExpertPrompt('Chief Strategist', analysis, history, commoditiesData, backtest, language);
  
  const additionalContext = `
【最终总结指令】
作为首席策略师，请根据上述所有的讨论历史（包括用户的提问和其他专家的回答），给出最新的、最终的投资结论。
请仅返回 JSON 格式，包含 content 字段。
`;

  const raw = await generateAndParseJsonWithRetry<any>(ai, {
    model: config?.model || GEMINI_MODEL,
    contents: prompt + additionalContext,
  }, { 
    responseMimeType: "application/json",
    tools: [{ googleSearch: {} }]
  });

  const message: AgentMessage = {
    id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    role: 'Chief Strategist',
    content: raw.content || "未提供结论",
    timestamp: new Date().toISOString(),
    type: "review"
  };

  return {
    message,
    finalConclusion: raw.content || "未提供结论"
  };
}

export async function startAgentDiscussion(
  analysis: StockAnalysis,
  config?: GeminiConfig,
  history?: AgentMessage[],
  prefetched?: {
    commoditiesData?: any[];
    backtest?: ReturnType<typeof performBacktest> | null;
  },
  language?: Language
): Promise<AgentDiscussion> {
  const ai = createAI(config);
  const currentLanguage = language ?? useConfigStore.getState().language;
  const historyContext = history ? `\n\n**PREVIOUS DISCUSSION HISTORY**:\n${JSON.stringify(history)}` : "";
  const commoditiesData = prefetched?.commoditiesData ?? await getCommoditiesData();
  const resolvedBacktest = prefetched?.backtest ?? await (async () => {
    const previousAnalysis = await getPreviousStockAnalysis(analysis.stockInfo.symbol);
    return performBacktest(analysis, previousAnalysis);
  })();

  const memoryContext = resolvedBacktest ? `
    **MEMORY & FEEDBACK LOOP (LEARNING FROM PAST)**:
    - 我们在 ${resolvedBacktest.previousDate} 对该股票进行过深度分析。
    - 当时价格为 ${resolvedBacktest.previousPrice}，当前价格为 ${resolvedBacktest.currentPrice}（变动: ${resolvedBacktest.returnSincePrev}）。
    - 当时给出的建议是 ${resolvedBacktest.previousRecommendation}，目标价为 ${resolvedBacktest.previousTarget}，止损价为 ${resolvedBacktest.previousStopLoss}。
    - **当前状态**: ${resolvedBacktest.status}（预测得分/准确率: ${resolvedBacktest.accuracy}/100）。
    - **强制指令**: 深度研究专家和首席策略师必须在讨论中明确引用上述历史业绩情况。如果是"预测被打脸"或"逻辑漂移"，必须解释原因并修正逻辑；如果是"目标达成"，则讨论是否该止盈或提高目标价。
  ` : "";

  // Inject reflection memory from past outcomes
  const memories = retrieveMemories(analysis.stockInfo.symbol, analysis.sentiment);
  const reflectionMemory = formatMemoryForPrompt(memories);

  // Store reflection if we have backtest data (learn from this cycle)
  reflectAndRemember(analysis, resolvedBacktest);

  const prompt = getDiscussionPrompt(analysis, commoditiesData, memoryContext + reflectionMemory, historyContext, currentLanguage);
  
  const raw = await generateAndParseJsonWithRetry<AgentDiscussion>(ai, {
    model: config?.model || GEMINI_MODEL,
    contents: prompt,
  }, { 
    responseMimeType: "application/json",
    tools: [{ googleSearch: {} }],
    responseSchema: AgentDiscussionSchema
  });

  const parsed = validateResponse(AgentDiscussionSchema, raw, 'AgentDiscussion') as AgentDiscussion;

  // Inject backtest results back into the response for UI display
  if (resolvedBacktest) {
    parsed.backtestResult = {
      previousDate: resolvedBacktest.previousDate,
      previousRecommendation: resolvedBacktest.previousRecommendation,
      actualReturn: resolvedBacktest.returnSincePrev,
      learningPoint: resolvedBacktest.learningPoint
    };
  }

  // Add unique IDs to messages for stable React keys
  if (parsed.messages) {
    parsed.messages = parsed.messages.map((msg, idx) => ({
      ...msg,
      id: `msg-${Date.now()}-${idx}-${Math.random().toString(36).substr(2, 9)}`
    }));
  }

  parsed.coreVariables = normalizeCoreVariablesByPriority(parsed.coreVariables, analysis);

  return parsed;
}

export async function translateDiscussion(discussion: AgentDiscussion, targetLanguage: string, config?: GeminiConfig): Promise<AgentDiscussion> {
  const ai = createAI(config);
  const prompt = getTranslationPrompt(targetLanguage, discussion, 'discussion');

  try {
    const translatedRaw = await generateAndParseJsonWithRetry<AgentDiscussion>(
      ai,
      {
        model: config?.model || GEMINI_MODEL,
        contents: prompt,
        config: { responseMimeType: "application/json" }
      },
      {
        transportRetries: 2,
        baseDelayMs: 2000,
        parseRetries: 1,
        parseDelayMs: 1000,
      }
    );
    
    const translated = validateResponse(AgentDiscussionSchema, translatedRaw, 'TranslatedDiscussion') as AgentDiscussion;
    
    return {
      ...discussion,
      ...translated,
      messages: translated.messages.map((msg, i) => ({
        ...msg,
        id: discussion.messages[i]?.id || msg.id // Try to keep original IDs for stable keys
      }))
    };
  } catch (err) {
    console.error(`[TranslationService] Failed to translate discussion:`, err);
    throw err;
  }
}
