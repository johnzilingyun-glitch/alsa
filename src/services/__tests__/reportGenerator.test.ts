import { describe, it, expect } from 'vitest';
import { ReportGeneratorService } from '../reportGenerator';
import { StockAnalysis } from '../../types';

describe('ReportGeneratorService', () => {
  it('should generate a professional HTML report', () => {
    const mockAnalysis: any = {
      stockInfo: { symbol: '00700', name: 'Tencent', price: 400, currency: 'HKD' },
      score: 85,
      recommendation: 'Buy'
    };
    const html = ReportGeneratorService.generateProfessionalHtmlReport(mockAnalysis as StockAnalysis, 'zh-CN');
    expect(html).toContain('Tencent');
    expect(html).toContain('00700');
    expect(html).toContain('DOCTYPE html');
  });
});
