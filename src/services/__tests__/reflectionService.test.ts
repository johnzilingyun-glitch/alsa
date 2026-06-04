import { describe, expect, it, vi, beforeEach } from 'vitest';
import { formatMemoryForPrompt, retrieveMemories } from '../reflectionService';


describe('retrieveMemories', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('handles legacy memory entries without lessons or reflections', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => [
        { symbol: 'AAPL', timestamp: new Date().toISOString(), marketContext: 'US tech' },
      ],
    } as Response);

    await expect(retrieveMemories('AAPL', 'US tech')).resolves.toHaveLength(1);
  });

  it('formats legacy memory entries without optional fields', () => {
    const formatted = formatMemoryForPrompt([
      { entry: { symbol: 'AAPL', timestamp: '2026-06-01', marketContext: 'US tech' } as any, relevanceScore: 10 },
    ]);

    expect(formatted).toContain('AAPL');
    expect(formatted).toContain('N/A');
  });
});
