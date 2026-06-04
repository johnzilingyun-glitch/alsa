import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

describe('production build budget', () => {
  it('keeps explicit manual chunk boundaries configured', () => {
    const config = fs.readFileSync('vite.config.ts', 'utf8');

    expect(config).toContain('manualChunks');
    expect(config).toContain('vendor-genai');
    expect(config).toContain('vendor-charts');
    expect(config).toContain('vendor-motion');
  });

  it('keeps built JavaScript chunks below Vite warning threshold when dist exists', () => {
    const assetsDir = path.join('dist', 'assets');
    if (!fs.existsSync(assetsDir)) return;

    const oversized = fs.readdirSync(assetsDir)
      .filter((file) => file.endsWith('.js'))
      .map((file) => ({ file, sizeKb: fs.statSync(path.join(assetsDir, file)).size / 1024 }))
      .filter(({ sizeKb }) => sizeKb > 500);

    expect(oversized).toEqual([]);
  });
});
