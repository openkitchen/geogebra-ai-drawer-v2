import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';

const projectRoot = process.cwd();

function readIfExists(p) {
  try {
    return fs.existsSync(p) ? fs.readFileSync(p, 'utf-8') : '';
  } catch {
    return '';
  }
}

dotenv.config({ path: path.join(projectRoot, '.env.local'), override: false });
dotenv.config({ path: path.join(projectRoot, '.env'), override: false });

const report = {
  node: process.versions.node,
  apiProxyPort: process.env.API_PROXY_PORT || '3002 (default)',
  hasEnvLocal: fs.existsSync(path.join(projectRoot, '.env.local')),
  hasEnv: fs.existsSync(path.join(projectRoot, '.env')),
  providers: { ok: false, count: 0, error: null },
};

const raw = process.env.LLM_ENDPOINTS_JSON;
if (!raw) {
  report.providers.error = 'LLM_ENDPOINTS_JSON is not set (see .env.example or docs/env.example.md)';
} else {
  try {
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) throw new Error('LLM_ENDPOINTS_JSON must be an array');
    report.providers.ok = true;
    report.providers.count = arr.length;
  } catch (e) {
    report.providers.error = String(e?.message || e || 'Unknown parse error');
  }
}

const hasSecretsLike = (s) => /\b(sk-|AIza)\w+/.test(String(s || ''));
const envLocalText = readIfExists(path.join(projectRoot, '.env.local'));
if (envLocalText && hasSecretsLike(envLocalText)) {
  report.warning = 'Detected key-like patterns in .env.local. Do not commit real keys.';
}

console.log(JSON.stringify(report, null, 2));

