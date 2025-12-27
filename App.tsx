import React, { useState, useCallback, useRef, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import GGBView from './components/GGBView';
import { Message, GeoGebraApplet, GGBResponse, EndpointStatus, ChatMessage, Corner } from './types';
import DebugPanel from './components/DebugPanel';

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasApiKey, setHasApiKey] = useState(true);
  const [endpoints, setEndpoints] = useState<EndpointStatus[]>([]);
  // UI 默认选 Auto；服务端 Auto 内部优先 Kimi。
  const [endpointId, setEndpointId] = useState<string>('auto');
  const [overlayTexts, setOverlayTexts] = useState<Partial<Record<Corner, string>>>({});
  const [showDebug, setShowDebug] = useState(false);
  const [selfTestRunning, setSelfTestRunning] = useState(false);
const [promptRunning, setPromptRunning] = useState(false);
const appletRef = useRef<GeoGebraApplet | null>(null);
  const tabIdRef = useRef<string>('');
  const CANVAS_STATE_REQUEST_TOKEN = '<<GET_CANVAS_STATE>>';

  const stripInternalTokensForDisplay = (text: string) => {
    return String(text || '').split(CANVAS_STATE_REQUEST_TOKEN).join('').trim();
  };

  useEffect(() => {
    try {
      const key = 'ggbTabId';
      const existing = sessionStorage.getItem(key);
      if (existing && existing.trim()) {
        tabIdRef.current = existing.trim();
        return;
      }
      const created = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      sessionStorage.setItem(key, created);
      tabIdRef.current = created;
    } catch {
      tabIdRef.current = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }
  }, []);

  const normalizeObjectNames = useCallback((names: any): string[] => {
    if (!names) return [];
    if (Array.isArray(names)) return names.filter((x) => typeof x === 'string');
    if (typeof names === 'string') {
      return names
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
    }
    return [];
  }, []);

  const getCurrentObjects = useCallback((): string[] => {
    try {
      return normalizeObjectNames(appletRef.current?.getAllObjectNames?.());
    } catch {
      return [];
    }
  }, [normalizeObjectNames]);

const buildStateSummary = useCallback((): string => {
    const api = appletRef.current as any;
    if (!api) return '';
    const names = getCurrentObjects().slice(0, 40);

    const fmt = (n: any) => {
      const v = Number(n);
      if (!Number.isFinite(v)) return '?';
      return v.toFixed(3);
    };

    const entries: string[] = [];
    for (const name of names) {
      let type = '';
      try {
        const t = api.getObjectType?.(name);
        type = typeof t === 'string' ? t.toLowerCase() : '';
      } catch {
        // ignore
      }

      if (type === 'point') {
        try {
          const x = api.getXcoord?.(name);
          const y = api.getYcoord?.(name);
          entries.push(`${name}(point x=${fmt(x)}, y=${fmt(y)})`);
          continue;
        } catch {
          // ignore
        }
      }

      if (type === 'angle') {
        try {
          const deg = api.getValue?.(name);
          entries.push(`${name}(angle deg=${fmt(deg)})`);
          continue;
        } catch {
          // ignore
        }
      }

      if (type === 'line' || type === 'segment' || type === 'ray') {
        try {
          const def = api.getDefinitionString?.(name) || api.getValueString?.(name) || '';
          const trimmed = String(def || '').trim();
          entries.push(`${name}(${type}${trimmed ? ` ${trimmed}` : ''})`);
          continue;
        } catch {
          // ignore
        }
      }

      // Fallback: only include the name and detected type if any
      if (type) {
        entries.push(`${name}(${type})`);
      } else {
        entries.push(name);
      }
    }

  return entries.join('; ');
}, [getCurrentObjects]);

const buildCanvasStateForLLM = useCallback((): string => {
  const summary = buildStateSummary();
  if (!summary) return '';
  return `CANVAS_STATE: ${summary}`;
}, [buildStateSummary]);

  const rollbackCreatedObjects = useCallback(
    (before: string[]) => {
      const api = appletRef.current as any;
      if (!api) return { rolledBack: [] as string[] };
      const after = getCurrentObjects();
      const beforeSet = new Set(before);
      const created = after.filter((n) => !beforeSet.has(n));
      const rolledBack: string[] = [];
      for (const name of created) {
        try {
          api.deleteObject?.(name);
          rolledBack.push(name);
        } catch {
          // ignore
        }
      }
      return { rolledBack };
    },
    [getCurrentObjects]
  );

  const pushDebug = useCallback((entry: any) => {
    try {
      const w = window as any;
      w.__ggbDebugLog = w.__ggbDebugLog || [];
      const payload = { ts: Date.now(), ...entry };
      w.__ggbDebugLog.push(payload);
      if (w.__ggbDebugLog.length > 200) w.__ggbDebugLog.shift();
      // Also emit high-signal events to console so automated testing can read them reliably.
      const t = String(entry?.type || '');
      if (t.startsWith('prompt_run') || t.startsWith('selftest_') || t.startsWith('api_') || t.includes('error')) {
        // eslint-disable-next-line no-console
        console.log('[ggb-debug]', JSON.stringify(payload));
      }
    } catch {}
  }, []);

  const readErrorPayload = useCallback(async (res: Response): Promise<{ text: string; json: any | null }> => {
    try {
      const contentType = String(res.headers.get('content-type') || '');
      if (contentType.includes('application/json')) {
        const json = await res.clone().json().catch(() => null);
        if (json) return { json, text: JSON.stringify(json) };
      }
      const text = await res.clone().text().catch(() => '');
      if (!text) return { text: '', json: null };
      try {
        return { text, json: JSON.parse(text) };
      } catch {
        return { text, json: null };
      }
    } catch {
      return { text: '', json: null };
    }
  }, []);

  useEffect(() => {
    // Backend decides which providers are enabled (API keys are server-side only).
    const loadProviders = async () => {
      try {
        const res = await fetch('/api/providers');
        if (!res.ok) throw new Error('Failed to load providers');
        const data = (await res.json()) as EndpointStatus[];
        setEndpoints(data);
        setHasApiKey(data.some((p) => p.enabled));

        // If preferred endpoint isn't available, fall back to auto.
        const preferred = data.find((p) => p.id === 'kimi' && p.enabled);
        if (!preferred && endpointId === 'kimi') {
          setEndpointId('auto');
        }
      } catch (e) {
        // If backend isn't running yet, show "not activated".
        setEndpoints([
          { id: 'gemini', label: 'Gemini', provider: 'google', enabled: false },
          { id: 'openai', label: 'GPT', provider: 'openai', enabled: false },
          { id: 'zhipu', label: 'GLM', provider: 'openai-compatible', enabled: false },
        ]);
        setHasApiKey(false);
      }
    };
    loadProviders();
  }, [endpointId]);

  const handleOpenKey = async () => {
    // Kept for UI compatibility: in B architecture, keys live on the server.
    alert('请在服务端配置 .env.local：LLM_ENDPOINTS_JSON（含 baseURL / apiKey / modelId），然后重启服务。');
  };

  const adjustView = useCallback((applet: any) => {
    try {
      const canvas = document.getElementById('ggb-canvas-root');
      if (!canvas) return;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const ratio = width / height;
      const xRange = 12;
      const yRange = xRange / ratio;
      applet.setAxesRatio(1, 1);
      applet.setCoordSystem(-xRange, xRange, -yRange, yRange);
    } catch (e) {}
  }, []);

  const onGGBReady = useCallback((applet: any) => {
    appletRef.current = applet;
    const setup = () => {
      try {
        // Disable GeoGebra modal error dialogs; we capture errors and feed them back to the LLM instead.
        applet.setErrorDialogsActive?.(false);
        applet.setPerspective("G"); 
        // Default to geometry-friendly canvas (no axes/grid). For algebra/graphing tasks we will enable axes/grid per request.
        applet.setGridVisible(false);
        applet.setAxesVisible(false, false);
        adjustView(applet);
      } catch (e) {
        setTimeout(setup, 500);
      }
    };
    setup();
  }, [adjustView]);

  // 核心：指令执行与验证逻辑
  const executeAndVerify = async (commands: string[]): Promise<{ success: boolean; errorInfo?: string }> => {
    if (!appletRef.current) return { success: false };
    
    let lastError = "";

    const consumeGeoGebraDialogs = (): string[] => {
      // GeoGebra often reports failures via in-app dialogs (OK/Close) instead of throwing.
      // We extract messages and close dialogs so the app can continue.
      const btnTexts = ['close', 'ok', '确定', '关闭'];
      // IMPORTANT: only scan inside the GeoGebra applet container, otherwise we may
      // accidentally treat our own UI buttons (e.g. DebugPanel "Close") as GeoGebra dialogs.
      const ggbRoot = document.getElementById('ggb-canvas-root') || document.body;
      const btns = Array.from(ggbRoot.querySelectorAll('button')) as HTMLButtonElement[];
      const targetBtn =
        btns.find((b) => btnTexts.some((t) => (b.textContent || '').trim().toLowerCase() === t)) ||
        btns.find((b) => btnTexts.some((t) => (b.textContent || '').toLowerCase().includes(t.toLowerCase())));
      if (!targetBtn) return [];

      // Walk up to find a container with error text.
      let node: HTMLElement | null = targetBtn;
      let best: HTMLElement | null = null;
      for (let i = 0; i < 12 && node; i++) {
        const t = (node.innerText || '').trim();
        if (
          t.includes('Unknown command') ||
          t.includes('Circular definition') ||
          t.includes('Undefined variable') ||
          t.includes('Please check your input') ||
          t.includes('Error') ||
          t.includes('错误') ||
          t.includes('未定义')
        ) {
          best = node;
        }
        node = node.parentElement;
      }

      const rawText = ((best || targetBtn.parentElement) as HTMLElement | null)?.innerText || '';
      // Close the dialog to unblock UI.
      targetBtn.click();

      const lines = rawText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);

      // Prefer concise, high-signal error line(s)
      const picked =
        lines.find((l) => l.includes('Unknown command')) ||
        lines.find((l) => l.includes('Circular definition')) ||
        lines.find((l) => l.includes('Undefined variable')) ||
        lines.find((l) => l.toLowerCase().includes('error')) ||
        null;

      return [picked || (lines.length ? lines.slice(0, 6).join(' | ') : 'GeoGebra dialog error')].filter(Boolean);
    };

    const isNoCreateCommand = (cmd: string) => {
      // Commands that often don't create new objects (they can still be valid).
      return /^(SetColor|SetPointSize|SetLineThickness|SetLineStyle|SetLabelVisible|SetVisibleInView|ShowGrid|ShowAxes|SetAxesVisible|SetGridVisible|SetCoordSystem|SetAxesRatio|Zoom(In|Out)|Pan|UpdateConstruction)\b/i.test(
        cmd.trim()
      );
    };

    const isLikelyCreateCommand = (cmd: string) => {
      const t = cmd.trim();
      if (/^\w+\s*=/.test(t)) return true; // assignment creates/defines something
      return /^(Point|Circle|Segment|Ray|Line|Polygon|Midpoint|Intersect|PerpendicularLine|Function|Angle|Text)\s*\(/i.test(
        t
      );
    };

    const isLikelyDeleteCommand = (cmd: string) => /^(Delete|Remove|DeleteObject)/i.test(cmd.trim());

    const isLikelyAlgebra = (cmds: string[]) => {
      const joined = cmds.join('\n').toLowerCase();
      return (
        /(^|\n)\s*[a-z]\w*\(x\)\s*=/.test(joined) ||
        /(^|\n)\s*y\s*=/.test(joined) ||
        /\bsin\b|\bcos\b|\btan\b|\blog\b|\bexp\b/.test(joined) ||
        /\bfunction\b|\bderivative\b|\bintegral\b/.test(joined)
      );
    };

    const applyCanvasPreset = (kind: 'geometry' | 'algebra') => {
      const api = appletRef.current as any;
      try {
        if (kind === 'geometry') {
          api.setAxesVisible?.(false, false);
          api.setGridVisible?.(false);
        } else {
          api.setAxesVisible?.(true, true);
          api.setGridVisible?.(true);
        }
      } catch {
        // best-effort
      }
    };

    const showKeyLabels = () => {
      const api = appletRef.current as any;
      try {
        const names: string[] = getCurrentObjects();
        const keyPoints = names.filter((n) => /^[A-Z]$/.test(n)); // A,B,C,...
        for (const p of keyPoints) {
          try {
            api.setCaption?.(p, p);
            api.setLabelVisible?.(p, true);
          } catch {
            // ignore
          }
        }
      } catch {
        // ignore
      }
    };

    const hideAngleValueLabels = () => {
      const api = appletRef.current as any;
      try {
        const names: string[] = getCurrentObjects();
        for (const n of names) {
          let isAngle = false;
          try {
            const t = api.getObjectType?.(n);
            if (typeof t === 'string' && t.toLowerCase() === 'angle') isAngle = true;
          } catch {
            // ignore
          }
          // Fallback heuristic: common naming convention
          if (!isAngle && /^ang/i.test(n)) isAngle = true;
          if (!isAngle) continue;
          try {
            api.setLabelVisible?.(n, false);
          } catch {
            // ignore
          }
        }
      } catch {
        // ignore
      }
    };

    const validateDiagram = (): string[] => {
      const api = appletRef.current as any;
      const warnings: string[] = [];
      try {
        const names: string[] = getCurrentObjects();
        const angles: string[] = [];
        for (const n of names) {
          let isAngle = false;
          try {
            const t = api.getObjectType?.(n);
            if (typeof t === 'string' && t.toLowerCase() === 'angle') isAngle = true;
          } catch {
            // ignore
          }
          if (!isAngle && /^ang/i.test(n)) isAngle = true;
          if (isAngle) angles.push(n);
        }
        if (angles.length > 6) {
          warnings.push(`Too many angle objects (${angles.length}); keep only necessary arcs.`);
        }
        for (const ang of angles) {
          try {
            const visible = api.getLabelVisible?.(ang);
            if (visible === true) {
              warnings.push(`Angle label still visible: ${ang} (should hide numeric labels).`);
            }
          } catch {
            // ignore
          }
        }
      } catch {
        // ignore
      }
      return warnings;
    };

    // Decide canvas mode per request and apply global preset (best-effort).
    const preset: 'geometry' | 'algebra' = isLikelyAlgebra(commands) ? 'algebra' : 'geometry';
    applyCanvasPreset(preset);
    
    for (const cmd of commands) {
      try {
        // Drain any existing dialogs before issuing a new command (they can block input).
        for (let i = 0; i < 8; i++) {
          const drained = consumeGeoGebraDialogs();
          if (drained.length === 0) break;
          lastError += `GeoGebra dialog: "${drained.join(' ; ')}" (pre-existing). `;
          // eslint-disable-next-line no-await-in-loop
          await new Promise((r) => setTimeout(r, 20));
        }

        const before = getCurrentObjects();
        // Try to extract assigned object name, e.g. "m_parallel = Line(A, l)" -> "m_parallel"
        // IMPORTANT: allow underscores; many models use snake_case names.
        const match = cmd.match(/^([A-Za-z][A-Za-z0-9_]*)\s*=/);
        const objectName = match ? match[1] : null;

        const trimmed = cmd.trim();

        // Bridge: some "label" features are unavailable as GeoGebra commands in this environment,
        // but exist as JS API methods. Translate a few common patterns.
        const api = appletRef.current as any;
        const labelMatch = trimmed.match(/^Label\(\s*([A-Za-z0-9_]+)\s*,\s*["']([^"']+)["']\s*\)\s*$/i);
        const setCaptionMatch = trimmed.match(/^SetCaption\(\s*([A-Za-z0-9_]+)\s*,\s*["']([^"']+)["']\s*\)\s*$/i);
        const setLabelVisibleMatch = trimmed.match(/^SetLabelVisible\(\s*([A-Za-z0-9_]+)\s*,\s*(true|false)\s*\)\s*$/i);
        const showLabelMatch = trimmed.match(/^ShowLabel\(\s*([A-Za-z0-9_]+)\s*,\s*(true|false)\s*\)\s*$/i);
        const showAxesMatch = trimmed.match(/^ShowAxes\(\s*(true|false)\s*\)\s*$/i);
        const showGridMatch = trimmed.match(/^ShowGrid\(\s*(true|false)\s*\)\s*$/i);
        const setAxesVisibleMatch = trimmed.match(/^SetAxesVisible\(\s*(true|false)\s*,\s*(true|false)\s*\)\s*$/i);
        const setGridVisibleMatch = trimmed.match(/^SetGridVisible\(\s*(true|false)\s*\)\s*$/i);
        const deleteMatch = trimmed.match(/^Delete\(\s*([A-Za-z0-9_]+)\s*\)\s*$/i);
        const deleteObjectMatch = trimmed.match(/^DeleteObject\(\s*([A-Za-z0-9_]+)\s*\)\s*$/i);
        const setLineThicknessMatch = trimmed.match(
          /^SetLineThickness\(\s*([A-Za-z0-9_]+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*$/i
        ) || trimmed.match(
          /^SetLineThickness\[\s*([A-Za-z0-9_]+)\s*,\s*([+-]?\d*\.?\d+)\s*\]\s*$/i
        );
        const setLineStyleMatch = trimmed.match(
          /^SetLineStyle\(\s*([A-Za-z0-9_]+)\s*,\s*([+-]?\d+)\s*\)\s*$/i
        ) || trimmed.match(
          /^SetLineStyle\[\s*([A-Za-z0-9_]+)\s*,\s*([+-]?\d+)\s*\]\s*$/i
        );
        const setPointSizeMatch = trimmed.match(
          /^SetPointSize\(\s*([A-Za-z0-9_]+)\s*,\s*([+-]?\d+)\s*\)\s*$/i
        ) || trimmed.match(
          /^SetPointSize\[\s*([A-Za-z0-9_]+)\s*,\s*([+-]?\d+)\s*\]\s*$/i
        );
        const setColorMatch = trimmed.match(
          /^SetColor\(\s*([A-Za-z0-9_]+)\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)\s*$/i
        ) || trimmed.match(
          /^SetColor\[\s*([A-Za-z0-9_]+)\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\]\s*$/i
        );
        const functionGraphMatch =
          trimmed.match(
            /^([A-Za-z][A-Za-z0-9_]*)\s*=\s*FunctionGraph\(\s*['"]([^'"]+)['"]\s*(?:,\s*(true|false)\s*)?\)\s*$/i
          ) ||
          trimmed.match(
            /^FunctionGraph\(\s*['"]([^'"]+)['"]\s*(?:,\s*(true|false)\s*)?\)\s*$/i
          );
        const setCoordsMatch = trimmed.match(
          /^SetCoords\(\s*([A-Za-z0-9_]+)\s*,\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*$/i
        );
        const setValuePointMatch = trimmed.match(
          /^SetValue\(\s*([A-Za-z0-9_]+)\s*,\s*\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*\)\s*$/i
        );

        if (labelMatch) {
          const obj = labelMatch[1];
          const caption = labelMatch[2];
          try {
            api.setCaption?.(obj, caption);
            api.setLabelVisible?.(obj, true);
          } catch (e: any) {
            lastError += `Label bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setCaptionMatch) {
          const obj = setCaptionMatch[1];
          const caption = setCaptionMatch[2];
          try {
            api.setCaption?.(obj, caption);
          } catch (e: any) {
            lastError += `SetCaption bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setLabelVisibleMatch || showLabelMatch) {
          const m = setLabelVisibleMatch || showLabelMatch;
          const obj = m![1];
          const visible = m![2].toLowerCase() === 'true';
          try {
            api.setLabelVisible?.(obj, visible);
          } catch (e: any) {
            lastError += `SetLabelVisible bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (showAxesMatch) {
          const visible = showAxesMatch[1].toLowerCase() === 'true';
          try {
            api.setAxesVisible?.(visible, visible);
          } catch (e: any) {
            lastError += `ShowAxes bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (showGridMatch) {
          const visible = showGridMatch[1].toLowerCase() === 'true';
          try {
            api.setGridVisible?.(visible);
          } catch (e: any) {
            lastError += `ShowGrid bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setAxesVisibleMatch) {
          const x = setAxesVisibleMatch[1].toLowerCase() === 'true';
          const y = setAxesVisibleMatch[2].toLowerCase() === 'true';
          try {
            api.setAxesVisible?.(x, y);
          } catch (e: any) {
            lastError += `SetAxesVisible bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setGridVisibleMatch) {
          const visible = setGridVisibleMatch[1].toLowerCase() === 'true';
          try {
            api.setGridVisible?.(visible);
          } catch (e: any) {
            lastError += `SetGridVisible bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (deleteMatch || deleteObjectMatch) {
          const m = deleteMatch || deleteObjectMatch;
          const obj = m![1];
          try {
            api.deleteObject?.(obj);
          } catch (e: any) {
            lastError += `Delete bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setLineThicknessMatch) {
          const obj = setLineThicknessMatch[1];
          const thickness = Number(setLineThicknessMatch[2]);
          try {
            api.setLineThickness?.(obj, thickness);
          } catch (e: any) {
            lastError += `SetLineThickness bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setLineStyleMatch) {
          const obj = setLineStyleMatch[1];
          const style = Number(setLineStyleMatch[2]);
          try {
            api.setLineStyle?.(obj, style);
          } catch (e: any) {
            lastError += `SetLineStyle bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setPointSizeMatch) {
          const obj = setPointSizeMatch[1];
          const size = Number(setPointSizeMatch[2]);
          try {
            api.setPointSize?.(obj, size);
          } catch (e: any) {
            lastError += `SetPointSize bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (setColorMatch) {
          const obj = setColorMatch[1];
          const r = Math.max(0, Math.min(255, Number(setColorMatch[2])));
          const g = Math.max(0, Math.min(255, Number(setColorMatch[3])));
          const b = Math.max(0, Math.min(255, Number(setColorMatch[4])));
          try {
            api.setColor?.(obj, r, g, b);
          } catch (e: any) {
            lastError += `SetColor bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }
        if (functionGraphMatch) {
          const hasName = functionGraphMatch.length >= 3 && functionGraphMatch[2] !== undefined;
          const name = hasName ? functionGraphMatch[1] : 'f';
          const rawExpr = hasName ? functionGraphMatch[2] : functionGraphMatch[1];
          let expr = String(rawExpr || '').trim();
          expr = expr.replace(/^y\s*=\s*/i, '');
          // Convert FunctionGraph('sin(x)*x') -> f(x)=sin(x)*x (GeoGebra Classic-friendly)
          const translated = `${name}(x)=${expr}`;
          const ok = api.evalCommand(translated);
          if (ok === false) {
            lastError += `Command failed (translated from FunctionGraph): "${translated}". `;
          }
          continue;
        }
        if (setCoordsMatch || setValuePointMatch) {
          const m = setCoordsMatch || setValuePointMatch;
          const obj = m![1];
          const x = Number(m![2]);
          const y = Number(m![3]);
          try {
            api.setCoords?.(obj, x, y);
          } catch (e: any) {
            lastError += `SetCoords bridge failed for "${cmd}": ${e?.message || e}. `;
          }
          continue;
        }

        const ok = api.evalCommand(cmd);
        const after = getCurrentObjects();

        // GeoGebra returns false for invalid/unknown commands even when it doesn't throw.
        if (ok === false) {
          lastError += `Command failed (evalCommand returned false): "${cmd}". `;
        }

        // GeoGebra may render error dialogs asynchronously and can stack many dialogs.
        // Drain a bunch so we don't miss important details.
        const dialogMsgs: string[] = [];
        for (let i = 0; i < 40; i++) {
          const drained = consumeGeoGebraDialogs();
          if (drained.length === 0) break;
          dialogMsgs.push(...drained);
          // eslint-disable-next-line no-await-in-loop
          await new Promise((r) => setTimeout(r, 25));
        }
        if (dialogMsgs.length > 0) {
          lastError += `GeoGebra dialog: "${dialogMsgs.join(' ; ')}" for command "${cmd}". `;
        }

        // 如果该命令应该是创建对象的，检查它是否真的存在
        if (objectName && !appletRef.current.exists(objectName)) {
          lastError += `Command failed: "${cmd}" (Object "${objectName}" was not created). `;
          continue;
        }

        // Heuristic verification for non-assignment create/delete commands.
        // GeoGebra doesn't always throw; use object count changes as a signal.
        if (!objectName && !isNoCreateCommand(cmd)) {
          if (isLikelyCreateCommand(cmd) && after.length === before.length) {
            lastError += `Command likely failed: "${cmd}" (No new objects were created). `;
          }
          if (isLikelyDeleteCommand(cmd) && after.length >= before.length) {
            lastError += `Command likely failed: "${cmd}" (Objects were not removed). `;
          }
        }
      } catch (e: any) {
        lastError += `Syntax error in "${cmd}": ${e.message}. `;
      }
    }

    // For pure geometry tasks, automatically show labels for key points (A,B,C,...) after execution.
    let qualityWarnings: string[] = [];
    if (preset === 'geometry') {
      showKeyLabels();
      // Proof diagrams often look messy if angle numeric labels are shown (multiple degrees, reflex values).
      // Keep angle arcs but hide their numeric labels.
      hideAngleValueLabels();
      qualityWarnings = validateDiagram();
      if (qualityWarnings.length > 0) {
        lastError += `Diagram quality issues: ${qualityWarnings.join(' ')} `;
      }
    }

    return lastError ? { success: false, errorInfo: lastError } : { success: true };
  };

  const toChatMessages = (msgs: Message[]): ChatMessage[] => {
    const recent = msgs.slice(-20); // keep last 20 turns to limit payload
    return recent.map((m) => ({
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: m.content,
      commands: m.commands,
    }));
  };

  const detectEditIntent = (text: string) => {
    const t = text.toLowerCase();
    return (
      /删除|去掉|移除|清除|清空|重画|重绘|重做|改一下|修改|擦掉|只保留|保留/.test(text) ||
      /delete|remove|clear|reset|redo|redraw|rewrite|cleanup/.test(t)
    );
  };

  const isProofQuery = (text: string) => {
    const t = text.toLowerCase();
    return /证明|为什么|原理|解释/.test(text) || /prove|explain why|reason/.test(t);
  };

  const getPreferenceString = () => {
    const key = 'ggb.preferences';
    const fallback =
      'Audience: middle-school; Proof: minimal helpers; hide angle values; label angles with alpha/beta/gamma; avoid long extended lines; keep diagram uncluttered.';
    try {
      const stored = localStorage.getItem(key);
      if (stored && stored.trim().length > 0) return stored;
      localStorage.setItem(key, fallback);
      return fallback;
    } catch {
      return fallback;
    }
  };

  const localIntentHeuristic = (text: string, hasObjects: boolean) => {
    if (!hasObjects) return { needsState: false, needsObjects: false, kind: 'draw' as const };
    const t = String(text || '');
    const lower = t.toLowerCase();
    const mentionsExisting =
      /你画了什么|我画了什么|画了个什么|现在是什么|这是什么形状|是什么形状|what did i draw|what shape|what is this shape/.test(lower) ||
      /画布|画板|画面|当前图|当前画布|当前画面|画布上|画板上|on the canvas|current drawing|current objects/.test(lower) ||
      /有哪些对象|有哪些元素|有哪些点|有哪些线|有什么对象|有什么点|有什么线|有什么图|what objects|which objects/.test(lower) ||
      /这个|刚才|上面|下面|这里|那条|那个|此图|现有|基于/.test(t) ||
      /modify|edit|change|move|shift|adjust|based on/.test(lower) ||
      /删除|去掉|移除|清除|清空|重画|重绘|重做|改一下|修改|移动|拖动|加粗|变粗|变细|变浅|颜色|改颜色|隐藏|显示|标注|标签|简化|辅助线|只保留|保留/.test(t);
    const mentionsObjectName = /\b[A-Z]\b/.test(t) || /点[A-Z]/.test(t) || /[A-Z]点/.test(t);
    const needs = Boolean(mentionsExisting || mentionsObjectName);
    return { needsState: needs, needsObjects: needs, kind: (needs ? 'edit' : 'question') as const };
  };

  const shouldAttachStateViaIntent = async (text: string) => {
    try {
      const hasObjects = getCurrentObjects().length > 0;
      if (!hasObjects) return { needsState: false, needsObjects: false, kind: 'draw' as const };

      // If local heuristic is confident it's an edit, skip the intent model to save cost/latency.
      const heuristic = localIntentHeuristic(text, hasObjects);
      if (heuristic.needsState || heuristic.needsObjects) {
        pushDebug({ type: 'intent_heuristic', text, hasObjects, decision: heuristic });
        return heuristic;
      }

      const ctrl = new AbortController();
      const timer = window.setTimeout(() => ctrl.abort(), 1800);
      const res = await fetch('/api/intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, hasObjects }),
        signal: ctrl.signal,
      });
      window.clearTimeout(timer);
      if (!res.ok) return { needsState: false, needsObjects: false, kind: 'other' as const };
      const data = (await res.json()) as { needsState?: boolean; needsObjects?: boolean; kind?: string };
      pushDebug({ type: 'intent', text, hasObjects, decision: data });
      return {
        needsState: Boolean(data.needsState),
        needsObjects: Boolean(data.needsObjects),
        kind: (data.kind as any) || ('other' as const),
      };
    } catch {
      const hasObjects = getCurrentObjects().length > 0;
      const fallback = localIntentHeuristic(text, hasObjects);
      pushDebug({ type: 'intent_fallback', text, hasObjects, decision: fallback });
      return fallback;
    }
  };

  const handleSendMessage = async (text: string) => {
    const runId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const userMessage: Message = { role: 'user', content: text, timestamp: Date.now() };
    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    let retryCount = 0;
    let errorContext = "";
    let finalResponse: GGBResponse | null = null;
    const attemptRecords: any[] = [];
    let forceIncludeCanvasState = false;
    const wantsClear = /^(清屏|清空|清除|重置|reset|clear)$/i.test(text.trim());
    const maybeEdit = detectEditIntent(text);
    const preferences = getPreferenceString();
    let phase: 'draw' | 'proof' | 'edit' | 'repair' = isProofQuery(text) ? 'proof' : 'draw';
    const intent = await shouldAttachStateViaIntent(text);

    try {
      pushDebug({
        type: 'chat_run_start',
        runId,
        prompt: text,
        endpointId,
        hasObjects: getCurrentObjects().length > 0,
        intent,
      });

      if (wantsClear) {
        // Deterministic clear: do not rely on LLM to delete objects.
        const api = appletRef.current as any;
        const names = getCurrentObjects();
        for (const n of names) {
          try {
            api.deleteObject?.(n);
          } catch {
            // ignore
          }
        }
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: '已清空画板。',
            timestamp: Date.now(),
          },
        ]);
        setOverlayTexts({});
        pushDebug({ type: 'chat_run_done', runId, prompt: text, endpointId, success: true, cleared: true });
        return;
      }

      // Attach canvas context when the (small) intent model says it's needed, or when we detect edit keywords.
      if (wantsClear || maybeEdit || intent.needsState || intent.needsObjects) {
        // Provide immediate environment context so the model can generate correct delete/modify commands.
        const current = appletRef.current?.getAllObjectNames?.();
        const currentObjects = Array.isArray(current)
          ? current
          : typeof current === 'string'
            ? current.split(',').map((s) => s.trim()).filter(Boolean)
            : [];
        const intentLabel = wantsClear ? 'clear/reset' : (maybeEdit ? 'edit/modify' : `context-needed(${intent.kind || 'other'})`);
        const state = intent.needsState || wantsClear || maybeEdit ? buildStateSummary() : '';
        errorContext =
          `User intent: ${intentLabel}. ` +
          (intent.needsObjects || wantsClear || maybeEdit
            ? (currentObjects.length > 0 ? `Current objects: ${currentObjects.join(", ")}.` : `Current objects: (none).`)
            : '') +
          (state ? ` State: ${state}` : '');
      }

      if (errorContext.trim().length > 0) {
        pushDebug({
          type: 'chat_context',
          runId,
          prompt: text,
          endpointId,
          retryCount: 0,
          errorContext,
        });
      }

      // 自我修正循环
      while (retryCount < 5) {
        if (retryCount > 0) {
          console.log(`正在进行第 ${retryCount} 次自动修正...`);
        }

        // Build chat history for this attempt
        const baseHistory: ChatMessage[] = toChatMessages([...messages, userMessage]);
        const toolHistory: ChatMessage[] =
          errorContext.trim().length > 0
            ? [{ role: 'tool', content: errorContext }]
            : [];

        if (maybeEdit || intent.needsState || intent.needsObjects) {
          phase = 'edit';
        }

        const effectivePhase: typeof phase = retryCount > 0 ? 'repair' : phase;
        // Default: do NOT send canvasState. Only attach when the user intent depends on the existing canvas.
        const includeCanvasState = Boolean(
          forceIncludeCanvasState ||
          wantsClear ||
          maybeEdit ||
          intent.needsState ||
          intent.needsObjects
        );
        const canvasState = includeCanvasState ? buildCanvasStateForLLM() : undefined;
        const canvasMsg: ChatMessage[] = []; // not auto-injecting as message

        const chatRequest = {
          messages: [...baseHistory, ...toolHistory, ...canvasMsg],
          endpointId: endpointId === 'auto' ? undefined : endpointId,
          // Always allow fallback; endpointId only sets preference order.
          mode: 'auto',
          phase: effectivePhase,
          preferences,
          // Used by codex-cli provider to keep per-tab conversation state on the server machine.
          codexTabId: tabIdRef.current || undefined,
          // Optional: current canvas summary; default OFF (on-demand only).
          canvasState,
        };
        pushDebug({
          type: 'chat_attempt_start',
          runId,
          prompt: text,
          retryCount,
          phase: effectivePhase,
          endpointId,
          errorContext,
          request: chatRequest,
        });
        const apiRes = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(chatRequest),
        });

        if (!apiRes.ok) {
          const { text: errText, json } = await readErrorPayload(apiRes);
          pushDebug({
            type: 'api_chat_error',
            runId,
            prompt: text,
            retryCount,
            endpointId,
            phase: effectivePhase,
            status: apiRes.status,
            error: errText || `API error: ${apiRes.status}`,
            debugTrace: json?.debugTrace,
            promptVersion: json?.promptVersion,
            request: chatRequest,
          });
          throw new Error(errText || `API error: ${apiRes.status}`);
        }

        const { response, usedEndpointId, usedModelId, usedProvider, usedLabel, debugTrace, promptVersion, toolCalls } = (await apiRes.json()) as {
          response: GGBResponse;
          usedEndpointId: string;
          usedModelId?: string | null;
          usedProvider?: string | null;
          usedLabel?: string | null;
          debugTrace?: any[];
          promptVersion?: string;
          toolCalls?: any;
        };

        pushDebug({
          type: 'llm_response',
          runId,
          prompt: text,
          retryCount,
          endpointId,
          usedEndpointId,
          usedModelId,
          usedProvider,
          usedLabel,
          errorContext,
          phase: effectivePhase,
          response,
          debugTrace,
          promptVersion,
          toolCalls,
          request: chatRequest,
        });

        const attemptRecord: any = {
          attempt: retryCount,
          phase: effectivePhase,
          includeCanvasState,
          forceIncludeCanvasState,
          wantsClear,
          maybeEdit,
          intent,
          usedEndpointId,
          usedProvider,
          usedModelId,
          usedLabel,
          promptVersion,
          toolCalls,
          response: {
            overlayText: (response as any)?.overlayText || null,
            commandsCount: Array.isArray(response?.commands) ? response.commands.length : 0,
          },
        };
        attemptRecords.push(attemptRecord);

        // If the model requested `get_canvas_state` but we didn't attach canvasState, retry once with canvasState.
        const requestedCanvasViaTool = Array.isArray(toolCalls)
          ? toolCalls.some((c: any) => String(c?.toolName || '').toLowerCase() === 'get_canvas_state')
          : false;
        if (requestedCanvasViaTool && !includeCanvasState) {
          const cs = buildCanvasStateForLLM();
          if (cs) {
            attemptRecord.action = 'retry_with_canvasState_due_to_tool_request';
            forceIncludeCanvasState = true;
            retryCount += 1;
            continue;
          }
        }

        // 如果模型请求画布状态，则把当前画布作为 tool 消息喂回，再重试，不计为执行失败。
        const canvasRequested =
          response?.explanation?.includes(CANVAS_STATE_REQUEST_TOKEN) ||
          (Array.isArray(response?.commands) && response.commands.some((c) => c.includes(CANVAS_STATE_REQUEST_TOKEN)));
        if (canvasRequested) {
          const cs = buildCanvasStateForLLM();
          if (cs) {
            errorContext = cs; // 将其作为 tool 消息注入
            // Also attach `canvasState` on the retry so the server can stop re-injecting the request token.
            // (The token is only a hidden retry trigger, not user-facing content.)
            attemptRecord.action = 'retry_with_canvasState_due_to_internal_token';
            forceIncludeCanvasState = true;
            retryCount += 1;
            continue; // 跳过执行，直接进入下一轮让模型利用画布数据
          }
        }
        
        // 尝试执行（记录 attempt 前对象，便于失败时回滚，避免“错误图形残留叠加”）
        const attemptBeforeObjects = getCurrentObjects();
        const result = await executeAndVerify(response.commands);
        
        if (result.success) {
          attemptRecord.exec = { success: true };
          const explanationText = stripInternalTokensForDisplay(String((response as any)?.explanation ?? ''));
          finalResponse = {
            ...response,
            explanation:
              endpointId === 'auto'
                ? `（已使用：${usedEndpointId}）${explanationText}`
                : explanationText,
          };
          if ((response as any)?.overlayText?.corner && typeof (response as any)?.overlayText?.text === 'string') {
            const corner = (response as any).overlayText.corner as Corner;
            const text = String((response as any).overlayText.text);
            setOverlayTexts((prev) => ({ ...prev, [corner]: text }));
          }
          pushDebug({
            type: 'chat_attempt_done',
            runId,
            prompt: text,
            retryCount,
            endpointId,
            usedEndpointId,
            success: true,
          });
          break;
        } else {
          // Roll back objects created during this failed attempt so the next retry starts clean.
          const { rolledBack } = rollbackCreatedObjects(attemptBeforeObjects);
          attemptRecord.exec = { success: false, errorInfo: result.errorInfo || null, rolledBack };

          // Feed back precise failed command info so the model can repair.
          const currentObjects = getCurrentObjects();
          const state = buildStateSummary();
          errorContext =
            (result.errorInfo || "Unknown execution error") +
            (rolledBack.length > 0 ? ` Rolled back: ${rolledBack.join(", ")}.` : "") +
            (currentObjects.length > 0 ? ` Current objects: ${currentObjects.join(", ")}.` : ` Current objects: (none).`) +
            (state ? ` State: ${state}.` : "");
          pushDebug({
            type: 'ggb_error',
            runId,
            prompt: text,
            retryCount,
            usedEndpointId,
            errorInfo: result.errorInfo,
            nextErrorContext: errorContext,
            rolledBack,
          });
          pushDebug({
            type: 'chat_attempt_done',
            runId,
            prompt: text,
            retryCount,
            endpointId,
            usedEndpointId,
            success: false,
          });
          retryCount++;
          // 如果失败了，在重试前清理掉可能产生的碎片对象
          // （可选：可以根据需要决定是否 reset）
        }
      }

      if (finalResponse) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: retryCount > 0 ? `经过修正，${finalResponse?.explanation}` : finalResponse?.explanation || "",
          commands: finalResponse?.commands,
          meta: {
            runRecord: {
              runId,
              retries: retryCount,
              endpointPreference: endpointId,
              attempts: attemptRecords,
            },
          },
          timestamp: Date.now()
        }]);
        pushDebug({
          type: 'chat_run_done',
          runId,
          prompt: text,
          endpointId,
          success: true,
          retries: retryCount,
        });
        try {
        appletRef.current?.setAxesRatio(1, 1);
        } catch (e) {
          // GeoGebra may throw intermittently; avoid marking the whole request as failed when drawing succeeded.
        }
      } else {
        throw new Error("指令修正失败，达到最大尝试次数。");
      }

    } catch (error: any) {
      let errorMsg = "抱歉，绘图请求失败。您可以尝试简化描述或重试。";
      if (error.message?.includes("No LLM endpoint is configured")) {
        errorMsg = "未配置任何模型 Endpoint。请在服务端 .env.local 配置 LLM_ENDPOINTS_JSON 后重启。";
        setHasApiKey(false);
      } else if (error.message?.includes("Failed to fetch") || error.message?.includes("API error")) {
        errorMsg = "后端 AI 代理未启动或不可用。请先启动 server（默认 3002 端口），再刷新页面。";
        setHasApiKey(false);
      }
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: errorMsg,
        timestamp: Date.now()
      }]);
      pushDebug({
        type: 'chat_run_done',
        runId,
        prompt: text,
        endpointId,
        success: false,
        error: error?.message || String(error),
      });
    } finally {
      setIsLoading(false);
    }
  };

  const runSelfTest = useCallback(async () => {
    if (selfTestRunning) return;
    setSelfTestRunning(true);
    pushDebug({ type: 'selftest_start' });
    const cases = [
      { id: 'angle-sum', prompt: '如何证明三角形的内角和是180度？请用画板辅助表达，给小朋友讲清楚。' },
      { id: 'parallel', prompt: '过直线外一点，如何做平行线？给我画示意图。' },
      { id: 'pythagoras', prompt: '什么是勾股定理，解释，然后画一个示意图' },
      { id: 'rollback', prompt: '用 RegularPolygon 画一个正方形，然后如果失败请修正并重新画。' },
      { id: 'algebra', prompt: '在 GeoGebra Classic 里画出函数 y = sin(x) * x。请用可执行命令（不要用 FunctionGraph 命令）。' },
    ];

    try {
      for (const tc of cases) {
        const before = getCurrentObjects();
        const startedAt = Date.now();
        try {
          const apiRes = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              messages: [{ role: 'user', content: tc.prompt }],
              endpointId: endpointId === 'auto' ? undefined : endpointId,
              // Always allow fallback; endpointId only sets preference order.
              mode: 'auto',
              codexTabId: tabIdRef.current || undefined,
            }),
          });
          if (!apiRes.ok) {
            const { text: errText, json } = await readErrorPayload(apiRes);
            pushDebug({
              type: 'selftest_case',
              id: tc.id,
              prompt: tc.prompt,
              pass: false,
              stage: 'api',
              error: errText || apiRes.status,
              debugTrace: json?.debugTrace,
              ms: Date.now() - startedAt,
            });
            // best-effort cleanup
            rollbackCreatedObjects(before);
            continue;
          }
          const { response, usedEndpointId, usedModelId, usedProvider, usedLabel, debugTrace } = (await apiRes.json()) as {
            response: GGBResponse;
            usedEndpointId: string;
            usedModelId?: string | null;
            usedProvider?: string | null;
            usedLabel?: string | null;
            debugTrace?: any[];
          };
          const exec = await executeAndVerify(response.commands);
          if (!exec.success) {
            const { rolledBack } = rollbackCreatedObjects(before);
            pushDebug({
              type: 'selftest_case',
              id: tc.id,
              prompt: tc.prompt,
              pass: false,
              stage: 'exec',
              usedEndpointId,
              usedModelId,
              usedProvider,
              usedLabel,
              error: exec.errorInfo,
              rolledBack,
              debugTrace,
              ms: Date.now() - startedAt,
            });
            continue;
          }
          // Cleanup after pass to keep tests isolated
          const { rolledBack } = rollbackCreatedObjects(before);
          pushDebug({
            type: 'selftest_case',
            id: tc.id,
            prompt: tc.prompt,
            pass: true,
            usedEndpointId,
            usedModelId,
            usedProvider,
            usedLabel,
            cleaned: rolledBack.length,
            debugTrace,
            ms: Date.now() - startedAt,
          });
        } catch (e: any) {
          rollbackCreatedObjects(before);
          pushDebug({ type: 'selftest_case', id: tc.id, prompt: tc.prompt, pass: false, stage: 'exception', error: e?.message || String(e) });
        }
      }
    } finally {
      pushDebug({ type: 'selftest_done' });
      setSelfTestRunning(false);
    }
  }, [endpointId, executeAndVerify, getCurrentObjects, pushDebug, readErrorPayload, rollbackCreatedObjects, selfTestRunning]);

  const runOnePrompt = useCallback(
    async (prompt: string) => {
      if (promptRunning) return;
      setPromptRunning(true);
      const before = getCurrentObjects();
      const startedAt = Date.now();
      pushDebug({ type: 'prompt_run_start', prompt });
      try {
        const apiRes = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [{ role: 'user', content: prompt }],
            endpointId: endpointId === 'auto' ? undefined : endpointId,
            // Always allow fallback; endpointId only sets preference order.
            mode: 'auto',
            codexTabId: tabIdRef.current || undefined,
          }),
        });
        if (!apiRes.ok) {
          const { text: errText, json } = await readErrorPayload(apiRes);
          pushDebug({
            type: 'prompt_run',
            prompt,
            pass: false,
            stage: 'api',
            error: errText || apiRes.status,
            debugTrace: json?.debugTrace,
            ms: Date.now() - startedAt,
          });
          return;
        }
        const { response, usedEndpointId, usedModelId, usedProvider, usedLabel, debugTrace } = (await apiRes.json()) as {
          response: GGBResponse;
          usedEndpointId: string;
          usedModelId?: string | null;
          usedProvider?: string | null;
          usedLabel?: string | null;
          debugTrace?: any[];
        };
        const exec = await executeAndVerify(response.commands);
        if (!exec.success) {
          const { rolledBack } = rollbackCreatedObjects(before);
          pushDebug({
            type: 'prompt_run',
            prompt,
            pass: false,
            stage: 'exec',
            usedEndpointId,
            usedModelId,
            usedProvider,
            usedLabel,
            response,
            debugTrace,
            error: exec.errorInfo,
            rolledBack,
            objects: getCurrentObjects(),
            ms: Date.now() - startedAt,
          });
          return;
        }
        pushDebug({
          type: 'prompt_run',
          prompt,
          pass: true,
          usedEndpointId,
          usedModelId,
          usedProvider,
          usedLabel,
          response,
          debugTrace,
          objects: getCurrentObjects(),
          ms: Date.now() - startedAt,
        });
      } catch (e: any) {
        pushDebug({ type: 'prompt_run', prompt, pass: false, stage: 'exception', error: e?.message || String(e), ms: Date.now() - startedAt });
      } finally {
        setPromptRunning(false);
      }
    },
    [endpointId, executeAndVerify, getCurrentObjects, promptRunning, pushDebug, readErrorPayload, rollbackCreatedObjects]
  );

  return (
    <div className="flex flex-col md:flex-row h-screen w-screen bg-slate-100 overflow-hidden">
      <aside className="w-full md:w-96 h-[40%] md:h-full bg-white z-20 border-r border-slate-200 shadow-xl">
        <ChatInterface 
          messages={messages} 
          onSendMessage={handleSendMessage} 
          isLoading={isLoading} 
          endpointId={endpointId}
          onEndpointChange={setEndpointId}
          endpoints={endpoints}
        />
      </aside>

      <main className="flex-1 h-[60%] md:h-full flex flex-col p-4 md:p-8 relative min-w-0">
        <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-black text-slate-800 tracking-tighter">
              GeoGebra <span className="text-indigo-600">AI</span>
            </h1>
            {!hasApiKey && (
              <button onClick={handleOpenKey} className="animate-pulse bg-red-500 text-white text-[10px] font-bold px-3 py-1 rounded-full shadow-lg">
                ● 激活 AI 引擎
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
             <button onClick={() => appletRef.current && adjustView(appletRef.current)} className="text-[10px] font-bold text-slate-500 hover:text-indigo-600 uppercase tracking-widest px-3 py-1.5 rounded-lg border border-slate-200 bg-white shadow-sm">
               校准视角
             </button>
             <button onClick={() => setShowDebug((v) => !v)} className="text-[10px] font-bold text-slate-500 hover:text-indigo-600 uppercase tracking-widest px-3 py-1.5 rounded-lg border border-slate-200 bg-white shadow-sm">
               Debug
             </button>
             <div className="hidden sm:block text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">Self-Correction v1</div>
          </div>
        </div>

        <div className="flex-1 relative min-h-0 group">
          <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-2xl blur-lg transition opacity-50"></div>
          <GGBView onReady={onGGBReady} overlayTexts={overlayTexts} />
        </div>
      </main>
      <DebugPanel
        visible={showDebug}
        onClose={() => setShowDebug(false)}
        onRunSelfTest={runSelfTest}
        selfTestRunning={selfTestRunning}
        onSendMessage={handleSendMessage}
        messages={messages}
        promptRunning={isLoading}
      />
    </div>
  );
};

export default App;
