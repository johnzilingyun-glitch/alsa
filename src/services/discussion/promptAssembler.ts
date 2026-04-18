import { AgentRole, Language, StockAnalysis, AgentMessage } from '../../types';
import { TEMPORAL_ALIGNMENT_EN, TEMPORAL_ALIGNMENT_ZH } from './prompts/protocols/temporalAlignment';
import { DATA_PRIORITY_EN, DATA_PRIORITY_ZH } from './prompts/protocols/dataSourcePriority';
import { TECHNICAL_ANALYST_PERSONA_EN, TECHNICAL_ANALYST_PERSONA_ZH } from './prompts/roles/technicalAnalyst';
import { FUNDAMENTAL_ANALYST_PERSONA_EN, FUNDAMENTAL_ANALYST_PERSONA_ZH } from './prompts/roles/fundamentalAnalyst';
import { CHIEF_STRATEGIST_PERSONA_EN, CHIEF_STRATEGIST_PERSONA_ZH } from './prompts/roles/chiefStrategist';
import { 
  TECHNICAL_ANALYST_EXAMPLES_ZH, 
  CHIEF_STRATEGIST_EXAMPLES_ZH,
  TECHNICAL_ANALYST_EXAMPLES_EN,
  CHIEF_STRATEGIST_EXAMPLES_EN
} from './prompts/fewShot/examples';

interface AssemblerOptions {
  language?: Language;
  includeExamples?: boolean;
}

export async function assembleExpertPrompt(
  role: AgentRole,
  analysis: StockAnalysis,
  previousRounds: AgentMessage[],
  commoditiesData: any[],
  options: AssemblerOptions = {}
): Promise<string> {
  const language = options.language || 'en';
  const isZh = language === 'zh-CN';

  const sections: string[] = [];

  // 1. Get Persona
  const persona = getRolePersona(role, isZh);
  sections.push(persona);

  // 2. Protocols
  sections.push(isZh ? TEMPORAL_ALIGNMENT_ZH : TEMPORAL_ALIGNMENT_EN);
  sections.push(isZh ? DATA_PRIORITY_ZH : DATA_PRIORITY_EN);

  // 3. Examples (Few-Shot)
  if (options.includeExamples) {
    const examples = getRoleExamples(role, isZh);
    if (examples) sections.push(examples);
  }

  // 4. Context
  sections.push(`\n**Current Date Time**: ${new Date().toISOString()}`);
  
  if (commoditiesData && commoditiesData.length > 0) {
    sections.push(`\n**MACD ENVIRONMENTAL SWEEP**:`);
    commoditiesData.forEach(c => {
      sections.push(`- ${c.name}: ${c.price} ${c.unit || ''} (${c.changePercent > 0 ? '+' : ''}${c.changePercent}%)`);
    });
  }

  sections.push(`\n**Target Analysis**: ${analysis.stockInfo.symbol} - ${analysis.stockInfo.name}`);
  sections.push(`**Latest Price**: ${analysis.stockInfo.price} ${analysis.stockInfo.currency}`);

  // Base output instruction
  sections.push(`\n**LANGUAGE**: MUST output in ${isZh ? 'Simplified Chinese (简体中文)' : 'English'}.`);

  return sections.join('\n');
}

function getRolePersona(role: AgentRole, isZh: boolean): string {
  switch (role) {
    case 'Technical Analyst':
      return isZh ? TECHNICAL_ANALYST_PERSONA_ZH : TECHNICAL_ANALYST_PERSONA_EN;
    case 'Fundamental Analyst':
      return isZh ? FUNDAMENTAL_ANALYST_PERSONA_ZH : FUNDAMENTAL_ANALYST_PERSONA_EN;
    case 'Chief Strategist':
      return isZh ? CHIEF_STRATEGIST_PERSONA_ZH : CHIEF_STRATEGIST_PERSONA_EN;
    default:
      return isZh ? `你是一位 ${role}。` : `You are a ${role}.`;
  }
}

function getRoleExamples(role: AgentRole, isZh: boolean): string | null {
  switch (role) {
    case 'Technical Analyst':
      return isZh ? TECHNICAL_ANALYST_EXAMPLES_ZH : TECHNICAL_ANALYST_EXAMPLES_EN;
    case 'Chief Strategist':
      return isZh ? CHIEF_STRATEGIST_EXAMPLES_ZH : CHIEF_STRATEGIST_EXAMPLES_EN;
    default:
      return null;
  }
}
