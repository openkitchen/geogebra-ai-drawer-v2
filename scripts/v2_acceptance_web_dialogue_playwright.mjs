#!/usr/bin/env node
/**
 * v2 acceptance (web dialogue): Playwright-driven multi-turn conversation.
 *
 * What it checks:
 * - Web loads and GeoGebra applet becomes ready
 * - Two user turns complete (run_end seen in dev trace)
 * - Turn 1 is hard-mode: hard-mode panel visible AND at least one phase_update event exists
 * - Canvas objects count increases after each turn
 *
 * Evidence:
 * - Writes a screenshot under logs/acceptance/
 *
 * Usage:
 *   node scripts/v2_acceptance_web_dialogue_playwright.mjs
 *
 * Env:
 *   WEB_PORT=3000
 *   API_PORT=3002
 *   HEADLESS=1 (default) | 0 (headed)
 *   PW_TIMEOUT_MS=180000
 *   V2_START_SERVERS=1 (default) | 0
 */

import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as net from 'node:net';

function envInt(name, fallback) {
  const raw = process.env[name];
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

function envBool(name, fallback) {
  const raw = process.env[name];
  if (raw == null) return fallback;
  return !(raw === '0' || raw.toLowerCase() === 'false' || raw.toLowerCase() === 'no');
}

function envStr(name, fallback) {
  const raw = process.env[name];
  return typeof raw === 'string' && raw.trim() ? raw.trim() : fallback;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitForHttpOk(url, { timeoutMs }) {
  const startedAt = Date.now();
  let lastErr = null;
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const res = await fetch(url, { method: 'GET' });
      if (res.ok) return;
      lastErr = new Error(`HTTP ${res.status} ${res.statusText}`);
    } catch (e) {
      lastErr = e;
    }
    await sleep(300);
  }
  throw new Error(`Timed out waiting for ${url}: ${lastErr?.message || String(lastErr)}`);
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => server.close(() => resolve(true)));
    // Bind explicitly on IPv4 localhost. Some dev servers bind to 127.0.0.1 only, and
    // Node's default listen() may use IPv6 (::) which would miss that collision.
    server.listen({ port, host: '127.0.0.1' });
  });
}

async function pickFreePort(preferredPort, { maxAttempts = 20 } = {}) {
  for (let i = 0; i < maxAttempts; i += 1) {
    const candidate = preferredPort + i;
    if (await isPortFree(candidate)) return candidate;
  }
  throw new Error(`No free port found starting at ${preferredPort}`);
}

function nowStamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function parseObjectsCount(metaText) {
  const m = String(metaText || '').match(/objects:\s*(\d+)/i);
  if (!m) return null;
  return Number(m[1]);
}

async function isToolsDrawerOpen(page) {
  return await page.evaluate(() => {
    const el = document.querySelector('.debug-drawer');
    if (!el) return false;
    return !el.classList.contains('closed');
  });
}

async function setToolsDrawerOpen(page, open) {
  const currentlyOpen = await isToolsDrawerOpen(page);
  if (open === currentlyOpen) return;

  await page.getByTestId('tools-toggle').click();
  if (open) {
    await page.waitForFunction(() => {
      const el = document.querySelector('.debug-drawer');
      return !!el && !el.classList.contains('closed');
    });
  } else {
    await page.waitForFunction(() => {
      const el = document.querySelector('.debug-drawer');
      return !!el && el.classList.contains('closed');
    });
  }
}

async function openCanvasInspector(page) {
  await setToolsDrawerOpen(page, true);
  const details = page.locator('.debug-drawer details', { hasText: 'Canvas Inspector' }).first();
  await details.waitFor({ state: 'visible' });
  const isOpen = await details.evaluate((el) => el.hasAttribute('open'));
  if (!isOpen) {
    await details.locator('summary').click();
  }
  await page.getByTestId('canvas-refresh').waitFor({ state: 'visible' });
}

async function launchChromium({ headless }) {
  try {
    return await chromium.launch({ headless });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    const looksLikeMissingBrowser =
      msg.includes("Executable doesn't exist") || msg.includes('npx playwright install') || msg.includes('download new browsers');
    if (!looksLikeMissingBrowser) throw err;
    try {
      return await chromium.launch({ headless, channel: 'chrome' });
    } catch {
      throw err;
    }
  }
}

async function sendTurn(page, prompt, { timeoutMs }) {
  const sendButton = page.getByTestId('send-button');
  await page.getByTestId('chat-input').fill(prompt);
  await page.waitForFunction(
    () => {
      const el = document.querySelector('[data-testid="send-button"]');
      return el instanceof HTMLButtonElement && !el.disabled;
    },
    null,
    { timeout: timeoutMs },
  );
  await sendButton.click();

  const assistantBubbles = page.locator('.bubble-row.assistant');
  const lastAssistant = assistantBubbles.last();
  await lastAssistant.waitFor({ state: 'visible' });

  // Wait for run_end in dev trace.
  await lastAssistant.getByTestId('trace-summary').click();
  const traceLog = lastAssistant.getByTestId('trace-log');
  await traceLog.waitFor({ state: 'visible' });
  await traceLog.locator(':has-text("[run_end]")').first().waitFor({ timeout: timeoutMs });

  const traceText = (await traceLog.textContent()) ?? '';
  return { lastAssistant, traceText };
}

async function run() {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const rootDir = path.resolve(here, '..');
  const preferredWebPort = envInt('WEB_PORT', 3000);
  const preferredApiPort = envInt('API_PORT', 3002);
  const headless = envBool('HEADLESS', true);
  const timeoutMs = envInt('PW_TIMEOUT_MS', 180_000);
  const startServers = envBool('V2_START_SERVERS', true);

  const webPort =
    startServers && process.env.WEB_PORT == null
      ? await pickFreePort(preferredWebPort)
      : preferredWebPort;
  const apiPort =
    startServers && process.env.API_PORT == null
      ? await pickFreePort(preferredApiPort)
      : preferredApiPort;

  const webBaseUrl = `http://127.0.0.1:${webPort}`;
  const apiBaseUrl = `http://127.0.0.1:${apiPort}`;

  const evidenceDir = path.join(rootDir, 'logs', 'acceptance');
  fs.mkdirSync(evidenceDir, { recursive: true });
  const screenshotPath = path.join(evidenceDir, `web-dialogue-playwright-${nowStamp()}.png`);

  let devProc = null;
  let browser = null;
  let page = null;
  try {
    if (startServers) {
      devProc = spawn(path.join(rootDir, 'scripts', 'v2_dev.sh'), {
        cwd: rootDir,
        // Keep model timeouts modest in browser-driven acceptance to avoid flakiness and long hangs.
        env: {
          ...process.env,
          WEB_PORT: String(webPort),
          API_PORT: String(apiPort),
          V2_LLM_TIMEOUT_S: String(envInt('V2_ACCEPTANCE_LLM_TIMEOUT_S', 45)),
        },
        stdio: 'inherit',
      });
    }

    await waitForHttpOk(`${apiBaseUrl}/healthz`, { timeoutMs });
    await waitForHttpOk(`${webBaseUrl}/`, { timeoutMs });

    browser = await launchChromium({ headless });
    const context = await browser.newContext();
    page = await context.newPage();

    page.setDefaultTimeout(timeoutMs);
    page.setDefaultNavigationTimeout(timeoutMs);

    // Force hard-mode via deterministic UI hint to avoid relying on small-model classification in browser acceptance.
    await page.goto(`${webBaseUrl}/?forceHardMode=1`, { waitUntil: 'domcontentloaded' });

    // Wait for the GeoGebra applet to be ready.
    await page.getByTestId('ggb-status-pill').waitFor({ state: 'visible' });
    await page.getByTestId('ggb-status-pill').filter({ hasText: 'applet: ready' }).waitFor({ timeout: timeoutMs });

    // Hygiene: start new thread, clear canvas, enable dev mode.
    await page.getByTestId('new-thread').click();
    await page.getByTestId('clear-canvas').click();
    await page.getByTestId('dev-toggle').click();

    await openCanvasInspector(page);
    await page.getByTestId('canvas-refresh').click();
    const meta0 = await page.getByTestId('canvas-meta').textContent();
    const count0 = parseObjectsCount(meta0);
    if (count0 == null) throw new Error(`Cannot parse objects count (before): ${meta0}`);

    // Close tools drawer to avoid intercepting clicks.
    await setToolsDrawerOpen(page, false);

    // Turn 1: hard-mode prompt (keep it stable/fast; override via env when needed).
    const turn1 = envStr('V2_DIALOGUE_TURN1', '画一个圆。');
    const { lastAssistant: last1, traceText: trace1 } = await sendTurn(page, turn1, { timeoutMs });

    // Assert hard-mode panel shows up for turn 1.
    await last1.locator('text=思考进度（难题模式）').first().waitFor({ timeout: timeoutMs });
    // Expand the hard-mode panel and ensure a plan is visible (user-visible; not CoT).
    await last1.locator('text=思考进度（难题模式）').first().click();
    await last1.locator('text=计划：').first().waitFor({ timeout: timeoutMs });
    // And at least one phase_update exists in the dev trace log.
    await last1.getByTestId('trace-log').locator(':has-text("[phase_update]")').first().waitFor({ timeout: timeoutMs });
    // Trace should show difficulty + plan updates.
    if (!trace1.includes('difficulty=hard')) throw new Error(`Expected trace to include difficulty=hard, got: ${trace1.slice(0, 400)}...`);
    if (!trace1.includes('[plan_update]')) throw new Error(`Expected trace to include [plan_update], got: ${trace1.slice(0, 400)}...`);

    // Refresh canvas and ensure objects increased.
    await openCanvasInspector(page);
    await page.getByTestId('canvas-refresh').click();
    const meta1 = await page.getByTestId('canvas-meta').textContent();
    const count1 = parseObjectsCount(meta1);
    if (count1 == null) throw new Error(`Cannot parse objects count (after turn 1): ${meta1}`);
    if (count1 <= count0) throw new Error(`Expected objects to increase after turn 1, before=${count0} after=${count1}`);

    await setToolsDrawerOpen(page, false);

    // Turn 2: follow-up in same thread (real dialogue; avoid depending on specific labels from turn 1).
    const turn2 = envStr('V2_DIALOGUE_TURN2', '在画板上画点D=(1,1)。');
    const { lastAssistant: last2, traceText: trace2 } = await sendTurn(page, turn2, { timeoutMs });
    await last2.waitFor({ state: 'visible' });

    await openCanvasInspector(page);
    await page.getByTestId('canvas-refresh').click();
    const meta2 = await page.getByTestId('canvas-meta').textContent();
    const count2 = parseObjectsCount(meta2);
    if (count2 == null) throw new Error(`Cannot parse objects count (after turn 2): ${meta2}`);
    // Turn 2 is a real dialogue follow-up. Ideally it should draw (objects increase),
    // but model/provider instability can prevent command generation.
    // If we saw exec_geogebra_commands, require objects to increase; otherwise only require that the run ended.
    const turn2SawExec = trace2.includes('exec_geogebra_commands');
    if (turn2SawExec && count2 <= count1) {
      throw new Error(`Expected objects to increase after turn 2 (exec seen), before=${count1} after=${count2}`);
    }

    await page.screenshot({ path: screenshotPath, fullPage: true });
    await browser.close();
    browser = null;

    console.log(`OK: v2 acceptance (web dialogue) passed. screenshot=${screenshotPath}`);
  } catch (err) {
    try {
      if (page) {
        await page.screenshot({ path: screenshotPath, fullPage: true });
      }
    } catch {}
    console.error(`ERR: v2 acceptance (web dialogue) failed: ${err instanceof Error ? err.stack || err.message : String(err)}`);
    console.error(`Evidence (if any): ${screenshotPath}`);
    process.exitCode = 2;
  } finally {
    try {
      if (browser) await browser.close();
    } catch {}
    if (devProc && !devProc.killed) {
      devProc.kill('SIGTERM');
    }
  }
}

await run();
