import type { CoreVariable, StockAnalysis } from '../types';

type SourceTier = 1 | 2 | 3;

function normalizeName(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[()（）\-_/]/g, '');
}

function sourceTier(source?: string): SourceTier {
  const s = (source || '').toLowerCase();
  if (!s) return 3;

  // Tier 1: API or clearly authoritative exchange/feed style sources
  if (
    s.includes('api') ||
    s.includes('realtime') ||
    s.includes('实时') ||
    s.includes('交易所') ||
    s.includes('exchange') ||
    s.includes('wind') ||
    s.includes('彭博') ||
    s.includes('bloomberg') ||
    s.includes('路透') ||
    s.includes('reuters') ||
    s.includes('中金所') ||
    s.includes('上交所') ||
    s.includes('深交所') ||
    s.includes('中国外汇交易中心')
  ) {
    return 1;
  }

  // Tier 2: search-derived but usually reliable portals/media
  if (
    s.includes('google') ||
    s.includes('search') ||
    s.includes('东方财富') ||
    s.includes('同花顺') ||
    s.includes('investing') ||
    s.includes('yahoo') ||
    s.includes('lme') ||
    s.includes('生意社')
  ) {
    return 2;
  }

  // Tier 3: fallback / other
  return 3;
}

function parseDateScore(dataDate?: string): number {
  if (!dataDate) return 0;
  const t = Date.parse(dataDate);
  return Number.isFinite(t) ? t : 0;
}

function chooseBetter(a: CoreVariable, b: CoreVariable): CoreVariable {
  const ta = sourceTier(a.source);
  const tb = sourceTier(b.source);

  if (ta !== tb) return ta < tb ? a : b;

  const da = parseDateScore(a.dataDate);
  const db = parseDateScore(b.dataDate);
  if (da !== db) return da > db ? a : b;

  return a;
}

function toStringValue(v: unknown): string {
  if (v == null) return '';
  return String(v);
}

function enrichFromApi(variable: CoreVariable, analysis: StockAnalysis): CoreVariable {
  const key = normalizeName(variable.name);
  const fundamentals = analysis.fundamentals;

  // Strong deterministic mapping for common financial anchors
  const mappings: Array<{ match: RegExp; value: unknown }> = [
    { match: /(当前股价|现价|price|收盘价)/i, value: analysis.stockInfo?.price },
    { match: /(pe|市盈率)/i, value: fundamentals?.pe },
    { match: /(pb|市净率)/i, value: fundamentals?.pb },
    { match: /(roe|净资产收益率)/i, value: fundamentals?.roe },
    { match: /(eps|每股收益)/i, value: fundamentals?.eps },
    { match: /(股息率|dividend)/i, value: fundamentals?.dividendYield },
  ];

  for (const m of mappings) {
    if (m.match.test(variable.name) && m.value != null && m.value !== '') {
      return {
        ...variable,
        value: m.value as any,
        source: analysis.stockInfo?.dataSource || 'API',
        dataDate: analysis.stockInfo?.lastUpdated?.slice(0, 10) || variable.dataDate,
      };
    }
  }

  // Keep for potential future expansions where name is normalized exact key
  if (key.includes('price') && analysis.stockInfo?.price != null) {
    return {
      ...variable,
      value: analysis.stockInfo.price,
      source: analysis.stockInfo?.dataSource || 'API',
      dataDate: analysis.stockInfo?.lastUpdated?.slice(0, 10) || variable.dataDate,
    };
  }

  return variable;
}

export function normalizeCoreVariablesByPriority(
  coreVariables: CoreVariable[] | undefined,
  analysis: StockAnalysis,
): CoreVariable[] | undefined {
  if (!coreVariables || coreVariables.length === 0) return coreVariables;

  const picked = new Map<string, CoreVariable>();

  for (const item of coreVariables) {
    const nameKey = normalizeName(item.name || '');
    if (!nameKey) continue;

    const current = picked.get(nameKey);
    if (!current) {
      picked.set(nameKey, item);
      continue;
    }

    picked.set(nameKey, chooseBetter(current, item));
  }

  const merged = Array.from(picked.values()).map((v) => {
    let next = v;

    // If source is missing or low-priority, attempt deterministic API override
    const tier = sourceTier(v.source);
    if (tier > 1 || !v.source) {
      next = enrichFromApi(v, analysis);
    }

    // Keep source/date visible for traceability
    if (!next.source) {
      next = { ...next, source: 'Other' };
    }
    if (!next.dataDate) {
      const fallbackDate =
        analysis.stockInfo?.lastUpdated?.slice(0, 10) ||
        new Date().toISOString().slice(0, 10);
      next = { ...next, dataDate: fallbackDate };
    }

    // add minimal audit note without breaking existing text
    if (next.reason) {
      const audit = `口径: ${toStringValue(next.source)} 优先级${sourceTier(next.source)}`;
      if (!next.reason.includes('口径:')) {
        next = { ...next, reason: `${next.reason} | ${audit}` };
      }
    }

    return next;
  });

  return merged;
}
