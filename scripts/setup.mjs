import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';

const projectRoot = process.cwd();

function fileExists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

function ensureEnvLocal() {
  const envLocal = path.join(projectRoot, '.env.local');
  if (fileExists(envLocal)) return { created: false };

  const envExample = path.join(projectRoot, '.env.example');
  if (!fileExists(envExample)) {
    return {
      created: false,
      warning: 'Missing .env.example; please create .env.local manually (see docs/env.example.md).',
    };
  }

  fs.copyFileSync(envExample, envLocal);
  return { created: true };
}

function ensureDependencies() {
  const nodeModules = path.join(projectRoot, 'node_modules');
  if (fileExists(nodeModules)) return { installed: true, ranInstall: false };

  const res = spawnSync('npm', ['install'], { stdio: 'inherit', cwd: projectRoot });
  if (res.status !== 0) process.exit(res.status ?? 1);
  return { installed: true, ranInstall: true };
}

function checkNodeVersion() {
  const major = Number(String(process.versions.node).split('.')[0] || 0);
  if (major < 18) {
    console.error(`[setup] Node.js >= 18 is required. Current: ${process.versions.node}`);
    process.exit(1);
  }
}

checkNodeVersion();

const deps = ensureDependencies();
const env = ensureEnvLocal();

console.log('[setup] Done.');
if (deps.ranInstall) console.log('[setup] Dependencies installed.');
if (env.created) console.log('[setup] Created .env.local from .env.example (please fill in real keys).');
if (env.warning) console.log(`[setup] ${env.warning}`);
console.log('[setup] Next: npm run dev');

