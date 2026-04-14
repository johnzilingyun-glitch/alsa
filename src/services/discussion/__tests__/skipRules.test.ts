import { describe, it, expect } from 'vitest';
import { getSkipRoles } from '../skipRules';

describe('skipRules', () => {
  it('returns no skip roles for stock', () => {
    expect(getSkipRoles('stock')).toEqual([]);
  });

  it('skips Deep Research + Fundamental for ETF', () => {
    const roles = getSkipRoles('etf');
    expect(roles).toContain('Deep Research Specialist');
    expect(roles).toContain('Fundamental Analyst');
  });

  it('skips Deep Research + Fundamental for index', () => {
    const roles = getSkipRoles('index');
    expect(roles).toContain('Deep Research Specialist');
    expect(roles).toContain('Fundamental Analyst');
  });

  it('skips Technical Analyst for bond', () => {
    const roles = getSkipRoles('bond');
    expect(roles).toContain('Technical Analyst');
  });
});
