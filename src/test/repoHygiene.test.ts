import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

const forbidden = [
  /(^|\/)data\//,
  /(^|\/)python_service\/data\//,
  /(^|\/)reports\//,
  /(^|\/)logs\//,
  /\.db$/,
  /\.parquet$/,
  /\.log$/,
  /(^|\/)\.env$/,
  /(^|\/)keys\.txt$/,
];

describe('repository hygiene', () => {
  it('does not track generated data, reports, logs, or local secret files', () => {
    const tracked = execFileSync('git', ['ls-files'], { encoding: 'utf8' })
      .split(/\r?\n/)
      .filter(Boolean);
    const offenders = tracked.filter((file) => forbidden.some((pattern) => pattern.test(file)));

    expect(offenders).toEqual([]);
  });
});
