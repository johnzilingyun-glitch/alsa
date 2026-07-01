import assert from 'node:assert/strict';
import test from 'node:test';
import {
  auditTrackedFiles,
  findForbiddenPathOffenders,
  scanContentForSecrets,
} from './audit-repo-hygiene.js';

test('findForbiddenPathOffenders detects generated tracked files', () => {
  assert.deepEqual(
    findForbiddenPathOffenders(['src/App.tsx', 'reports/demo.html', 'python_service/data/cache.db', 'safe.env.example']),
    ['reports/demo.html', 'python_service/data/cache.db'],
  );
});

test('scanContentForSecrets detects common secret patterns', () => {
  const findings = scanContentForSecrets(
    'src/config.ts',
    [
      'const safe = "placeholder";',
      `OPENAI_API_KEY="${'sk-proj-' + 'abcdefghijklmnopqrstuvwxyz'}"`,
      `JWT_SECRET_KEY="${'super-secret-' + 'value-12345'}"`,
    ].join('\n'),
  );

  assert.deepEqual(findings.map((finding) => `${finding.line}:${finding.name}`), [
    '2:OpenAI API key',
    '2:Hard-coded secret assignment',
    '3:Hard-coded secret assignment',
  ]);
});

test('scanContentForSecrets ignores safe placeholder and test values', () => {
  const findings = scanContentForSecrets(
    'src/setup.ts',
    [
      "process.env.API_TOKEN = 'test-token-for-analysis-routes';",
      'GEMINI_API_KEY="your-gemini-api-key"',
      'ADMIN_TOKEN="change_me_in_production"',
      'GEMINI_API_KEY="??_GEMINI_API_KEY"',
    ].join('\n'),
  );

  assert.deepEqual(findings, []);
});

test('auditTrackedFiles combines path and content findings', () => {
  const files = ['src/config.ts', 'reports/out.html'];
  const result = auditTrackedFiles(files, (file) => {
    if (file === 'src/config.ts') return 'const token = "not-real";\nADMIN_TOKEN="admin-token-value"';
    return '<html></html>';
  });

  assert.deepEqual(result.pathOffenders, ['reports/out.html']);
  assert.deepEqual(result.secretFindings, [
    { file: 'src/config.ts', line: 2, name: 'Hard-coded secret assignment' },
  ]);
});
