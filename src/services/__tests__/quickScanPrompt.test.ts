import { describe, it, expect } from 'vitest';
import { getQuickScanPrompt } from '../prompts';

describe('getQuickScanPrompt', () => {
  const realtimeData = {
    symbol: '600519',
    name: '贵州茅台',
    price: 1800,
    change: 20,
    changePercent: 1.1,
  };

  it('contains the symbol', () => {
    const prompt = getQuickScanPrompt('600519', 'A-Share', realtimeData, '2026-03-27');
    expect(prompt).toContain('600519');
  });

  it('contains the market', () => {
    const prompt = getQuickScanPrompt('600519', 'A-Share', realtimeData, '2026-03-27');
    expect(prompt).toContain('A-Share');
  });

  it('contains realtime data', () => {
    const prompt = getQuickScanPrompt('600519', 'A-Share', realtimeData, '2026-03-27');
    expect(prompt).toContain('1800');
  });

  it('contains date', () => {
    const prompt = getQuickScanPrompt('600519', 'A-Share', realtimeData, '2026-03-27');
    expect(prompt).toContain('2026-03-27');
  });

  it('requests simplified JSON output fields', () => {
    const prompt = getQuickScanPrompt('600519', 'A-Share', realtimeData, '2026-03-27');
    expect(prompt).toContain('stockInfo');
    expect(prompt).toContain('score');
    expect(prompt).toContain('sentiment');
    expect(prompt).toContain('recommendation');
    expect(prompt).toContain('summary');
    expect(prompt).toContain('keyRisks');
    expect(prompt).toContain('keyOpportunities');
  });

  it('is shorter than the full analysis prompt', () => {
    const quickPrompt = getQuickScanPrompt('600519', 'A-Share', realtimeData, '2026-03-27');
    // Quick scan prompt should be concise (~50 lines per spec)
    expect(quickPrompt.length).toBeLessThan(3000);
  });
});
