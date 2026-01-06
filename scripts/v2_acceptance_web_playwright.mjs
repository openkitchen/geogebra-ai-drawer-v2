#!/usr/bin/env node
/**
 * v2 acceptance (web): Playwright-driven browser smoke test.
 *
 * What it checks:
 * - Web loads and GeoGebra applet becomes ready (send button enabled)
 * - Sending a prompt triggers a run with a full interrupt/resume chain (detects [run_end] in trace)
 * - Canvas objects count increases after the draw request (via Canvas Inspector)
 *
 * Evidence:
 * - Writes a screenshot under logs/acceptance/
 *
 * Usage:
 *   node scripts/v2_acceptance_web_playwright.mjs
 *
 * Env:
 *   WEB_PORT=3000
 *   API_PORT=3002
 *   HEADLESS=1 (default) | 0 (headed)
 *   PW_TIMEOUT_MS=120000
 *   V2_START_SERVERS=1 (default) | 0 (assume already running)
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
    server.listen(port, '127.0.0.1');
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
  // Expected: "objects: 3"
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

    // Best-effort fallback: use system Chrome/Chromium without downloading Playwright browsers.
    // This is helpful in restricted or slow network environments.
    try {
      return await chromium.launch({ headless, channel: 'chrome' });
    } catch {
      throw err;
    }
  }
}

async function run() {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const rootDir = path.resolve(here, '..');
  const preferredWebPort = envInt('WEB_PORT', 3000);
  const preferredApiPort = envInt('API_PORT', 3002);
  const headless = envBool('HEADLESS', true);
  const timeoutMs = envInt('PW_TIMEOUT_MS', 120_000);
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
  const screenshotPath = path.join(evidenceDir, `web-playwright-${nowStamp()}.png`);

  let devProc = null;
  let browser = null;
  let page = null;
  try {
    if (startServers) {
      devProc = spawn(path.join(rootDir, 'scripts', 'v2_dev.sh'), {
        cwd: rootDir,
        env: { ...process.env, WEB_PORT: String(webPort), API_PORT: String(apiPort) },
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

    // Force hard-mode hint from UI so we can assert hard-mode progress panel rendering deterministically.
    await page.goto(`${webBaseUrl}/?forceHardMode=1`, { waitUntil: 'domcontentloaded' });

    // Wait for the GeoGebra applet to be ready.
    await page.getByTestId('ggb-status-pill').waitFor({ state: 'visible' });
    await page.getByTestId('ggb-status-pill').filter({ hasText: 'applet: ready' }).waitFor({ timeout: timeoutMs });

    const sendButton = page.getByTestId('send-button');
    await sendButton.waitFor({ state: 'visible' });

    // Optional hygiene: clear canvas and start new thread.
    await page.getByTestId('new-thread').click();
    await page.getByTestId('clear-canvas').click();

    // Enable dev mode + tools drawer.
    await page.getByTestId('dev-toggle').click();
    await openCanvasInspector(page);

    await page.getByTestId('canvas-refresh').click();
    const metaBefore = await page.getByTestId('canvas-meta').textContent();
    const countBefore = parseObjectsCount(metaBefore);
    if (countBefore == null) throw new Error(`Cannot parse objects count (before): ${metaBefore}`);

    // Close tools drawer to avoid intercepting clicks in the chat pane.
    await setToolsDrawerOpen(page, false);

    // Send a draw request.
    const prompt = '画一个圆';
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

    // Wait for assistant bubble, then for run_end in trace (dev mode).
    const assistantBubbles = page.locator('.bubble-row.assistant');
    await assistantBubbles.first().waitFor({ state: 'visible' });

    const lastAssistant = assistantBubbles.last();
    // Hard-mode panel should be present (we forced it via query param).
    await lastAssistant.locator('text=思考进度（难题模式）').first().waitFor({ timeout: timeoutMs });
    await lastAssistant.getByTestId('trace-summary').click();
    const traceLog = lastAssistant.getByTestId('trace-log');
    await traceLog.waitFor({ state: 'visible' });
    await traceLog.locator(':has-text("[run_end]")').first().waitFor({ timeout: timeoutMs });

    // Re-open tools drawer and refresh objects.
    await openCanvasInspector(page);

    // Refresh objects and ensure we actually drew something new.
    await page.getByTestId('canvas-refresh').click();
    const metaAfter = await page.getByTestId('canvas-meta').textContent();
    const countAfter = parseObjectsCount(metaAfter);
    if (countAfter == null) throw new Error(`Cannot parse objects count (after): ${metaAfter}`);
    if (countAfter <= countBefore) {
      throw new Error(`Expected objects to increase, before=${countBefore} after=${countAfter}`);
    }

    await page.screenshot({ path: screenshotPath, fullPage: true });
    await browser.close();
    browser = null;

    console.log(`OK: v2 acceptance (web) passed. screenshot=${screenshotPath}`);
  } catch (err) {
    try {
      // Best-effort screenshot on failure.
      if (page) {
        await page.screenshot({ path: screenshotPath, fullPage: true });
      }
    } catch {}
    console.error(`ERR: v2 acceptance (web) failed: ${err instanceof Error ? err.stack || err.message : String(err)}`);
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
