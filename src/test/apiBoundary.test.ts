import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

function readSourceFiles(dir: string): Array<{ file: string; content: string }> {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (['test', '__tests__'].includes(entry.name)) return [];
      return readSourceFiles(fullPath);
    }
    if (!/\.(ts|tsx)$/.test(entry.name)) return [];
    return [{ file: fullPath, content: fs.readFileSync(fullPath, 'utf8') }];
  });
}

describe('API boundary contract', () => {
  it('exposes a versioned API namespace while preserving legacy routes', () => {
    const server = fs.readFileSync('server.ts', 'utf8');

    expect(server).toContain("app.use('/api/v1'");
    expect(server).toContain("app.use('/api'");
  });

  it('does not allow browser-side provider key fallback calls', () => {
    const provider = fs.readFileSync('src/services/llmProvider.ts', 'utf8');

    expect(provider).not.toContain('VITE_OPENAI_API_KEY');
    expect(provider).not.toContain('VITE_ANTHROPIC_API_KEY');
    expect(provider).not.toContain('https://api.openai.com/v1');
    expect(provider).not.toContain('https://api.anthropic.com/v1');
  });

  it('keeps server-side provider secrets out of browser source files', () => {
    const sourceFiles = readSourceFiles('src');
    const forbidden = [
      'process.env.GEMINI_API_KEY',
      'process.env.DEEPSEEK_API_KEY',
      'process.env.OPENAI_API_KEY',
      'process.env.ANTHROPIC_API_KEY',
      'VITE_GEMINI_API_KEY',
      'VITE_OPENAI_API_KEY',
      'VITE_ANTHROPIC_API_KEY',
      'VITE_DEEPSEEK_API_KEY',
    ];

    const violations = sourceFiles.flatMap(({ file, content }) =>
      forbidden.filter((token) => content.includes(token)).map((token) => `${file}: ${token}`),
    );

    expect(violations).toEqual([]);
  });

  it('does not call diagnostics routes from browser source files', () => {
    const violations = readSourceFiles('src')
      .filter(({ content }) => content.includes('/api/diagnostics'))
      .map(({ file }) => file);

    expect(violations).toEqual([]);
  });

  it('keeps THS chart legend rendering free of raw HTML injection', () => {
    const chart = fs.readFileSync('src/components/dashboard/ThsKlineChart.tsx', 'utf8');

    expect(chart).not.toContain('innerHTML');
    expect(chart).not.toContain('buildLegendHtml');
    expect(chart).toContain('textContent');
    expect(chart).toContain('replaceChildren');
  });

});
