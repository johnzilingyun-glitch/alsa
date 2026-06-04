import { execFileSync } from 'node:child_process';

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

const tracked = execFileSync('git', ['ls-files'], { encoding: 'utf8' })
  .split(/\r?\n/)
  .filter(Boolean);

const offenders = tracked.filter((file) => forbidden.some((pattern) => pattern.test(file)));

if (offenders.length > 0) {
  console.error('Forbidden generated/sensitive files are tracked by git:');
  for (const offender of offenders) console.error(`- ${offender}`);
  process.exit(1);
}

console.log('Repository hygiene check passed.');
