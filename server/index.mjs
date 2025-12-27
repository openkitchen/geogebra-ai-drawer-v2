import dotenv from 'dotenv';
import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';
import os from 'os';
import crypto from 'crypto';
import { spawn } from 'child_process';

import { generateObject, generateText, hasToolCall, stepCountIs, tool, zodSchema } from 'ai';
import { z } from 'zod';
import { createOpenAI } from '@ai-sdk/openai';
import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import { buildTools } from './tools.js';
import { adjustTriangleForObtuseAtA } from './geometry-helpers.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');

// Best practice: load secrets/config from .env files (server-side only).
// Load .env.local first, then .env. Do not override existing environment variables.
dotenv.config({ path: path.join(projectRoot, '.env.local'), override: false });
dotenv.config({ path: path.join(projectRoot, '.env'), override: false });

// AI SDK warnings are useful when debugging provider capabilities, but can be noisy in normal use.
// To disable warnings, set AI_SDK_LOG_WARNINGS=false in the server environment.
if (String(process.env.AI_SDK_LOG_WARNINGS || '').toLowerCase() === 'false') {
  globalThis.AI_SDK_LOG_WARNINGS = false;
}

// Compatibility: allow legacy/lowercase env var names without code changes elsewhere.
// (Still server-side env only; not exposed to the client.)
const looksLikeUnexpandedVar = (v) => typeof v === 'string' && /\$\{[A-Z0-9_]+\}/i.test(v);
if (
  (!process.env.KIMI_API_KEY || looksLikeUnexpandedVar(process.env.KIMI_API_KEY)) &&
  process.env.kimi_api_key
) {
  // dotenv does NOT expand ${...} by default; prefer the concrete legacy key if present.
  process.env.KIMI_API_KEY = process.env.kimi_api_key;
}

function readTextIfExists(filePath) {
  try {
    if (!fs.existsSync(filePath)) return '';
    return fs.readFileSync(filePath, 'utf-8');
  } catch {
    return '';
  }
}

function loadPack(name) {
  return readTextIfExists(path.join(projectRoot, 'prompts', 'packs', `${name}.md`));
}

function loadCommandbook() {
  const filePath = path.join(projectRoot, 'prompts', 'commandbook.json');
  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    const parsed = JSON.parse(raw);
    const entries = Array.isArray(parsed) ? parsed : [];
    const byKey = new Map();
    for (const entry of entries) {
      if (!entry?.name) continue;
      const key = String(entry.name).toLowerCase();
      byKey.set(key, entry);
      if (Array.isArray(entry.aliases)) {
        entry.aliases.forEach((a) => byKey.set(String(a).toLowerCase(), entry));
      }
    }
    const version = crypto.createHash('md5').update(raw).digest('hex');
    return { entries, byKey, version };
  } catch (e) {
    console.warn('[commandbook] load failed:', e?.message || e);
    return { entries: [], byKey: new Map(), version: 'none' };
  }
}

const commandbook = loadCommandbook();

const llmDebugIo =
  String(process.env.LLM_DEBUG_IO || '').toLowerCase() === 'true' ||
  String(process.env.LLM_DEBUG_IO || '').toLowerCase() === '1';
const llmErrorLog =
  String(process.env.LLM_ERROR_LOG || '').toLowerCase() === 'true' ||
  String(process.env.LLM_ERROR_LOG || '').toLowerCase() === '1';
const llmSessionLog =
  String(process.env.LLM_SESSION_LOG || '').toLowerCase() === 'true' ||
  String(process.env.LLM_SESSION_LOG || '').toLowerCase() === '1';

const errorLogPath = path.join(projectRoot, 'logs', 'llm-errors.log');
const sessionLogPath = path.join(projectRoot, 'logs', 'llm-sessions.log');

function logLlmIO(direction, payload) {
  if (!llmDebugIo) return;
  const stamp = new Date().toISOString();
  try {
    const pretty = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
    // Avoid flooding terminal; trim extremely long bodies.
    const MAX = 8000;
    const body = pretty.length > MAX ? `${pretty.slice(0, MAX)}…<trimmed ${pretty.length - MAX} chars>` : pretty;
    console.log(`[LLM-IO][${stamp}][${direction}] ${body}`);
  } catch (e) {
    console.log(`[LLM-IO][${stamp}][${direction}] <unprintable>`, e?.message || e);
  }
}

function logLlmError(payload) {
  if (!llmErrorLog) return;
  const stamp = new Date().toISOString();
  const entry = { stamp, ...payload };
  try {
    fs.mkdirSync(path.dirname(errorLogPath), { recursive: true });
    fs.appendFileSync(errorLogPath, JSON.stringify(entry) + '\n', 'utf-8');
  } catch (e) {
    console.warn('[LLM-ERROR-LOG] failed to append:', e?.message || e);
  }
}

function logLlmSession(payload) {
  if (!llmSessionLog) return;
  const stamp = new Date().toISOString();
  const entry = { stamp, ...payload };
  try {
    fs.mkdirSync(path.dirname(sessionLogPath), { recursive: true });
    fs.appendFileSync(sessionLogPath, JSON.stringify(entry) + '\n', 'utf-8');
  } catch (e) {
    console.warn('[LLM-SESSION-LOG] failed to append:', e?.message || e);
  }
}

function loadSystemPrompt(phase = 'draw', preferences = '') {
  const base = loadPack('base');
  const phasePack = loadPack(phase) || loadPack('draw');
  const constraints = readTextIfExists(path.join(projectRoot, 'prompts', 'geogebra-constraints.md'));
  const scenariosDir = path.join(projectRoot, 'prompts', 'scenarios');
  const scenarioFiles = fs.existsSync(scenariosDir)
    ? fs.readdirSync(scenariosDir).filter((f) => f.endsWith('.md')).sort()
    : [];
  const scenarios = scenarioFiles.map((f) => readTextIfExists(path.join(scenariosDir, f))).join('\n\n');
  const prefs = preferences ? `\n\nPREFERENCES:\n${preferences}` : '';
  return [base, phasePack, constraints, scenarios, prefs].filter(Boolean).join('\n\n');
}

function formatErrorForLog(e) {
  try {
    if (!e) return '';
    if (typeof e === 'string') return e;
    const msg = e.message ? String(e.message) : String(e);
    const status = e.statusCode || e.status || e?.cause?.statusCode || e?.cause?.status;
    return status ? `${msg} (status=${status})` : msg;
  } catch {
    return 'Unknown error';
  }
}

function isTimeoutError(e) {
  try {
    const name = e?.name || e?.cause?.name || e?.reason?.name || e?.cause?.reason?.name;
    if (name === 'TimeoutError') return true;
    const msg = String(e?.message || '');
    if (msg.toLowerCase().includes('timeout')) return true;
    const causeMsg = String(e?.cause?.message || '');
    if (causeMsg.toLowerCase().includes('timeout')) return true;
    return false;
  } catch {
    return false;
  }
}

function isToolChoiceAutoOnlyError(e) {
  try {
    const msg = formatErrorForLog(e).toLowerCase();
    return msg.includes('tool_choice') && msg.includes('auto');
  } catch {
    return false;
  }
}

function safeOrigin(urlLike) {
  const raw = String(urlLike || '').trim();
  if (!raw) return null;
  try {
    const u = new URL(raw);
    return u.origin;
  } catch {
    return raw;
  }
}

function buildPromptBundle(phase = 'draw', preferences = '') {
  const text = loadSystemPrompt(phase, preferences);
  const hash = crypto.createHash('md5').update(text).digest('hex');
  return { text, version: `${phase}:${hash}` };
}

function extractCommandCandidates(messages = []) {
  const last = [...messages].reverse().find((m) => m.role === 'user');
  const toolFeedback = messages.filter((m) => m.role === 'tool').map((m) => m.content).join('\n');
  const haystack = [last?.content || '', toolFeedback].join('\n').toLowerCase();
  const tokens = new Set();
  const nameLike = [...haystack.matchAll(/([a-z][a-z0-9_]*)\s*\(/gi)].map((m) => m[1]);
  nameLike.forEach((n) => tokens.add(n));
  haystack.split(/[^a-z0-9_]+/gi).forEach((t) => t && tokens.add(t));
  return [...tokens];
}

function searchCommandbook(messages = []) {
  const tokens = extractCommandCandidates(messages);
  const hits = [];
  for (const t of tokens) {
    const entry = commandbook.byKey.get(String(t).toLowerCase());
    if (entry && !hits.includes(entry)) hits.push(entry);
  }
  return hits.slice(0, 3);
}

function formatCommandbookHints(entries = []) {
  if (!entries.length) return '';
  const lines = entries.map((e) => {
    const pitfalls = Array.isArray(e.pitfalls) && e.pitfalls.length ? ` Pitfalls: ${e.pitfalls[0]}` : '';
    const exec = e.execPath ? ` [${e.execPath}]` : '';
    return `- ${e.signature}: ${e.example}${pitfalls}${exec ? ` (${exec})` : ''}`;
  });
  return ['COMMANDBOOK HINTS:', ...lines].join('\n');
}

const GGB_SCHEMA = z.object({
  // Allow string or string[]; we'll normalize to string later.
  explanation: z.union([z.string(), z.array(z.string())]),
  // Some OpenAI-compatible gateways (e.g. Kimi) may return a single string instead of string[].
  commands: z.union([z.array(z.string()), z.string()]),
  // Optional UI overlay text pinned to a viewport corner (not a GeoGebra command).
  overlayText: z.object({
    corner: z.enum(['top-left', 'top-right', 'bottom-left', 'bottom-right']),
    text: z.string(),
  }).optional(),
  // Optional hints for geometry validation/adjustment.
  obtuseVertex: z.string().optional(),
  obtuseAnchor: z.string().optional(),
});

let GLOBAL_CANVAS_STATE = '';

const GGB_TOOL_NAME = 'ggb_response';
const FRONTEND_TOOL_NAMES = new Set(['get_canvas_state', 'set_corner_text']);
const TOOL_RESULT_PREFIX = 'TOOL_RESULT:';
const CANVAS_STATE_REQUEST_TOKEN = '<<GET_CANVAS_STATE>>';
const OVERLAY_TOOL_NAME = 'set_corner_text';

const GGB_TOOL = tool({
  description:
    'Return the final GeoGebra JSON response. Must be valid JSON. No markdown. ' +
    'IMPORTANT: `commands` must be an array of GeoGebra command strings (e.g. ["A=(0,0)","c=Circle(A,3)"]). ' +
    'Do NOT put a JSON array literal inside a string.',
  inputSchema: zodSchema(GGB_SCHEMA),
  // Echo back the tool input as the tool output so we can read it from toolResults reliably.
  execute: async (input) => input,
});

function normalizeCommandsField(commands) {
  const out = [];

  const pushParsedOrRaw = (item) => {
    const s = String(item ?? '').trim();
    if (!s) return;

    // Common failure mode: the model returns a JSON-stringified array inside the array, e.g.
    // commands: ["[\"O=(0,0)\", \"c=Circle(O,3)\"]"]
    // GeoGebra expects each array element to be a single command, not a JSON array literal.
    if (s.startsWith('[') && s.endsWith(']')) {
      try {
        const parsed = JSON.parse(s);
        if (Array.isArray(parsed) && parsed.every((x) => typeof x === 'string')) {
          parsed.map((x) => String(x).trim()).filter(Boolean).forEach((x) => out.push(x));
          return;
        }
      } catch {}
    }

    out.push(s);
  };

  if (Array.isArray(commands)) {
    commands.forEach(pushParsedOrRaw);
  } else {
    pushParsedOrRaw(commands);
  }

  return out;
}

function normalizeExplanationField(explanation) {
  if (Array.isArray(explanation)) return explanation.map((s) => String(s)).join('\n');
  return typeof explanation === 'string' ? explanation : '';
}

function stripToolInvocationsFromCommands(commands = []) {
  const removed = [];
  let requestedCanvasState = false;
  const out = [];

  const isToolInvocation = (cmd) => {
    const s = String(cmd || '').trim();
    if (!s) return false;
    // Only match direct invocations (avoid false positives inside Text("...")).
    if (/^\s*get_canvas_state\s*\(\s*\)\s*;?\s*$/i.test(s)) return 'get_canvas_state';
    if (/^\s*get_canvas_state\s*$/i.test(s)) return 'get_canvas_state';
    if (/^\s*ggb_response\s*\(/i.test(s)) return 'ggb_response';
    if (/^\s*set_corner_text\s*\(/i.test(s)) return 'set_corner_text';
    return false;
  };

  for (const c of Array.isArray(commands) ? commands : [commands]) {
    const hit = isToolInvocation(c);
    if (hit) {
      removed.push(String(c).trim());
      if (hit === 'get_canvas_state') requestedCanvasState = true;
      continue;
    }
    const s = String(c ?? '').trim();
    if (s) out.push(s);
  }

  return { commands: out, removed, requestedCanvasState };
}

function sanitizeGgbResponse(response) {
  const explanation = normalizeExplanationField(response?.explanation);
  const normalizedCommands = normalizeCommandsField(response?.commands);
  const stripped = stripToolInvocationsFromCommands(normalizedCommands);
  const overlayText = (() => {
    const validated = GGB_SCHEMA.shape.overlayText.safeParse(response?.overlayText);
    return validated.success ? validated.data : undefined;
  })();

  // If the model mistakenly put `get_canvas_state()` into commands, treat it as a request for canvas context.
  // The client recognizes this token and will re-try with a canvas summary, without showing it to users.
  const needsCanvasToken = stripped.requestedCanvasState && !GLOBAL_CANVAS_STATE;
  const safeExplanation = needsCanvasToken
    ? [explanation, CANVAS_STATE_REQUEST_TOKEN].filter(Boolean).join('\n')
    : explanation;

  return {
    explanation: safeExplanation,
    commands: stripped.commands,
    removedToolCommands: stripped.removed,
    overlayText,
  };
}

function parsePointLiteral(s) {
  if (!s) return null;
  const m = String(s).match(/\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?/);
  if (!m) return null;
  return [parseFloat(m[1]), parseFloat(m[2])];
}

function maybeAdjustObtuseTriangle(response) {
  const { commands, obtuseVertex, obtuseAnchor } = response || {};
  if (!commands || !commands.length) return response;
  const anchorName = obtuseVertex || obtuseAnchor || 'A';
  const pts = {};
  commands.forEach((c) => {
    const match = String(c).match(/^\s*([A-Za-z]+)\s*=\s*\(([^)]+)\)/);
    if (match) {
      const name = match[1];
      const pt = parsePointLiteral(match[2]);
      if (pt) pts[name] = pt;
    }
  });
  const A = pts[anchorName];
  const B = pts['B'];
  const C = pts['C'];
  if (!A || !B || !C) return response;
  const adjusted = adjustTriangleForObtuseAtA(A, B, C);
  if (!adjusted.adjusted) return response;
  const replace = (name, coords) => `${name}=(${coords[0]},${coords[1]})`;
  const newCommands = commands.map((cmd) => {
    if (new RegExp(`^\\s*${anchorName}\\s*=\\s*\\(`, 'i').test(cmd)) return replace(anchorName, adjusted.A);
    if (/^\s*B\s*=\s*\(/i.test(cmd)) return replace('B', adjusted.B);
    if (/^\s*C\s*=\s*\(/i.test(cmd)) return replace('C', adjusted.C);
    return cmd;
  });
  return { ...response, commands: newCommands, _adjustedObtuse: true };
}

function stripTrailingCommas(jsonText) {
  return String(jsonText).replace(/,(\s*[}\]])/g, '$1');
}

function tryParseJsonObjectText(text) {
  const raw = String(text || '').trim();
  if (!raw) return null;

  const candidates = [];
  const fenceRe = /```(?:json)?\s*([\s\S]*?)```/gi;
  let m;
  while ((m = fenceRe.exec(raw)) !== null) {
    if (m[1]) candidates.push(m[1].trim());
  }

  const firstBrace = raw.indexOf('{');
  const lastBrace = raw.lastIndexOf('}');
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    candidates.push(raw.slice(firstBrace, lastBrace + 1).trim());
  }

  // Try direct parse first, then a light cleanup pass (remove trailing commas).
  for (const c of candidates) {
    for (const variant of [c, stripTrailingCommas(c)]) {
      try {
        const obj = JSON.parse(variant);
        return JSON.stringify(obj);
      } catch {}
    }
  }

  return null;
}

const repairJsonObjectText = async ({ text }) => tryParseJsonObjectText(text);

function isModelIdentityQuery(text) {
  const t = String(text || '').trim().toLowerCase();
  if (!t) return false;
  // Chinese
  if (/你是什么模型|你用的什么模型|你在用什么模型|你是哪(个|種|种)模型|你是什么大模型|你是哪个大模型/.test(t)) return true;
  // English-ish
  if (/(what|which)\s+(model|llm)\s+(are|r)\s+you/.test(t)) return true;
  if (/what\s+model\s+is\s+this/.test(t)) return true;
  return false;
}

const EndpointSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  provider: z.enum(['openai', 'google', 'openai-compatible', 'codex-cli']),
  baseURL: z.string().url().optional(), // for google/base URL override or openai-compatible
  apiKey: z.string().min(1),
  // Legacy single model id (still supported)
  modelId: z.string().min(1).optional(),
  // New: multiple model variants keyed by name, e.g. { main: "...", intent: "...", fallback: "..." }
  models: z.record(z.string().min(1)).optional(),
});

function parseEndpointsFromEnv() {
  const jsonRaw = process.env.LLM_ENDPOINTS_JSON;
  // Allow ${ENV_VAR} interpolation inside the JSON string so users can keep keys as separate env vars.
  const json = typeof jsonRaw === 'string'
    ? jsonRaw.replace(/\$\{([A-Z0-9_]+)\}/gi, (_m, name) => process.env[name] ?? '')
    : jsonRaw;
  if (!json) return { endpoints: [], error: 'LLM_ENDPOINTS_JSON is not set' };
  try {
    const parsed = JSON.parse(json);
    if (!Array.isArray(parsed)) {
      return { endpoints: [], error: 'LLM_ENDPOINTS_JSON must be an array' };
    }
    const endpoints = [];
    const mainKey = process.env.LLM_MAIN_MODEL_KEY || 'main';
    for (const item of parsed) {
      const res = EndpointSchema.safeParse(item);
      if (!res.success) {
        return { endpoints: [], error: `Invalid endpoint config: ${res.error.message}` };
      }
      const cfg = res.data;

      // If models map is provided, pick the default "main" model unless overridden.
      // Keep backward compatibility with legacy `modelId` configs.
      if (!cfg.modelId) {
        if (cfg.models && cfg.models[mainKey]) {
          cfg.modelId = cfg.models[mainKey];
        } else if (cfg.models && cfg.models.main) {
          cfg.modelId = cfg.models.main;
        } else {
          return {
            endpoints: [],
            error: `Endpoint "${cfg.id}" is missing modelId and models["${mainKey}"]`,
          };
        }
      }

      endpoints.push(cfg);
    }
    return { endpoints, error: null };
  } catch (e) {
    return { endpoints: [], error: `Failed to parse LLM_ENDPOINTS_JSON: ${e.message}` };
  }
}

function buildModel(endpoint) {
  const { provider, apiKey, baseURL, modelId, id } = endpoint;
  if (provider === 'openai') {
    const openai = createOpenAI({ apiKey, baseURL });
    return openai.chat(modelId);
  }
  if (provider === 'google') {
    const google = createGoogleGenerativeAI({ apiKey, baseURL });
    return google(modelId);
  }
  if (provider === 'codex-cli') {
    // This provider is handled out-of-band via the official Codex CLI process.
    // We return null here and special-case it in request execution.
    return null;
  }
  // openai-compatible
  const compat = createOpenAICompatible({
    name: id,
    apiKey,
    baseURL,
  });
  return compat(modelId);
}

const { endpoints: endpointConfigs, error: endpointError } = parseEndpointsFromEnv();

const endpointConfigsById = new Map(endpointConfigs.map((c) => [c.id, c]));

const endpointModels = endpointConfigs.map((cfg) => ({
  id: cfg.id,
  label: cfg.label,
  provider: cfg.provider,
  modelId: cfg.modelId,
  model: buildModel(cfg),
}));

function parseEndpointIdList(value) {
  const raw = String(value || '').trim();
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

function reorderEndpointsById(enabled, ids) {
  const byId = new Map(enabled.map((e) => [e.id, e]));
  const used = new Set();
  const ordered = [];
  for (const id of ids) {
    const e = byId.get(id);
    if (!e) continue;
    if (used.has(e.id)) continue;
    ordered.push(e);
    used.add(e.id);
  }
  for (const e of enabled) {
    if (used.has(e.id)) continue;
    ordered.push(e);
    used.add(e.id);
  }
  return ordered;
}

function computeOrderedEndpoints(enabled, endpointId, mode) {
  const allowAllFallback = String(process.env.LLM_ALLOW_ALL_FALLBACK || '').toLowerCase() === 'true';
  const explicitFallbackIds = parseEndpointIdList(process.env.LLM_EXPLICIT_FALLBACK_ORDER);
  const autoOrderIds = parseEndpointIdList(process.env.LLM_AUTO_ORDER);
  const autoPreferredId = String(process.env.LLM_AUTO_PREFERRED_ENDPOINT_ID || 'kimi').trim() || 'kimi';

  if (endpointId) {
    const preferred = enabled.find((e) => e.id === endpointId) || null;
    if (!preferred) return [];

    // Default explicit behavior (backward compatible): preferred -> kimi (only).
    // If LLM_EXPLICIT_FALLBACK_ORDER is set, use it as the fallback chain after preferred.
    const fallbackIds = explicitFallbackIds.length > 0
      ? explicitFallbackIds
      : ['kimi'];

    const chain = [preferred];
    for (const id of fallbackIds) {
      if (id === preferred.id) continue;
      const e = enabled.find((x) => x.id === id);
      if (e && !chain.includes(e)) chain.push(e);
    }

    if (allowAllFallback) {
      for (const e of enabled) {
        if (!chain.includes(e)) chain.push(e);
      }
    }

    return chain;
  }

  if (mode === 'auto') {
    // If LLM_AUTO_ORDER is set, it fully controls priority in Auto mode (disabled/unknown ids are ignored).
    if (autoOrderIds.length > 0) return reorderEndpointsById(enabled, autoOrderIds);

    // Backward compatible default: prefer Kimi first unless overridden by LLM_AUTO_PREFERRED_ENDPOINT_ID.
    const preferred =
      enabled.find((e) => e.id === autoPreferredId) ||
      enabled.find((e) => e.id === 'kimi') ||
      enabled[0] ||
      null;
    if (!preferred) return enabled;
    return [preferred, ...enabled.filter((e) => e.id !== preferred.id)];
  }

  return enabled;
}

function formatChatPromptForCodex({ system, messages }) {
  const lines = [];
  lines.push(
    'You are NOT allowed to run any shell commands or access files.',
    'You are a geometry drawing assistant.',
    'Return only a JSON object that matches the required output schema.',
    ''
  );
  if (system) {
    lines.push('SYSTEM_PROMPT:');
    lines.push(String(system));
    lines.push('');
  }
  lines.push('CONVERSATION:');
  for (const m of messages || []) {
    const role = String(m?.role || 'user');
    const content = String(m?.content || '');
    const cmds = Array.isArray(m?.commands) && m.commands.length ? `\nCommands: ${m.commands.join(' | ')}` : '';
    const label = role === 'assistant' ? 'Assistant' : role === 'tool' ? 'Tool' : 'User';
    lines.push(`${label}: ${content}${cmds}`);
  }
  lines.push('');
  lines.push('Remember: respond with JSON only.');
  return lines.join('\n');
}

function hashKey(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  return crypto.createHash('md5').update(raw).digest('hex').slice(0, 16);
}

function codexHomeDirForTab(tabId) {
  const suffix = hashKey(tabId) || hashKey(crypto.randomUUID());
  return path.join(os.tmpdir(), 'ggb-codex-home', suffix);
}

async function runCodexCliTurn({
  reqId,
  baseURL,
  apiKey,
  modelId,
  systemPrompt,
  messages,
  timeoutMs,
  codexTabId,
  preferResume,
}) {
  const schemaPath = path.join(projectRoot, 'server', 'codex-output-schema.json');
  if (!fs.existsSync(schemaPath)) {
    throw new Error(`codex output schema missing at ${schemaPath}`);
  }

  const providerId = `ggb-${String(reqId).slice(0, 8)}`;
  const envKey = `CODEX_GGB_API_KEY_${String(reqId).slice(0, 8).toUpperCase()}`;
  const codexHome = codexHomeDirForTab(codexTabId || reqId);
  await fs.promises.mkdir(codexHome, { recursive: true });
  const outPath = path.join(codexHome, `last-message-${String(reqId).slice(0, 8)}.json`);

  const prompt = formatChatPromptForCodex({ system: systemPrompt, messages });

  const baseArgs = [
    '-s',
    'read-only',
    '-a',
    'untrusted',
    'exec',
    '--skip-git-repo-check',
    '-C',
    codexHome,
    '--output-schema',
    schemaPath,
    '--output-last-message',
    outPath,
    // Disable MCP startup for faster, more deterministic runs.
    '-c',
    'mcp_servers={}',
    '-c',
    'tools.web_search=false',
    '-c',
    'tools.view_image=false',
    '-c',
    'include_apply_patch_tool=false',
    '-c',
    `model_providers.${providerId}={ name = 'GeoGebra Codex CLI', base_url = '${baseURL}', env_key = '${envKey}', wire_api='responses' }`,
    '-c',
    `model_provider="${providerId}"`,
    '-m',
    modelId,
  ];

  const args = preferResume
    ? [...baseArgs, 'resume', '--last', '-']
    : [...baseArgs, '-'];

  const startedAt = Date.now();
  const child = spawn('codex', args, {
    stdio: ['pipe', 'pipe', 'pipe'],
    env: {
      ...process.env,
      [envKey]: apiKey,
      CODEX_HOME: codexHome,
    },
  });

  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (d) => {
    stdout += String(d);
  });
  child.stderr.on('data', (d) => {
    stderr += String(d);
  });

  const killTimer = setTimeout(() => {
    try {
      child.kill('SIGKILL');
    } catch {}
  }, Math.max(1000, Number(timeoutMs) + 5000));

  try {
    child.stdin.write(prompt);
    child.stdin.end();
  } catch {}

  const exitCode = await new Promise((resolve) => {
    child.on('close', (code) => resolve(code));
    child.on('error', () => resolve(1));
  });
  clearTimeout(killTimer);

  const ms = Date.now() - startedAt;
  if (exitCode !== 0) {
    const msg = [stderr.trim(), stdout.trim()].filter(Boolean).join('\n').slice(0, 1200);
    throw new Error(`codex exec failed (code=${exitCode}, ms=${ms}): ${msg || 'unknown error'}`);
  }

  let raw = '';
  try {
    raw = await fs.promises.readFile(outPath, 'utf-8');
  } catch {
    raw = '';
  }

  const jsonText = tryParseJsonObjectText(raw);
  if (!jsonText) {
    throw new Error(`codex output is not valid JSON (ms=${ms})`);
  }
  const parsed = JSON.parse(jsonText);
  return { object: parsed, usage: null, ms };
}

const shouldLogConnectionInfo = String(process.env.LLM_LOG_CONNECTION_INFO || '').toLowerCase() === 'true';
// NOTE: moonshot-v1-8k (or other small/cheap models) should NOT be used for primary chat responses by default.
// If you explicitly want to allow a secondary "fast" fallback within Kimi for chat, set this to true.
const allowKimiChatFallbackModel = String(process.env.KIMI_ALLOW_CHAT_FALLBACK_MODEL || '').toLowerCase() === 'true';
// Prefer tool-calling for openai-compatible gateways to avoid structured output incompatibilities.
const preferToolCallingForCompat = String(process.env.LLM_COMPAT_PREFER_TOOL_CALLING || '').toLowerCase() !== 'false';
if (shouldLogConnectionInfo) {
  console.log('[LLM] endpoints:', endpointConfigs.map((e) => ({
    id: e.id,
    label: e.label,
    provider: e.provider,
    baseURL: safeOrigin(e.baseURL),
    modelId: e.modelId,
    models: e.models ? Object.keys(e.models) : null,
  })));
}

async function generateGgbObjectWithTool({ model, system, messages, maxRetries, timeoutMs, toolChoice, prepareStep }) {
  const tools = buildTools({ canvasState: GLOBAL_CANVAS_STATE });
  const allToolCalls = [];
  const allToolResults = [];
  const { toolResults, toolCalls, usage, response, text } = await generateText({
    model,
    system,
    messages,
    tools: { [GGB_TOOL_NAME]: GGB_TOOL, ...tools },
    toolChoice: toolChoice || 'auto',
    // Allow multi-step tool use (e.g. call get_canvas_state, then call ggb_response).
    stopWhen: [
      // Stop early if the model requested a frontend tool; the browser will execute and send results in a follow-up request.
      ...Array.from(FRONTEND_TOOL_NAMES).map((name) => hasToolCall(name)),
      hasToolCall(GGB_TOOL_NAME),
      stepCountIs(6),
    ],
    prepareStep,
    maxRetries,
    abortSignal: AbortSignal.timeout(timeoutMs),
    onStepFinish: (step) => {
      try {
        const calls = Array.isArray(step?.toolCalls) ? step.toolCalls : [];
        const results = Array.isArray(step?.toolResults) ? step.toolResults : [];
        if (calls.length) allToolCalls.push(...calls);
        if (results.length) allToolResults.push(...results);
      } catch {}
    },
  });

  const mergedToolResults = (allToolResults.length ? allToolResults : toolResults) || [];
  const mergedToolCalls = (allToolCalls.length ? allToolCalls : toolCalls) || [];

  const extractFrontendToolCalls = () => {
    try {
      const calls = Array.isArray(mergedToolCalls) ? mergedToolCalls : [];
      const out = [];
      for (const c of calls) {
        if (!c || c.type !== 'tool-call') continue;
        if (!FRONTEND_TOOL_NAMES.has(c.toolName)) continue;
        out.push({
          type: 'tool-call',
          toolCallId: c.toolCallId,
          toolName: c.toolName,
          input: c.input ?? {},
        });
      }
      return out;
    } catch {
      return [];
    }
  };

  const extractOverlayText = () => {
    try {
      const calls = Array.isArray(mergedToolCalls) ? mergedToolCalls : [];
      for (let i = calls.length - 1; i >= 0; i--) {
        const c = calls[i];
        if (c && c.type === 'tool-call' && c.toolName === OVERLAY_TOOL_NAME && c.input) {
          const validated = GGB_SCHEMA.shape.overlayText.safeParse(c.input);
          if (validated.success) return validated.data;
        }
      }
    } catch {}
    return null;
  };

  const validateOrThrow = (candidate, source) => {
    const validated = GGB_SCHEMA.safeParse(candidate);
    if (validated.success) return validated.data;
    const err = new Error(`Invalid ${GGB_TOOL_NAME} tool payload (${source}).`);
    try {
      err.text = JSON.stringify(
        {
          source,
          validation: validated.error.flatten(),
          toolCalls: mergedToolCalls,
        },
        null,
        2
      );
    } catch {}
    throw err;
  };

  const frontendCalls = extractFrontendToolCalls();
  if (frontendCalls.length > 0) {
    // Do NOT validate/return ggb_response here. The client will run these tools, then send TOOL_RESULT in a follow-up request.
    return { object: null, toolRequest: { toolCalls: frontendCalls }, usage, rawText: null, toolCalls: mergedToolCalls };
  }

  const result = mergedToolResults.find((r) => r && r.type === 'tool-result' && r.toolName === GGB_TOOL_NAME);
  if (result && result.output) {
    const obj = validateOrThrow(result.output, 'tool-result');
    return { object: { ...obj, overlayText: obj.overlayText || extractOverlayText() || undefined }, usage, rawText: null, toolCalls: mergedToolCalls };
  }

  const call = mergedToolCalls.find((c) => c && c.type === 'tool-call' && c.toolName === GGB_TOOL_NAME);
  if (call && call.input) {
    const obj = validateOrThrow(call.input, 'tool-call');
    return { object: { ...obj, overlayText: obj.overlayText || extractOverlayText() || undefined }, usage, rawText: null, toolCalls: mergedToolCalls };
  }

  const raw = response?.body || text || null;
  const rawStr = typeof raw === 'string' ? raw : raw ? JSON.stringify(raw) : '';
  try {
    const jsonText = tryParseJsonObjectText(rawStr);
    if (jsonText) {
      const parsed = JSON.parse(jsonText);
      const validated = GGB_SCHEMA.safeParse(parsed);
      if (validated.success) {
        const obj = validated.data;
        return { object: { ...obj, overlayText: obj.overlayText || extractOverlayText() || undefined }, usage, rawText: rawStr, toolCalls: mergedToolCalls };
      }
    }
  } catch {}
  throw Object.assign(new Error('No tool result generated.'), { text: typeof raw === 'string' ? raw : JSON.stringify(raw) });
}

// In-memory cache for resilience when all LLMs are temporarily down.
// Keyed by the last user prompt (normalized).
const responseCache = new Map();
const MAX_CACHE_ENTRIES = 50;
function normalizeCacheKey(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .slice(0, 500);
}
function cachePut(key, value) {
  try {
    if (responseCache.size >= MAX_CACHE_ENTRIES) {
      const firstKey = responseCache.keys().next().value;
      if (firstKey) responseCache.delete(firstKey);
    }
    responseCache.set(key, value);
  } catch {}
}
function cacheGet(key) {
  try {
    return responseCache.get(key);
  } catch {
    return null;
  }
}

function localFallback(messages) {
  const lastUser = [...(messages || [])].reverse().find((m) => m && m.role === 'user');
  const text = String(lastUser?.content || '').trim();
  const norm = normalizeCacheKey(text);

  // Scenario: Triangle angle sum proof (parallel-line method)
  if (/三角形/.test(text) && /(内角和|角和)/.test(text) && /(180|一百八十)/.test(text)) {
    return {
      explanation:
        '我们用“平行线法”来证明：三角形三个内角加起来等于180°。\n\n' +
        '1) 先画出三角形 ABC。\n' +
        '2) 过顶点 A 画一条直线 l，使它与 BC 平行。\n' +
        '3) 因为 l ∥ BC，所以：\n' +
        '   - ∠ABC 和 在 A 点靠左的那个角是“内错角”，它们相等；\n' +
        '   - ∠ACB 和 在 A 点靠右的那个角也是“内错角”，它们相等。\n' +
        '4) 这三个角正好排成一条直线（平角），所以它们的和就是 180°。\n\n' +
        '因此，∠A + ∠B + ∠C = 180°。',
      commands: [
        // Base triangle + parallel line through A
        'A=(0,0)',
        'B=(4,0)',
        'C=(1,3)',
        'TriangleABC=Polygon(A,B,C)',
        'lBC=Line(B,C)',
        'l=Line(A,lBC)',
        // Use segments for AB/AC to avoid long extension lines (cleaner diagram).
        'sAB=Segment(A,B)',
        'sAC=Segment(A,C)',
        // Angle arcs (visual anchors). Choose point orders to avoid reflex angles (e.g. 360-∠B).
        'angA=Angle(B,A,C)',
        'angB=Angle(C,B,A)',
        'angC=Angle(A,C,B)',
        // Corresponding angles on the parallel line at A
        'angB2=Angle(sAB,l)',
        'angC2=Angle(l,sAC)',
        // Hide numeric degree labels (keep arcs only) to avoid clutter.
        'SetLabelVisible(angA,false)',
        'SetLabelVisible(angB,false)',
        'SetLabelVisible(angC,false)',
        'SetLabelVisible(angB2,false)',
        'SetLabelVisible(angC2,false)',
        'SetLabelVisible(l,false)',
        'SetLabelVisible(lBC,false)',
        // De-emphasize helper lines (keep them visible but light/thin).
        'SetLineThickness(l,1)',
        'SetColor(l,160,160,160)',
        'SetLineStyle(l,1)',
        'SetLineThickness(lBC,1)',
        'SetColor(lBC,160,160,160)',
        'SetLineStyle(lBC,1)',
        // Add simple alpha/beta/gamma labels for kids.
        'Text("α",(0.4,0.4))',
        'Text("β",(3.7,0.3))',
        'Text("γ",(1.1,2.6))',
        // One short label
        'Text("∠A+∠B+∠C = 180°",(0,-1))',
      ],
      usedEndpointId: 'local-fallback',
      _cacheKey: norm,
    };
  }

  return null;
}

function shouldForceCanvasStateTool(text) {
  const t = String(text || '');
  const lower = t.toLowerCase();
  return (
    /你画了什么|我画了什么|画了个什么|现在是什么|这是什么形状|这个是什么|这个图|刚才|上面|下面|这里|那条|那个|此图|现有|基于/.test(t) ||
    /modify|edit|change|move|shift|adjust|based on/.test(lower) ||
    /删除|去掉|移除|清除|清空|重画|重绘|重做|改一下|修改|移动|拖动|加粗|变粗|变细|变浅|颜色|改颜色|隐藏|显示|标注|标签|简化|辅助线|只保留|保留/.test(t) ||
    /\b[A-Z]\b/.test(t) ||
    /点[A-Z]/.test(t) ||
    /[A-Z]点/.test(t)
  );
}

const app = express();
app.use(express.json({ limit: '1mb' }));

// Lightweight request logging (dev-only signal). Keep concise to avoid noise.
app.use((req, _res, next) => {
  if (req.path.startsWith('/api/')) {
    console.log(`[req] ${req.method} ${req.path}`);
  }
  next();
});

app.get('/api/providers', (_req, res) => {
  const list = endpointModels.map((e) => ({
    id: e.id,
    label: e.label,
    provider: e.provider,
    modelId: e.modelId,
    enabled: true,
  }));
  // If no endpoints or parse error, surface disabled list
  if (list.length === 0) {
    return res.json([{ id: 'default', label: 'No endpoints configured', provider: 'openai', enabled: false }]);
  }
  res.json(list);
});

// Intent router: decide whether to include canvas state/objects for better multi-turn UX.
const INTENT_SCHEMA = z.object({
  kind: z.enum(['draw', 'edit', 'explain', 'question', 'other']),
  needsState: z.boolean(),
  needsObjects: z.boolean(),
  reason: z.string(),
});

function pickIntentModel() {
  const preferId = process.env.INTENT_ENDPOINT_ID || 'kimi';
  const baseCfg =
    endpointConfigsById.get(preferId) ||
    endpointConfigsById.get('kimi') ||
    endpointConfigs[0] ||
    null;
  if (!baseCfg) return null;

  const intentKey = process.env.INTENT_MODEL_KEY || 'intent';
  const overrideModelId =
    process.env.INTENT_MODEL_ID ||
    (baseCfg.models && baseCfg.models[intentKey]) ||
    (baseCfg.models && baseCfg.models.intent) ||
    (baseCfg.id === 'kimi' ? 'moonshot-v1-8k' : baseCfg.modelId);

  try {
    const intentCfg = { ...baseCfg, modelId: overrideModelId };
    return {
      id: baseCfg.id,
      label: baseCfg.label,
      provider: baseCfg.provider,
      modelId: overrideModelId,
      model: buildModel(intentCfg),
    };
  } catch {
    // Fall back to main model instance (already built) if rebuild fails.
    return endpointModels.find((e) => e.id === baseCfg.id) || endpointModels[0] || null;
  }
}

function heuristicIntent(text, hasObjects) {
  const t = String(text || '');
  const lower = t.toLowerCase();
  const mentionsExisting =
    /这个|刚才|上面|下面|这里|那条|那个|此图|现有|基于/.test(t) ||
    /modify|edit|change|move|shift|adjust|based on/.test(lower) ||
    /删除|去掉|移除|清除|清空|重画|重绘|重做|改一下|修改|移动|拖动/.test(t);
  const mentionsObjectName = /\b[A-Z]\b/.test(t) || /点[A-Z]/.test(t) || /[A-Z]点/.test(t);
  const needs = Boolean(hasObjects && (mentionsExisting || mentionsObjectName));
  return {
    kind: needs ? 'edit' : 'question',
    needsState: needs,
    needsObjects: needs,
    reason: needs ? '用户在基于现有画板对象提要求，需要状态与对象列表。' : '用户不依赖画板现状也可回答。',
  };
}

app.post('/api/intent', async (req, res) => {
  const BodySchema = z.object({
    text: z.string().min(1),
    hasObjects: z.boolean().optional().default(false),
  });
  const parsed = BodySchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: 'Invalid request body', details: parsed.error.flatten() });
  }
  const { text, hasObjects } = parsed.data;

  // If no models available, fall back to heuristic.
  if (endpointModels.length === 0) {
    return res.json(heuristicIntent(text, hasObjects));
  }

  const p = pickIntentModel();
  try {
    if (!p) return res.json(heuristicIntent(text, hasObjects));
    const system =
      '你是一个意图路由器，用于决定是否要把 GeoGebra 画板状态附加给主模型。' +
      '输入包含用户文本和画板是否已有对象。' +
      '如果用户在讨论/修改/引用现有图（包括提到点名如A/B/C/E、说“这个/刚才/上面”、说移动/调整），needsState/needsObjects 应为 true。' +
      '如果用户是纯概念问答且不依赖现有图，needsState/needsObjects 为 false。' +
      '输出严格为 JSON。';
    const prompt = `UserText: ${text}\nCanvasHasObjects: ${hasObjects}\nReturn JSON.`;
    const timeoutMs = Number(process.env.INTENT_TIMEOUT_MS || 2500);
    const { object } = await generateObject({
      model: p.model,
      schema: INTENT_SCHEMA,
      system,
      prompt,
      abortSignal: AbortSignal.timeout(timeoutMs),
    });
    return res.json(object);
  } catch (e) {
    // If intent model fails, fall back to heuristic.
    return res.json(heuristicIntent(text, hasObjects));
  }
});

// New chat endpoint: accepts full message history (session-only) and returns explanation + commands.
app.post('/api/chat', async (req, res) => {
  const reqId = crypto.randomUUID();
  const BodySchema = z.object({
    messages: z.array(
      z.object({
        role: z.enum(['user', 'assistant', 'tool']).default('user'),
        content: z.string(),
        commands: z.array(z.string()).optional(),
        meta: z.record(z.any()).optional(),
      })
    ),
    endpointId: z.string().optional(),
    mode: z.enum(['auto', 'one']).optional(),
    phase: z.string().optional(),
    preferences: z.string().optional(),
    codexTabId: z.string().optional(),
    canvasState: z.string().optional(), // optional text summary of current canvas/objects for model感知
  });

  const parsed = BodySchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: 'Invalid request body', details: parsed.error.flatten() });
  }

  if (endpointError) {
    return res.status(500).json({ error: `No LLM endpoint is configured: ${endpointError}` });
  }
  if (endpointModels.length === 0) {
    return res.status(500).json({
      error: 'No LLM endpoint is configured. Please set LLM_ENDPOINTS_JSON in .env.local and restart.',
    });
  }

  const { messages, endpointId, mode = 'auto', phase: phaseRaw, preferences = '', codexTabId, canvasState } = parsed.data;
  GLOBAL_CANVAS_STATE = canvasState || '';
  const phase = typeof phaseRaw === 'string' && phaseRaw.trim().length > 0 ? phaseRaw.trim() : 'draw';
  const promptBundle = buildPromptBundle(phase, preferences);
  const cbHits = searchCommandbook(messages);
  const cbHints = formatCommandbookHints(cbHits);
  const promptText = cbHints ? `${promptBundle.text}\n\n${cbHints}` : promptBundle.text;
  const promptVersion = cbHints
    ? `${promptBundle.version}::cb:${commandbook.version}:${crypto.createHash('md5').update(cbHints).digest('hex')}`
    : promptBundle.version;
  const lastUser = [...messages].reverse().find((m) => m.role === 'user');
  const lastUserText = String(lastUser?.content || '');
  const identityQuery = isModelIdentityQuery(lastUser?.content || '');
  const cacheKey = normalizeCacheKey(lastUser?.content || '');
  const versionedCacheKey = cacheKey ? `${promptBundle.version}::${phase}::${cacheKey}` : null;
  const cached = versionedCacheKey ? cacheGet(versionedCacheKey) : null;
  const hasCanvasStateToolResult = (messages || []).some((m) => {
    try {
      return (
        m &&
        m.role === 'tool' &&
        String(m?.meta?.type || '') === 'tool_result' &&
        String(m?.meta?.toolName || '') === 'get_canvas_state'
      );
    } catch {
      return false;
    }
  });
  const wantsCanvasStateViaTool = Boolean(!hasCanvasStateToolResult && !canvasState && shouldForceCanvasStateTool(lastUserText));

  // For core teaching scenarios, prefer deterministic local fallback first to avoid model-specific DSL drift.
  // Only apply when the client did NOT explicitly choose an endpoint (so "GLM main" tests won't be bypassed).
  const earlyFb = !identityQuery && !endpointId && mode === 'auto' ? localFallback(messages) : null;
  if (earlyFb) {
    const { usedEndpointId, _cacheKey, ...rest } = earlyFb;
    if (_cacheKey) cachePut(_cacheKey, rest);
    const debugTrace = [
      { endpointId: usedEndpointId, label: usedEndpointId, provider: 'local', modelId: null, ok: true, ms: 0, error: null, usage: null },
    ];
    return res.json({
      kind: 'final',
      response: rest,
      usedEndpointId,
      usedModelId: null,
      usedProvider: null,
      usedLabel: null,
      debugTrace,
      promptVersion,
    });
  }

  // AI SDK v6 ModelMessage schema uses content parts arrays (e.g. [{type:'text', text:'...'}]).
  // Also: language models do not accept role 'tool' directly; convert tool feedback into a user message.
  const modelMessages = messages.map((m) => {
    const cmds = m.commands && m.commands.length ? `\nCommands: ${m.commands.join(' | ')}` : '';
    const text = `${m.content}${cmds}`;
    const role = m.role === 'assistant' ? 'assistant' : 'user';
    const metaType = String(m?.meta?.type || '');
    const finalText =
      m.role === 'tool' && metaType === 'tool_result'
        ? `${TOOL_RESULT_PREFIX}\n${text}`
        : m.role === 'tool'
          ? `RUNTIME_FEEDBACK:\n${text}`
          : text;
    return { role, content: [{ type: 'text', text: finalText }] };
  });

  // Explicit tool roster hint for models (helps some providers choose to call tools)
  modelMessages.unshift({
    role: 'user',
    content: [
      {
        type: 'text',
        text:
          'Tools available: get_canvas_state (获取当前画布摘要), set_corner_text (设置画布四角固定提示文字)。' +
          '当你需要画布信息时请先调用 get_canvas_state；应用会在下一轮用 TOOL_RESULT 返回结果，然后你再继续作答/作图。' +
          '作图完成后可用 set_corner_text 给小朋友一个简短步骤提示。',
      },
    ],
  });

  // Optional: inline the canvas state as a user message (default OFF; prefer tool-calling).
  const inlineCanvasState = String(process.env.LLM_INLINE_CANVAS_STATE || '').toLowerCase() === 'true';
  if (inlineCanvasState && canvasState && canvasState.trim().length > 0) {
    modelMessages.push({ role: 'user', content: [{ type: 'text', text: `CANVAS_STATE:\n${canvasState}` }] });
  }

  const enabled = endpointModels;
  if (endpointId && !enabled.find((e) => e.id === endpointId)) {
    return res.status(400).json({ error: `Unknown endpointId: ${endpointId}` });
  }
  const ordered = computeOrderedEndpoints(enabled, endpointId, mode);

  let lastErr = null;
  const timeoutMs = Number(process.env.LLM_TIMEOUT_MS || 20000);
  const defaultMaxRetries = Number(process.env.LLM_MAX_RETRIES || 2);
  const compatMaxRetries = Number(process.env.LLM_COMPAT_MAX_RETRIES || 0);
  const debugTrace = [];
  for (const p of ordered) {
    const cfg = endpointConfigsById.get(p.id);
    const attemptBase = {
      endpointId: p.id,
      label: p.label,
      provider: p.provider,
      modelId: p.modelId,
      baseURL: safeOrigin(cfg?.baseURL),
    };

    if (p.provider === 'codex-cli') {
      const attempt = {
        ...attemptBase,
        strategy: 'codex-cli',
        ok: false,
        ms: 0,
        error: null,
        rawTextPreview: null,
        usage: null,
      };
      const startedAt = Date.now();
      try {
        const baseURL = cfg?.baseURL;
        const apiKey = cfg?.apiKey;
        const modelId = attempt.modelId;
        if (!baseURL || !apiKey || !modelId) {
          throw new Error('codex-cli endpoint missing baseURL/apiKey/modelId');
        }
        if (shouldLogConnectionInfo) {
          console.log(
            `[LLM] chat attempt start reqId=${reqId} phase=${phase} selected=${endpointId || 'auto'} endpoint=${attempt.endpointId} provider=${attempt.provider} baseURL=${attempt.baseURL || ''} model=${attempt.modelId} timeoutMs=${timeoutMs} strategy=${attempt.strategy}`
          );
        }
        let codexResult = null;
        try {
          codexResult = await runCodexCliTurn({
            reqId,
            baseURL,
            apiKey,
            modelId,
            systemPrompt: promptText,
            messages,
            timeoutMs,
            codexTabId,
            preferResume: true,
          });
        } catch (e) {
          // If there is no existing session for this tab yet, resume will fail; start a new session.
          codexResult = await runCodexCliTurn({
            reqId,
            baseURL,
            apiKey,
            modelId,
            systemPrompt: promptText,
            messages,
            timeoutMs,
            codexTabId,
            preferResume: false,
          });
        }
        const { object, usage, ms } = codexResult;
        const providerToolCalls = codexResult?.toolCalls || null;
        attempt.ok = true;
        attempt.ms = ms;
        attempt.usage = usage;
        debugTrace.push(attempt);
        if (shouldLogConnectionInfo) {
          console.log(
            `[LLM] chat attempt ok reqId=${reqId} endpoint=${attempt.endpointId} model=${attempt.modelId} ms=${attempt.ms} strategy=${attempt.strategy}`
          );
        }

        const sanitized = sanitizeGgbResponse(object);
        const normalized = {
          explanation: sanitized.explanation,
          commands: sanitized.commands,
          overlayText: sanitized.overlayText,
          obtuseVertex: object.obtuseVertex,
          obtuseAnchor: object.obtuseAnchor,
        };
        const maybeAdjusted = maybeAdjustObtuseTriangle(normalized);

        if (identityQuery) {
          const selected = endpointId ? endpointModels.find((e) => e.id === endpointId) : null;
          const allowAllFallback = String(process.env.LLM_ALLOW_ALL_FALLBACK || '').toLowerCase() === 'true';
          const selectedLine = selected
            ? `你选择的模型：${selected.label}（endpointId=${selected.id}, modelId=${selected.modelId}）。`
            : `你选择的模型：Auto（自动选择/降级）。`;
          const usedLine = `本次回答实际使用：${p.label}（endpointId=${p.id}, provider=${p.provider}, modelId=${modelId}）。`;
          const fallbackLine =
            selected && selected.id !== 'kimi' && endpointModels.some((e) => e.id === 'kimi')
              ? (allowAllFallback
                ? `降级顺序：优先回落到 Kimi，且已开启全量 fallback（LLM_ALLOW_ALL_FALLBACK=true）。`
                : `若主模型失败，将优先回落到 Kimi。`)
              : '';
          normalized.explanation = [normalized.explanation, '', selectedLine, usedLine, fallbackLine].filter(Boolean).join('\n');
          normalized.commands = [];
        }

        if (versionedCacheKey) cachePut(versionedCacheKey, maybeAdjusted);
        return res.json({
          kind: 'final',
          response: maybeAdjusted,
          usedEndpointId: p.id,
          usedModelId: modelId,
          usedProvider: p.provider,
          usedLabel: p.label,
          debugTrace,
          promptVersion,
          toolCalls: providerToolCalls,
        });
      } catch (e) {
        const errForLog = isTimeoutError(e) ? new Error(`llm timeout after ${timeoutMs}ms`) : e;
        lastErr = errForLog;
        attempt.ok = false;
        attempt.ms = Date.now() - startedAt;
        attempt.error = formatErrorForLog(errForLog);
        debugTrace.push(attempt);
        logLlmError({
          phase,
          endpointId: p.id,
          provider: p.provider,
          modelId: modelId,
          promptVersion,
          strategy,
          error: attempt.error,
          messages: modelMessages,
          system: promptText,
          reqId,
        });
        if (shouldLogConnectionInfo) {
          console.log(
            `[LLM] chat attempt fail reqId=${reqId} endpoint=${attempt.endpointId} model=${attempt.modelId} ms=${attempt.ms} error=${attempt.error} strategy=${attempt.strategy}`
          );
        }
        console.warn(`[API] Endpoint ${p.id} failed, trying next... ${formatErrorForLog(errForLog)}`);
      }
      continue;
    }

    // If you explicitly enable it, allow a faster fallback model within Kimi for chat.
    // Default: disabled (small models are reserved for intent/cheap tasks).
    let modelToUse = p.model;
    let resolvedModelId = p.modelId;
    if (allowKimiChatFallbackModel && p.id === 'kimi' && endpointId && endpointId !== 'kimi' && endpointConfigsById.has('kimi')) {
      const cfg = endpointConfigsById.get('kimi');
      const fallbackKey = process.env.KIMI_FALLBACK_MODEL_KEY || 'fallback';
      const fallbackModelId =
        process.env.KIMI_FALLBACK_MODEL_ID ||
        (cfg.models && cfg.models[fallbackKey]) ||
        (cfg.models && cfg.models.fallback) ||
        'moonshot-v1-8k';
      try {
        modelToUse = buildModel({ ...cfg, modelId: fallbackModelId });
        resolvedModelId = fallbackModelId;
      } catch {
        // If rebuild fails, keep using the prebuilt model instance.
      }
    }

    const strategies = [];
    if (p.provider === 'openai-compatible' && preferToolCallingForCompat) {
      strategies.push('tool');
    }
    strategies.push('object');

    let endpointFailed = null;
    for (const strategy of strategies) {
      const attempt = {
        ...attemptBase,
        modelId: resolvedModelId,
        strategy,
        ok: false,
        ms: 0,
        error: null,
        rawTextPreview: null,
        usage: null,
      };
      const startedAt = Date.now();
      try {
        if (shouldLogConnectionInfo) {
          console.log(
            `[LLM] chat attempt start reqId=${reqId} phase=${phase} selected=${endpointId || 'auto'} endpoint=${attempt.endpointId} provider=${attempt.provider} baseURL=${attempt.baseURL || ''} model=${attempt.modelId} timeoutMs=${timeoutMs} strategy=${attempt.strategy}`
          );
        }

        let object = null;
        let usage = null;
        let providerToolCalls = null;
        if (strategy === 'tool') {
          const toolSystem =
            `${promptText}\n\n` +
            `IMPORTANT: You MUST call the tool "${GGB_TOOL_NAME}" to return the final JSON object.`;

          try {
            logLlmIO('request', {
              endpoint: p.id,
              provider: p.provider,
              modelId: resolvedModelId,
              promptVersion,
              strategy,
              system: toolSystem,
              messages: modelMessages,
            });
            const toolResult = await generateGgbObjectWithTool({
              model: modelToUse,
              system: toolSystem,
              messages: modelMessages,
              maxRetries: compatMaxRetries,
              timeoutMs,
              // Stability first: when we don't expect frontend tools, force the final tool.
              // When we expect frontend tools, allow the model to call them (toolChoice=auto) and stop on tool_request.
              toolChoice: wantsCanvasStateViaTool ? 'auto' : { type: 'tool', toolName: GGB_TOOL_NAME },
              prepareStep: wantsCanvasStateViaTool
                ? ({ steps }) => {
                  if (!steps || steps.length === 0) {
                    return {
                      toolChoice: { type: 'tool', toolName: 'get_canvas_state' },
                      activeTools: ['get_canvas_state'],
                    };
                  }
                  return {
                    toolChoice: 'auto',
                    activeTools: [GGB_TOOL_NAME, 'get_canvas_state', 'set_corner_text'],
                  };
                }
                : undefined,
            });
            if (toolResult.toolRequest) {
              attempt.ok = true;
              attempt.ms = Date.now() - startedAt;
              attempt.error = null;
              attempt.rawTextPreview = null;
              attempt.usage = toolResult.usage || null;
              debugTrace.push(attempt);
              return res.json({
                kind: 'tool_request',
                response: null,
                toolRequest: toolResult.toolRequest,
                usedEndpointId: p.id,
                usedModelId: resolvedModelId,
                usedProvider: p.provider,
                usedLabel: p.label,
                debugTrace,
                promptVersion,
                toolCalls: toolResult?.toolCalls || null,
              });
            }
            object = toolResult.object;
            usage = toolResult.usage || null;
            providerToolCalls = toolResult?.toolCalls || null;
            logLlmIO('response', {
              endpoint: p.id,
              provider: p.provider,
              modelId: resolvedModelId,
              promptVersion,
              strategy,
              rawResponse: toolResult.rawText || toolResult.object || null,
              toolCalls: providerToolCalls,
            });
          } catch (e) {
            // Some providers (e.g. Zhipu/GLM) only support tool_choice="auto". Retry once.
            if (isToolChoiceAutoOnlyError(e)) {
              logLlmIO('request', {
                endpoint: p.id,
                provider: p.provider,
                modelId: resolvedModelId,
                promptVersion,
                strategy: 'tool-auto',
                system: toolSystem,
                messages: modelMessages,
              });
              const result = await generateGgbObjectWithTool({
                model: modelToUse,
                system: toolSystem,
                messages: modelMessages,
                maxRetries: compatMaxRetries,
                timeoutMs,
                toolChoice: 'auto',
                prepareStep: wantsCanvasStateViaTool
                  ? ({ steps }) => {
                    if (!steps || steps.length === 0) {
                      return {
                        toolChoice: { type: 'tool', toolName: 'get_canvas_state' },
                        activeTools: ['get_canvas_state'],
                      };
                    }
                    return {
                      toolChoice: 'auto',
                      activeTools: [GGB_TOOL_NAME, 'get_canvas_state', 'set_corner_text'],
                    };
                  }
                  : undefined,
              });
              if (result.toolRequest) {
                attempt.ok = true;
                attempt.ms = Date.now() - startedAt;
                attempt.error = null;
                attempt.rawTextPreview = null;
                attempt.usage = result.usage || null;
                debugTrace.push(attempt);
                return res.json({
                  kind: 'tool_request',
                  response: null,
                  toolRequest: result.toolRequest,
                  usedEndpointId: p.id,
                  usedModelId: resolvedModelId,
                  usedProvider: p.provider,
                  usedLabel: p.label,
                  debugTrace,
                  promptVersion,
                  toolCalls: result?.toolCalls || null,
                });
              }
              object = result.object;
              usage = result.usage || null;
              providerToolCalls = result?.toolCalls || null;
              logLlmIO('response', {
                endpoint: p.id,
                provider: p.provider,
                modelId: resolvedModelId,
                promptVersion,
                strategy: 'tool-auto',
                rawResponse: result.rawText || result.object || null,
                toolCalls: providerToolCalls,
              });
            } else {
              throw e;
            }
          }
        } else {
          logLlmIO('request', {
            endpoint: p.id,
            provider: p.provider,
            modelId: resolvedModelId,
            promptVersion,
            strategy,
            system: promptText,
            messages: modelMessages,
          });
          const resp = await generateObject({
            model: modelToUse,
            schema: GGB_SCHEMA,
            maxRetries: p.provider === 'openai-compatible' ? compatMaxRetries : defaultMaxRetries,
            experimental_repairText: repairJsonObjectText,
            system: promptText,
            messages: modelMessages,
            abortSignal: AbortSignal.timeout(timeoutMs),
            tools: buildTools({ canvasState }),
            toolChoice: 'auto',
          });
          object = resp.object;
          usage = resp.usage || null;
          providerToolCalls = resp?.rawResponse?.tool_calls || resp?.rawResponse?.function_call || null;
          logLlmIO('response', {
            endpoint: p.id,
            provider: p.provider,
            modelId: resolvedModelId,
            promptVersion,
            strategy,
            rawResponse: resp.rawResponse || resp.object || null,
            toolCalls: providerToolCalls,
          });
        }

        const sanitized = sanitizeGgbResponse(object);
        const normalized = {
          explanation: sanitized.explanation,
          commands: sanitized.commands,
          overlayText: sanitized.overlayText,
          obtuseVertex: object.obtuseVertex,
          obtuseAnchor: object.obtuseAnchor,
        };
        const maybeAdjusted = maybeAdjustObtuseTriangle(normalized);

        if (identityQuery) {
          const selected = endpointId ? endpointModels.find((e) => e.id === endpointId) : null;
          const allowAllFallback = String(process.env.LLM_ALLOW_ALL_FALLBACK || '').toLowerCase() === 'true';
          const selectedLine = selected
            ? `你选择的模型：${selected.label}（endpointId=${selected.id}, modelId=${selected.modelId}）。`
            : `你选择的模型：Auto（自动选择/降级）。`;
          const usedLine = `本次回答实际使用：${p.label}（endpointId=${p.id}, provider=${p.provider}, modelId=${resolvedModelId}）。`;
          const fallbackLine =
            selected && selected.id !== 'kimi' && endpointModels.some((e) => e.id === 'kimi')
              ? (allowAllFallback
                ? `降级顺序：优先回落到 Kimi，且已开启全量 fallback（LLM_ALLOW_ALL_FALLBACK=true）。`
                : `若主模型失败，将优先回落到 Kimi。`)
              : '';
          normalized.explanation = [normalized.explanation, '', selectedLine, usedLine, fallbackLine].filter(Boolean).join('\n');
          normalized.commands = [];
        }

        attempt.ok = true;
        attempt.ms = Date.now() - startedAt;
        attempt.usage = usage || null;
        debugTrace.push(attempt);
        if (shouldLogConnectionInfo) {
          console.log(
            `[LLM] chat attempt ok reqId=${reqId} endpoint=${attempt.endpointId} model=${attempt.modelId} ms=${attempt.ms} strategy=${attempt.strategy}`
          );
        }

        if (versionedCacheKey) cachePut(versionedCacheKey, maybeAdjusted);
        logLlmSession({
          phase,
          endpointId: p.id,
          provider: p.provider,
          modelId: resolvedModelId,
          promptVersion,
          strategy,
          reqId,
          messages: modelMessages,
          system: promptText,
          response: maybeAdjusted,
          usage,
          toolCalls: providerToolCalls,
        });
        return res.json({
          kind: 'final',
          response: maybeAdjusted,
          usedEndpointId: p.id,
          usedModelId: resolvedModelId,
          usedProvider: p.provider,
          usedLabel: p.label,
          debugTrace,
          promptVersion,
          toolCalls: providerToolCalls,
        });
      } catch (e) {
        // If the provider returned non-JSON (or invalid JSON), keep a short preview for debugging.
        // AI SDK's NoObjectGeneratedError typically includes `.text`.
        try {
          const rawText = e?.text || e?.cause?.text || e?.response?.body || e?.cause?.response?.body || null;
          if (rawText) attempt.rawTextPreview = String(rawText).slice(0, 800);
        } catch {}

        const errForLog = isTimeoutError(e) ? new Error(`llm timeout after ${timeoutMs}ms`) : e;
        endpointFailed = errForLog;
        attempt.ok = false;
        attempt.ms = Date.now() - startedAt;
        attempt.error = formatErrorForLog(errForLog);
        debugTrace.push(attempt);
        logLlmError({
          phase,
          endpointId: p.id,
          provider: p.provider,
          modelId: resolvedModelId,
          promptVersion,
          strategy,
          error: attempt.error,
          messages: modelMessages,
          system: promptText,
          reqId,
        });
        if (shouldLogConnectionInfo) {
          console.log(
            `[LLM] chat attempt fail reqId=${reqId} endpoint=${attempt.endpointId} model=${attempt.modelId} ms=${attempt.ms} error=${attempt.error} strategy=${attempt.strategy}`
          );
        }
      }
    }

    lastErr = endpointFailed || lastErr;
    console.warn(`[API] Endpoint ${p.id} failed, trying next... ${formatErrorForLog(endpointFailed)}`);
  }

  // If all LLMs fail, try cache first, then a small local fallback for core teaching scenarios.
	  if (cached) {
	    debugTrace.push({ endpointId: 'cache', label: 'cache', provider: 'local', modelId: null, ok: true, ms: 0, error: null, usage: null });
	    return res.json({
	      kind: 'final',
	      response: cached,
	      usedEndpointId: 'cache',
	      usedModelId: null,
	      usedProvider: null,
	      usedLabel: null,
	      debugTrace,
	      promptVersion,
	    });
	  }
  const fb = localFallback(messages);
	  if (fb) {
    const { usedEndpointId, _cacheKey, ...rest } = fb;
    if (_cacheKey) cachePut(_cacheKey, rest);
	    debugTrace.push({ endpointId: usedEndpointId, label: usedEndpointId, provider: 'local', modelId: null, ok: true, ms: 0, error: null, usage: null });
	    return res.json({
	      kind: 'final',
	      response: rest,
	      usedEndpointId,
	      usedModelId: null,
	      usedProvider: null,
	      usedLabel: null,
	      debugTrace,
	      promptVersion,
	    });
	  }

  return res.status(502).json({
    error: 'All LLM endpoints failed.',
    details: String(lastErr?.message || lastErr || ''),
    debugTrace,
    promptVersion,
  });
});

app.post('/api/ggb', async (req, res) => {
  const BodySchema = z.object({
    prompt: z.string().min(1),
    errorContext: z.string().optional(),
    endpointId: z.string().optional(),
    mode: z.enum(['auto', 'one']).optional(),
  });

  const parsed = BodySchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: 'Invalid request body', details: parsed.error.flatten() });
  }

  if (endpointError) {
    return res.status(500).json({ error: `No LLM endpoint is configured: ${endpointError}` });
  }

  if (endpointModels.length === 0) {
    return res.status(500).json({
      error: 'No LLM endpoint is configured. Please set LLM_ENDPOINTS_JSON in .env.local and restart.',
    });
  }

  const { prompt, errorContext, endpointId, mode = 'auto' } = parsed.data;
  const userPrompt = errorContext
    ? `The following commands failed in GeoGebra:\n${errorContext}\n\nPlease fix them and provide the full corrected command sequence for the original request: "${prompt}"`
    : prompt;

  const enabled = endpointModels;
  if (endpointId && !enabled.find((e) => e.id === endpointId)) {
    return res.status(400).json({ error: `Unknown endpointId: ${endpointId}` });
  }
  const ordered = computeOrderedEndpoints(enabled, endpointId, mode);

  let lastError = null;
  const repairPrompt = buildPromptBundle('repair');
  const timeoutMs = Number(process.env.LLM_TIMEOUT_MS || 20000);
  const defaultMaxRetries = Number(process.env.LLM_MAX_RETRIES || 2);
  const compatMaxRetries = Number(process.env.LLM_COMPAT_MAX_RETRIES || 0);
  for (const p of ordered) {
    try {
      const { object } = await generateObject({
        model: p.model,
        schema: GGB_SCHEMA,
        maxRetries: p.provider === 'openai-compatible' ? compatMaxRetries : defaultMaxRetries,
        experimental_repairText: repairJsonObjectText,
        system: repairPrompt.text,
        prompt: userPrompt,
        abortSignal: AbortSignal.timeout(timeoutMs),
      });

      const normalized = {
        explanation: object.explanation,
        commands: normalizeCommandsField(object.commands),
        overlayText: object.overlayText || undefined,
      };

      return res.json({ response: normalized, usedEndpointId: p.id });
    } catch (e) {
      lastError = e;
      console.warn(`[API] Endpoint ${p.id} failed, trying next... ${formatErrorForLog(e)}`);
    }
  }

  return res.status(502).json({
    error: 'All LLM endpoints failed.',
    details: String(lastError?.message || lastError || ''),
  });
});

// Production: serve built client (dist/) from the same server.
if (process.env.NODE_ENV === 'production') {
  const distDir = path.resolve(__dirname, '..', 'dist');
  app.use(express.static(distDir));
  app.get('*', (_req, res) => {
    res.sendFile(path.join(distDir, 'index.html'));
  });
}

const port = Number(process.env.PORT || process.env.API_PROXY_PORT || (process.env.NODE_ENV === 'production' ? 3000 : 3002));
app.listen(port, () => {
  console.log(`[server] listening on http://localhost:${port}`);
});
