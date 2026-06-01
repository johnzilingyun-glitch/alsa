/**
 * Cross-platform IBKR Gateway launcher.
 * Detects OS and runs the appropriate script (PowerShell on Windows, bash on Unix).
 * Usage: node scripts/start-ibkr-gateway.js [--docker|--local|--stop|--auto]
 */
import { spawn } from 'child_process';
import { existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const args = process.argv.slice(2);
const isWindows = process.platform === 'win32';

if (isWindows) {
  const ps1Script = path.join(__dirname, 'start-ibkr-gateway.ps1');
  if (!existsSync(ps1Script)) {
    console.error('[IBKR] PowerShell script not found:', ps1Script);
    process.exit(1);
  }

  // Normalize arguments for PowerShell script parameter binding
  const psArgs = [];
  for (const arg of args) {
    if (arg === '--stop' || arg === '-stop' || arg === '-s' || arg === 'stop') {
      psArgs.push('-Mode', 'stop');
    } else if (arg === '--local' || arg === '-local' || arg === '-l' || arg === 'local') {
      psArgs.push('-Mode', 'local');
    } else if (arg === '--docker' || arg === '-docker' || arg === '-d' || arg === 'docker') {
      psArgs.push('-Mode', 'docker');
    } else if (arg === '--auto' || arg === '-auto' || arg === '-a' || arg === 'auto') {
      psArgs.push('-Mode', 'auto');
    } else {
      psArgs.push(arg);
    }
  }

  const child = spawn(
    'powershell',
    ['-ExecutionPolicy', 'Bypass', '-File', ps1Script, ...psArgs],
    { stdio: 'inherit', shell: false }
  );
  child.on('close', (code) => process.exit(code ?? 0));
} else {
  const shScript = path.join(__dirname, 'start-ibkr-gateway.sh');
  if (!existsSync(shScript)) {
    console.error('[IBKR] Bash script not found:', shScript);
    process.exit(1);
  }
  const child = spawn('bash', [shScript, ...args], { stdio: 'inherit' });
  child.on('close', (code) => process.exit(code ?? 0));
}
