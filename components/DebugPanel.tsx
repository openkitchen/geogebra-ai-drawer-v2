import React, { useEffect, useMemo, useState } from 'react';
import type { Message } from '../types';

interface DebugEntry {
  ts: number;
  [key: string]: any;
}

interface TraceAttempt {
  retryCount: number;
  phase?: string;
  endpointId?: string;
  promptVersion?: string;

  request?: any;
  errorContext?: string;
  toolCalls?: any;

  apiStatus?: number;
  apiError?: string;

  usedEndpointId?: string;
  usedModelId?: string | null;
  usedProvider?: string | null;
  usedLabel?: string | null;

  debugTrace?: any[];
  response?: any;
}

interface TraceRun {
  runId: string;
  prompt: string;
  endpointId?: string;
  startedAt: number;
  doneAt?: number;
  success?: boolean;
  error?: string;
  attempts: TraceAttempt[];
}

interface Props {
  visible: boolean;
  onClose: () => void;
  onRunSelfTest?: () => void;
  selfTestRunning?: boolean;
  onSendMessage?: (prompt: string) => void;
  promptRunning?: boolean;
  messages?: Message[];
}

const LLM_EVENT_TYPES = new Set([
  'chat_run_start',
  'chat_attempt_start',
  'llm_response',
  'api_chat_error',
  'chat_run_done',
]);

const DebugPanel: React.FC<Props> = ({ visible, onClose }) => {
  const [rawLog, setRawLog] = useState<DebugEntry[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');

  useEffect(() => {
    if (!visible) return;
    const timer = setInterval(() => {
      try {
        const w = window as any;
        const log = (w.__ggbDebugLog || []) as DebugEntry[];
        const filtered = Array.isArray(log)
          ? log.filter((e) => e && LLM_EVENT_TYPES.has(String(e.type || '')))
          : [];
        setRawLog(filtered);
      } catch {
        setRawLog([]);
      }
    }, 500);
    return () => clearInterval(timer);
  }, [visible]);

  const formatProviderTrace = (items: any[]): string => {
    const list = Array.isArray(items) ? items : [];

    const pickTokens = (usage: any) => {
      if (!usage) return null;
      const total = usage.totalTokens ?? usage.total_tokens ?? usage.tokens ?? null;
      const input = usage.promptTokens ?? usage.inputTokens ?? usage.input_tokens ?? null;
      const output = usage.completionTokens ?? usage.outputTokens ?? usage.output_tokens ?? null;
      if (total != null || input != null || output != null) return { total, input, output };
      return usage;
    };

    return list
      .map((it) => {
        const ok = it?.ok ? 'OK' : 'FAIL';
        const endpoint = String(it?.endpointId || it?.id || '');
        const label = it?.label ? ` (${it.label})` : '';
        const provider = it?.provider ? ` provider=${it.provider}` : '';
        const baseURL = it?.baseURL ? ` baseURL=${String(it.baseURL)}` : '';
        const model = it?.modelId ? ` model=${it.modelId}` : '';
        const strategy = it?.strategy ? ` strategy=${String(it.strategy)}` : '';
        const ms = Number.isFinite(Number(it?.ms)) ? ` ${Number(it.ms)}ms` : '';
        const tokens = pickTokens(it?.usage);
        const tok = tokens ? ` tokens=${JSON.stringify(tokens)}` : '';
        const err = it?.error ? ` error=${String(it.error)}` : '';
        const raw =
          !it?.ok && it?.rawTextPreview
            ? ` rawPreview=${JSON.stringify(String(it.rawTextPreview).slice(0, 200))}`
            : '';
        return `${ok} ${endpoint}${label}${provider}${baseURL}${model}${strategy}${ms}${tok}${err}${raw}`;
      })
      .join('\n');
  };

  const traces = useMemo<TraceRun[]>(() => {
    const log = Array.isArray(rawLog) ? rawLog : [];
    const byRunId = new Map<string, TraceRun>();

    const ensureRun = (runId: string, promptText: string, ts: number, endpointId?: string) => {
      const existing = byRunId.get(runId);
      if (existing) return existing;
      const run: TraceRun = {
        runId,
        prompt: promptText || '(unknown prompt)',
        endpointId,
        startedAt: ts || Date.now(),
        attempts: [],
      };
      byRunId.set(runId, run);
      return run;
    };

    const ensureAttempt = (run: TraceRun, retryCount: number) => {
      const idx = run.attempts.findIndex((a) => a.retryCount === retryCount);
      if (idx >= 0) return run.attempts[idx];
      const att: TraceAttempt = { retryCount };
      run.attempts.push(att);
      run.attempts.sort((a, b) => a.retryCount - b.retryCount);
      return att;
    };

    for (const e of log) {
      const t = String(e?.type || '');
      const runId = typeof e?.runId === 'string' && e.runId.trim() ? e.runId : null;
      if (!runId) continue;

      const promptText = String(e?.prompt || '');
      const run = ensureRun(runId, promptText, Number(e?.ts || Date.now()), e?.endpointId);
      if (!run.prompt && promptText) run.prompt = promptText;
      if (!run.endpointId && e?.endpointId) run.endpointId = e.endpointId;

      if (t === 'chat_run_start') {
        run.startedAt = Number(e.ts || run.startedAt);
      }

      if (t === 'chat_run_done') {
        run.doneAt = Number(e.ts || Date.now());
        run.success = Boolean(e.success);
        if (e.error) run.error = String(e.error);
      }

      if (t === 'chat_attempt_start') {
        const att = ensureAttempt(run, Number(e.retryCount || 0));
        att.phase = e.phase;
        att.endpointId = e.endpointId;
        att.errorContext = e.errorContext;
        att.request = e.request;
      }

      if (t === 'api_chat_error') {
        const att = ensureAttempt(run, Number(e.retryCount || 0));
        att.phase = e.phase || att.phase;
        att.endpointId = e.endpointId || att.endpointId;
        att.apiStatus = typeof e.status === 'number' ? e.status : att.apiStatus;
        att.apiError = e.error || att.apiError;
        att.debugTrace = Array.isArray(e.debugTrace) ? e.debugTrace : att.debugTrace;
        att.promptVersion = e.promptVersion || att.promptVersion;
        att.request = e.request || att.request;
      }

      if (t === 'llm_response') {
        const att = ensureAttempt(run, Number(e.retryCount || 0));
        att.phase = e.phase || att.phase;
        att.endpointId = e.endpointId || att.endpointId;
        att.usedEndpointId = e.usedEndpointId || att.usedEndpointId;
        att.usedModelId = e.usedModelId ?? att.usedModelId;
        att.usedProvider = e.usedProvider ?? att.usedProvider;
        att.usedLabel = e.usedLabel ?? att.usedLabel;
        att.debugTrace = Array.isArray(e.debugTrace) ? e.debugTrace : att.debugTrace;
        att.response = e.response || att.response;
        att.promptVersion = e.promptVersion || att.promptVersion;
        att.errorContext = e.errorContext || att.errorContext;
        att.toolCalls = e.toolCalls ?? att.toolCalls;
        att.request = e.request || att.request;
      }
    }

    return [...byRunId.values()].sort((a, b) => (b.doneAt || b.startedAt) - (a.doneAt || a.startedAt));
  }, [rawLog]);

  useEffect(() => {
    if (!visible) return;
    if (selectedRunId) return;
    if (traces.length > 0) setSelectedRunId(traces[0].runId);
  }, [visible, traces, selectedRunId]);

  const selectedRun = useMemo(() => traces.find((t) => t.runId === selectedRunId) || null, [traces, selectedRunId]);

  if (!visible) return null;

  return (
    <div className="fixed bottom-4 right-4 w-full max-w-md bg-white border border-slate-200 rounded-xl shadow-2xl z-50">
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-200">
        <div className="text-xs font-bold text-slate-600 uppercase tracking-widest">LLM Trace</div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              try {
                navigator.clipboard?.writeText(JSON.stringify(traces, null, 2));
              } catch {}
            }}
            className="text-xs text-slate-500 hover:text-slate-800"
            title="Copy filtered LLM trace JSON to clipboard"
          >
            Copy
          </button>
          <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-800">Close</button>
        </div>
      </div>

      <div className="max-h-96 overflow-auto text-[11px] leading-relaxed p-3 font-mono bg-slate-50">
        {traces.length === 0 && <div className="text-slate-400">No LLM trace data</div>}

        {traces.length > 0 && (
          <div className="mb-2">
            <div className="text-[10px] text-slate-500 mb-1">Runs</div>
            <select
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="w-full text-[12px] bg-white border border-slate-200 rounded-md px-2 py-1"
            >
              {traces.slice(0, 30).map((r) => (
                <option key={r.runId} value={r.runId}>
                  {new Date(r.startedAt).toLocaleTimeString()} · {r.prompt.slice(0, 26)}{r.prompt.length > 26 ? '…' : ''} · {r.success === true ? 'OK' : r.success === false ? 'FAIL' : '…'}
                </option>
              ))}
            </select>
          </div>
        )}

        {selectedRun && (
          <div className="border border-slate-200 rounded-lg bg-white p-2">
            <div className="text-slate-600 mb-2">
              <div><span className="font-bold">Prompt:</span> {selectedRun.prompt}</div>
              <div><span className="font-bold">Run:</span> {selectedRun.runId}</div>
              <div><span className="font-bold">Selected endpoint:</span> {selectedRun.endpointId || '(auto)'}</div>
              <div><span className="font-bold">Result:</span> {selectedRun.success === true ? 'success' : selectedRun.success === false ? `failed${selectedRun.error ? ` (${selectedRun.error})` : ''}` : 'unknown'}</div>
            </div>

            {selectedRun.attempts.length === 0 && <div className="text-slate-400">No attempts</div>}
            {selectedRun.attempts.map((a) => (
              <details key={a.retryCount} className="mb-2 border-t border-slate-200 pt-2" open={a.retryCount === 0}>
                <summary className="cursor-pointer text-slate-800">
                  Attempt {a.retryCount}
                  {a.phase ? ` · phase=${a.phase}` : ''}
                  {a.usedEndpointId ? ` · used=${a.usedEndpointId}` : ''}
                  {a.usedModelId ? ` · model=${a.usedModelId}` : ''}
                  {a.apiStatus ? ` · api=${a.apiStatus}` : ''}
                </summary>
                <div className="mt-2 space-y-2">
                  {a.promptVersion && (
                    <div>
                      <div className="text-slate-500">Prompt version</div>
                      <pre className="whitespace-pre-wrap break-words">{a.promptVersion}</pre>
                    </div>
                  )}
                  {a.errorContext && (
                    <div>
                      <div className="text-slate-500">Tool feedback (errorContext)</div>
                      <pre className="whitespace-pre-wrap break-words">{a.errorContext}</pre>
                    </div>
                  )}
                  {a.request && (
                    <div>
                      <div className="text-slate-500">Request (/api/chat)</div>
                      <pre className="whitespace-pre-wrap break-words">{JSON.stringify(a.request, null, 2)}</pre>
                    </div>
                  )}
                  {(a.apiError || typeof a.apiStatus === 'number') && (
                    <div>
                      <div className="text-slate-500">API error</div>
                      <pre className="whitespace-pre-wrap break-words">{`${typeof a.apiStatus === 'number' ? `status=${a.apiStatus} ` : ''}${a.apiError || ''}`}</pre>
                    </div>
                  )}
                  {Array.isArray(a.debugTrace) && a.debugTrace.length > 0 && (
                    <div>
                      <div className="text-slate-500">Provider trace (fallback chain)</div>
                      <pre className="whitespace-pre-wrap break-words">{formatProviderTrace(a.debugTrace)}</pre>
                    </div>
                  )}
                  {a.response && (
                    <div>
                      <div className="text-slate-500">Response (LLM JSON)</div>
                      <pre className="whitespace-pre-wrap break-words">{JSON.stringify(a.response, null, 2)}</pre>
                    </div>
                  )}
                  {a.toolCalls && (
                    <div>
                      <div className="text-slate-500">Tool calls (provider raw)</div>
                      <pre className="whitespace-pre-wrap break-words">{JSON.stringify(a.toolCalls, null, 2)}</pre>
                    </div>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DebugPanel;
