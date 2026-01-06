#!/usr/bin/env node
/**
 * v2 refinement acceptance (web): Playwright-driven multi-turn smoke test.
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
  console.log(`Waiting for ${url} (timeout: ${timeoutMs}ms)...`);
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const res = await fetch(url, { method: 'GET' });
      if (res.ok) {
        console.log(`Success: ${url} is OK`);
        return;
      }
      lastErr = new Error(`HTTP ${res.status} ${res.statusText}`);
    } catch (e) {
      lastErr = e;
    }
    process.stdout.write('.');
    await sleep(1000);
  }
  console.log('\n');
  throw new Error(`Timed out waiting for ${url}: ${lastErr?.message || String(lastErr)}`);
}

async function launchChromium({ headless }) {
  try {
    return await chromium.launch({ headless });
  } catch (err) {
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
  const webBaseUrl = `http://localhost:${envInt('WEB_PORT', 3000)}`;
  const apiBaseUrl = `http://localhost:${envInt('API_PORT', 3002)}`;
  const headless = envBool('HEADLESS', true);
  const timeoutMs = envInt('PW_TIMEOUT_MS', 180_000); // 3 minutes for multi-turn

  const evidenceDir = path.join(rootDir, 'logs', 'acceptance');
  fs.mkdirSync(evidenceDir, { recursive: true });
  const screenshotPath = path.join(evidenceDir, `web-refinement-${Date.now()}.png`);

  let browser = null;
  try {
    await waitForHttpOk(`${apiBaseUrl}/healthz`, { timeoutMs });
    await waitForHttpOk(`${webBaseUrl}/`, { timeoutMs });

    browser = await launchChromium({ headless });
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(timeoutMs);

    await page.goto(`${webBaseUrl}/`);

    // Turn 1: Draw
    console.log('--- Turn 1: Drawing ---');
    await page.getByTestId('chat-input').fill('画一个三角形 ABC');
    await page.getByTestId('send-button').click();
    await page.locator('.bubble-row.assistant').first().waitFor({ state: 'visible' });
    await page.waitForFunction(() => {
        const bubbles = document.querySelectorAll('.bubble-row.assistant');
        const last = bubbles[bubbles.length - 1];
        return last && !last.querySelector('.thinking-dots');
    }, null, { timeout: timeoutMs });

    // Turn 2: Refine
    console.log('--- Turn 2: Refining ---');
    await page.getByTestId('chat-input').fill('把 A 点往上移一点');
    await page.getByTestId('send-button').click();
    
    // Wait for Turn 2 completion
    await page.waitForFunction(() => {
        const bubbles = document.querySelectorAll('.bubble-row.assistant');
        return bubbles.length >= 2 && !bubbles[bubbles.length - 1].querySelector('.thinking-dots');
    }, null, { timeout: timeoutMs });

    const lastText = await page.locator('.bubble-row.assistant .content').last().textContent();
    console.log('Last response:', lastText);

    if (!lastText.includes('A')) {
        console.warn('Warning: Response might not mention point A');
    }

    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`OK: Refinement acceptance passed. Evidence: ${screenshotPath}`);

  } catch (err) {
    console.error(`ERR: Refinement acceptance failed: ${err.message}`);
    process.exitCode = 2;
  } finally {
    if (browser) await browser.close();
  }
}

await run();
