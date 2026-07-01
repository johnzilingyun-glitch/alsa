import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const forbiddenPathPatterns = [
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

export const secretContentPatterns = [
  { name: 'OpenAI API key', pattern: /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/ },
  { name: 'Google API key', pattern: /\bAIza[0-9A-Za-z_-]{30,}\b/ },
  { name: 'JWT token', pattern: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/ },
  { name: 'AWS access key', pattern: /\bAKIA[0-9A-Z]{16}\b/ },
  { name: 'Private key block', pattern: /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/ },
  {
    name: 'Hard-coded secret assignment',
    pattern: /\b(?:API_TOKEN|JWT_SECRET_KEY|GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|DEEPSEEK_API_KEY|ADMIN_TOKEN|PASSWORD|SECRET)\s*=\s*['"][^'"\s]{12,}['"]/i,
  },
];

const textFileExtensions = new Set([
  '.cjs', '.css', '.env', '.example', '.html', '.js', '.json', '.jsx', '.md', '.mjs', '.py', '.sh', '.toml', '.ts', '.tsx', '.txt', '.yaml', '.yml',
]);

function normalizePath(file) {
  return file.replace(/\\/g, '/');
}

function isSafePlaceholderLine(line) {
  const valueMatch = line.match(/=\s*(?:['"]([^'"]+)['"]|([^#\s]+))/);
  const value = (valueMatch?.[1] || valueMatch?.[2] || '').toLowerCase();
  if (/test|dummy|mock|placeholder|example|your|change_me|changeme|<|>/.test(value)) return true;
  if (value.includes('?') && /key|token|secret|password/i.test(value)) return true;
  return /[^\x00-\x7F]/.test(value) && /key|token|secret|password/i.test(value);
}

function isTextFile(file) {
  const normalized = normalizePath(file);
  if (normalized.endsWith('.env.example')) return true;
  const dot = normalized.lastIndexOf('.');
  if (dot === -1) return false;
  return textFileExtensions.has(normalized.slice(dot).toLowerCase());
}

export function findForbiddenPathOffenders(files, patterns = forbiddenPathPatterns) {
  return files.map(normalizePath).filter((file) => patterns.some((pattern) => pattern.test(file)));
}

export function scanContentForSecrets(file, content, patterns = secretContentPatterns) {
  const findings = [];
  const lines = content.split(/\r?\n/);
  lines.forEach((line, index) => {
    for (const { name, pattern } of patterns) {
      pattern.lastIndex = 0;
      if (pattern.test(line) && !isSafePlaceholderLine(line)) {
        findings.push({ file: normalizePath(file), line: index + 1, name });
      }
    }
  });
  return findings;
}

export function auditTrackedFiles(files, readFile = (file) => fs.readFileSync(file, 'utf8')) {
  const pathOffenders = findForbiddenPathOffenders(files);
  const secretFindings = files
    .map(normalizePath)
    .filter(isTextFile)
    .flatMap((file) => {
      try {
        return scanContentForSecrets(file, readFile(file));
      } catch {
        return [];
      }
    });

  return { pathOffenders, secretFindings };
}

function getTrackedFiles() {
  return execFileSync('git', ['ls-files'], { encoding: 'utf8' })
    .split(/\r?\n/)
    .filter(Boolean);
}

export function runCli() {
  const { pathOffenders, secretFindings } = auditTrackedFiles(getTrackedFiles());
  let failed = false;

  if (pathOffenders.length > 0) {
    failed = true;
    console.error('Forbidden generated/sensitive files are tracked by git:');
    for (const offender of pathOffenders) console.error(`- ${offender}`);
  }

  if (secretFindings.length > 0) {
    failed = true;
    console.error('Potential secrets found in tracked files:');
    for (const finding of secretFindings) console.error(`- ${finding.file}:${finding.line} (${finding.name})`);
  }

  if (failed) process.exit(1);
  console.log('Repository hygiene check passed.');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  runCli();
}
