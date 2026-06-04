import { describe, expect, it } from 'vitest';
import fs from 'fs';

describe('vite security configuration', () => {
  it('does not inject server-side provider keys into browser bundle config', () => {
    const config = fs.readFileSync('vite.config.ts', 'utf8');

    expect(config).not.toContain('process.env.GEMINI_API_KEY');
    expect(config).not.toContain('process.env.DEEPSEEK_API_KEY');
  });
});
