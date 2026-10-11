/**
 * scripts/harness.mjs
 * KIMIDORI YouTube Auto - Autonomous Verification & Build Harness
 * Executes TypeScript typecheck (tsc --noEmit) and Next.js production build (npm run build),
 * returning explicit Exit Code 0 on pass or Exit Code 1 on failure.
 */
import { spawn } from 'node:child_process';
import process from 'node:process';

const isWindows = process.platform === 'win32';
const npmCmd = isWindows ? 'npm.cmd' : 'npm';
const npxCmd = isWindows ? 'npx.cmd' : 'npx';

const steps = [
  {
    name: 'TypeScript Typecheck (tsc --noEmit)',
    command: npxCmd,
    args: ['tsc', '--noEmit'],
  },
  {
    name: 'Application Production Build (next build)',
    command: npmCmd,
    args: ['run', 'build'],
  },
];

function runStep(step) {
  return new Promise((resolve, reject) => {
    console.log('\n========================================');
    console.log(`[HARNESS] Starting: ${step.name}`);
    console.log(`[COMMAND] ${step.command} ${step.args.join(' ')}`);
    console.log('========================================\n');

    const child = spawn(step.command, step.args, {
      stdio: 'inherit',
      shell: isWindows,
    });

    child.on('error', (err) => {
      reject(new Error(`Failed to spawn ${step.name}: ${err.message}`));
    });

    child.on('close', (code) => {
      if (code === 0) {
        console.log(`\n[PASS] ${step.name} completed with Exit Code 0.`);
        resolve();
      } else {
        reject(new Error(`[FAIL] ${step.name} exited with code ${code}`));
      }
    });
  });
}

async function main() {
  const startTime = Date.now();
  console.log('[HARNESS] Starting autonomous verification pipeline for KIMIDORI YouTube Auto...');

  for (const step of steps) {
    try {
      await runStep(step);
    } catch (err) {
      console.error(`\n[HARNESS FATAL] ${err.message}`);
      console.error('[HARNESS] Verification failed. Fix the reported errors and re-run npm run harness:check.');
      process.exit(1);
    }
  }

  const duration = ((Date.now() - startTime) / 1000).toFixed(2);
  console.log(`\n[HARNESS SUCCESS] All checks passed in ${duration}s (Exit Code 0).`);
  process.exit(0);
}

main();
