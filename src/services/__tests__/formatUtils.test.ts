import { describe, it, expect } from 'vitest';
import { formatCommoditiesToMarkdown } from '../formatUtils';

describe('formatUtils', () => {
  describe('formatCommoditiesToMarkdown', () => {
    it('should return placeholder for empty array', () => {
      expect(formatCommoditiesToMarkdown([])).toBe('No real-time commodity data available.');
    });

    it('should return placeholder for null/undefined', () => {
      expect(formatCommoditiesToMarkdown(null as any)).toBe('No real-time commodity data available.');
      expect(formatCommoditiesToMarkdown(undefined as any)).toBe('No real-time commodity data available.');
    });

    it('should format single commodity as markdown table', () => {
      const data = [{
        name: '伦敦金 (XAU)',
        symbol: 'GC=F',
        price: 2350,
        changePercent: 1.5,
        unit: '$/oz',
        lastUpdated: '2026-04-01 15:00 CST',
      }];
      const result = formatCommoditiesToMarkdown(data);
      expect(result).toContain('| 商品种类 |');
      expect(result).toContain('伦敦金 (XAU)');
      expect(result).toContain('$2350');
      expect(result).toContain('+1.5%');
      expect(result).toContain('$/oz');
    });

    it('should format negative change correctly', () => {
      const data = [{
        name: '原油 (WTI)',
        symbol: 'CL=F',
        price: 75,
        changePercent: -2.3,
        unit: '$/bbl',
        lastUpdated: '2026-04-01',
      }];
      const result = formatCommoditiesToMarkdown(data);
      expect(result).toContain('-2.3%');
    });

    it('should format multiple commodities', () => {
      const data = [
        { name: 'Gold', symbol: 'GC=F', price: 2350, changePercent: 1.5, unit: '$/oz', lastUpdated: 'now' },
        { name: 'Oil', symbol: 'CL=F', price: 75, changePercent: -0.8, unit: '$/bbl', lastUpdated: 'now' },
        { name: 'Copper', symbol: 'HG=F', price: 4.2, changePercent: 0.3, unit: '$/lb', lastUpdated: 'now' },
      ];
      const result = formatCommoditiesToMarkdown(data);
      expect(result).toContain('Gold');
      expect(result).toContain('Oil');
      expect(result).toContain('Copper');
      // Should have header + separator + 3 data rows
      const lines = result.trim().split('\n');
      expect(lines.length).toBe(5);
    });
  });
});
