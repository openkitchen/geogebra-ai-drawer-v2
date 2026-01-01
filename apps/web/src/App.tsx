import { useEffect, useMemo, useRef, useState } from 'react';
import { CanvasInspector } from './CanvasInspector';
import { GeoGebraApplet } from './GeoGebraApplet';
import { runFrontendTool } from './frontendTools';
import { RunStreamEvent, streamSse } from './sse';

type ChatMessage =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'assistant'; text: string; events: RunStreamEvent[]; status: 'running' | 'done' | 'error'; error?: string };

type FrontendToolInterrupt = Extract<RunStreamEvent, { event: 'interrupt' }>;

function shortId(id: string): string {
  return id.length <= 8 ? id : id.slice(0, 8);
}

function summarizeToolOutput(toolName: string, output: unknown): string {
  if (!output || typeof output !== 'object') return '';

  if (toolName === 'get_canvas_state') {
    const objects = (output as any).objects;
    if (!Array.isArray(objects)) return '';
    const names = objects
      .slice(0, 5)
      .map((o: any) => (typeof o?.name === 'string' ? o.name : null))
      .filter(Boolean);
    return `objects=${objects.length}${names.length ? ` [${names.join(', ')}${objects.length > names.length ? ', …' : ''}]` : ''}`;
  }

  if (toolName === 'eval_expression') {
    const ok = (output as any).ok;
    const labels = (output as any).labels;
    const okText = typeof ok === 'boolean' ? `ok=${ok}` : '';
    const labelsText = Array.isArray(labels)
      ? labels.length
        ? `labels=[${labels
            .filter((x: unknown) => typeof x === 'string' && x.trim().length > 0)
            .slice(0, 3)
            .join(', ')}${labels.length > 3 ? ', …' : ''}]`
        : ''
      : typeof labels === 'string' && labels
        ? `labels=${labels}`
        : '';
    return [okText, labelsText].filter(Boolean).join(' ');
  }

  if (toolName === 'exec_geogebra_commands') {
    const results = (output as any).results;
    if (!Array.isArray(results)) return '';
    const okCount = results.filter((r: any) => r?.ok === true).length;
    const created = (output as any).created_objects;
    const rolledBack = (output as any).rolled_back_objects;
    const dialogs = (output as any).dialogs;
    const parts = [`commands=${results.length}`, `ok=${okCount}`];
    if (Array.isArray(created) && created.length) parts.push(`created=${created.length}`);
    if (Array.isArray(rolledBack) && rolledBack.length) parts.push(`rollback=${rolledBack.length}`);
    if (Array.isArray(dialogs) && dialogs.length) parts.push(`dialogs=${dialogs.length}`);
    return parts.join(' ');
  }

  if (toolName === 'delete_objects') {
    const deleted = (output as any).deleted_objects;
    const failed = (output as any).failed_objects;
    const dialogs = (output as any).dialogs;
    const parts: string[] = [];
    if (Array.isArray(deleted)) parts.push(`deleted=${deleted.length}`);
    if (Array.isArray(failed) && failed.length) parts.push(`failed=${failed.length}`);
    if (Array.isArray(dialogs) && dialogs.length) parts.push(`dialogs=${dialogs.length}`);
    return parts.join(' ');
  }

  return '';
}

function summarizeToolInput(toolName: string, input: unknown): string {
  if (!input || typeof input !== 'object') return '';
  if (toolName === 'get_canvas_state') {
    const include = (input as any).include;
    if (Array.isArray(include)) return `include=[${include.filter((x: unknown) => typeof x === 'string').join(', ')}]`;
  }
  if (toolName === 'eval_expression') {
    const expression = (input as any).expression;
    if (typeof expression === 'string' && expression.trim()) return `expression="${expression.trim()}"`;
  }
  if (toolName === 'exec_geogebra_commands') {
    const commands = (input as any).commands;
    if (Array.isArray(commands)) return `commands=${commands.length}`;
  }
  if (toolName === 'delete_objects') {
    const objects = (input as any).objects;
    if (Array.isArray(objects)) return `objects=${objects.length}`;
  }
  return '';
}

function extractRunStart(events: RunStreamEvent[]): Extract<RunStreamEvent, { event: 'run_start' }> | null {
  for (const ev of events) {
    if (ev.event === 'run_start') return ev;
  }
  return null;
}

function extractLatestExecCommands(events: RunStreamEvent[]): string[] | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i];
    if (ev.event !== 'tool_start') continue;
    if (ev.data.tool_name !== 'exec_geogebra_commands') continue;
    const input = ev.data.input as any;
    const commands = input?.commands;
    if (!Array.isArray(commands)) continue;
    return commands.filter((c: unknown) => typeof c === 'string' && c.trim().length > 0);
  }
  return null;
}

async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback: no-op (still better than throwing inside UI).
  }
}

function renderTimeline(events: RunStreamEvent[]): string[] {
  const lines: string[] = [];
  for (const ev of events) {
    if (ev.event === 'run_start') {
      const pv = ev.data.protocol_version;
      const llmEnabled = ev.data.llm_enabled;
      const llmModel = ev.data.llm_model ?? undefined;
      const llmText =
        llmEnabled === false ? ' llm=disabled' : typeof llmModel === 'string' && llmModel ? ` llm=${llmModel}` : '';
      lines.push(`run_start${pv ? ` protocol=${pv}` : ''}${llmText} run_id=${shortId(ev.data.run_id)} (${ev.data.run_id})`);
      continue;
    }
    if (ev.event === 'budget') {
      const parts: string[] = [];
      if (typeof ev.data.tool_calls_used === 'number' && typeof ev.data.tool_calls_limit === 'number') {
        parts.push(`tool_calls=${ev.data.tool_calls_used}/${ev.data.tool_calls_limit}`);
      }
      if (typeof ev.data.model_calls_used === 'number' && typeof ev.data.model_calls_limit === 'number') {
        parts.push(`model_calls=${ev.data.model_calls_used}/${ev.data.model_calls_limit}`);
      }
      if (parts.length) lines.push(`budget ${parts.join(' ')}`);
      continue;
    }
    if (ev.event === 'node_start') {
      lines.push(`node_start ${ev.data.name}`);
      continue;
    }
    if (ev.event === 'plan_update') {
      const plan = ev.data.plan;
      const done = plan.filter((p) => p.done).length;
      lines.push(`plan ${done}/${plan.length}`);
      continue;
    }
    if (ev.event === 'tool_start') {
      const inputText = summarizeToolInput(ev.data.tool_name, ev.data.input);
      lines.push(
        `tool_use ${ev.data.tool_name}#${shortId(ev.data.tool_call_id)}${inputText ? ` (${inputText})` : ''}`,
      );
      if (ev.data.tool_name === 'exec_geogebra_commands') {
        const input = ev.data.input as any;
        const commands: unknown = input?.commands;
        if (Array.isArray(commands)) {
          const clean = commands.filter((c: unknown) => typeof c === 'string' && c.trim().length > 0);
          const show = clean.slice(0, 8);
          for (let i = 0; i < show.length; i += 1) {
            lines.push(`  ${i + 1}. ${show[i]}`);
          }
          if (clean.length > show.length) {
            lines.push(`  … (+${clean.length - show.length} more)`);
          }
        }
      }
      continue;
    }
    if (ev.event === 'interrupt') {
      lines.push(`interrupt ${ev.data.tool_name}#${shortId(ev.data.tool_call_id)}`);
      continue;
    }
    if (ev.event === 'tool_end') {
      const tail = ev.data.ok ? summarizeToolOutput(ev.data.tool_name, ev.data.output) : 'error';
      lines.push(`tool_result ${ev.data.tool_name}#${shortId(ev.data.tool_call_id)} ok=${ev.data.ok}${tail ? ` (${tail})` : ''}`);
      continue;
    }
    if (ev.event === 'client_error') {
      const prefix =
        ev.data.status === 0
          ? `client_error at=${ev.data.at}`
          : `client_error at=${ev.data.at} HTTP ${ev.data.status} ${ev.data.statusText}`;

      const detail = ev.data.detail;
      const expected = typeof detail === 'object' && detail !== null ? (detail as any).expected : null;
      const got = typeof detail === 'object' && detail !== null ? (detail as any).got : null;
      if (expected?.tool_call_id && expected?.tool_name && got?.tool_call_id && got?.tool_name) {
        lines.push(
          `${prefix} (expected ${expected.tool_name}#${shortId(expected.tool_call_id)} got ${got.tool_name}#${shortId(got.tool_call_id)})`,
        );
      } else if (typeof detail === 'string' && detail) {
        lines.push(`${prefix} (${detail})`);
      } else {
        lines.push(prefix);
      }
      continue;
    }
    if (ev.event === 'final') {
      lines.push('final');
      continue;
    }
    if (ev.event === 'run_end') {
      lines.push('run_end');
      continue;
    }
  }
  return lines;
}

async function createThreadId(): Promise<string> {
  const res = await fetch('/api/threads', { method: 'POST' });
  if (!res.ok) throw new Error(`create_thread failed: HTTP ${res.status}`);
  const json = (await res.json()) as { thread_id: string };
  return json.thread_id;
}

export default function App() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [ggbApi, setGgbApi] = useState<GeoGebraAppletApi | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const [protocolVersion, setProtocolVersion] = useState<string | null>(null);
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [llmModel, setLlmModel] = useState<string | null>(null);
  const [schemaV2, setSchemaV2] = useState<unknown | null>(null);
  const [schemaBusy, setSchemaBusy] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const meta = useMemo(() => {
    const llmText =
      llmEnabled === false
        ? 'disabled'
        : llmEnabled === true
          ? llmModel
            ? llmModel
            : 'enabled'
          : '(unknown)';

    return `API: /api (proxy→3002) · protocol: ${protocolVersion ?? '(unknown)'} · llm: ${llmText} · thread_id: ${threadId ?? '(none)'}`;
  }, [protocolVersion, threadId, llmEnabled, llmModel]);

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  async function startNewThread() {
    if (busy) return;
    const newId = await createThreadId();
    setThreadId(newId);
    setMessages([]);
    setInput('');
    setProtocolVersion(null);
    setLlmEnabled(null);
    setLlmModel(null);
  }

  function clearChat() {
    if (busy) return;
    setMessages([]);
  }

  function clearCanvas() {
    if (!ggbApi) return;
    const names = ggbApi.getAllObjectNames();
    let deleted = 0;
    for (const name of names) {
      if (ggbApi.deleteObject(name)) deleted += 1;
    }

    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      {
        id: assistantId,
        role: 'assistant',
        status: 'done',
        text: `（本地操作）已尝试删除 ${names.length} 个对象，成功 ${deleted} 个。`,
        events: [],
      },
    ]);
  }

  async function send() {
    const userText = input.trim();
    if (!userText || busy) return;
    if (!ggbApi) return;
    setInput('');

    const userId = crypto.randomUUID();
    setMessages((prev) => [...prev, { id: userId, role: 'user', text: userText }]);

    setBusy(true);
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', text: '', events: [], status: 'running' },
    ]);

    try {
      const effectiveThreadId = threadId ?? (await createThreadId());
      if (!threadId) setThreadId(effectiveThreadId);

      let runId: string | null = null;
      const toolResultCache = new Map<string, Awaited<ReturnType<typeof runFrontendTool>>>();

      function appendEvent(ev: RunStreamEvent) {
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId || m.role !== 'assistant') return m;
            const nextEvents = [...m.events, ev];
            if (ev.event === 'token') {
              return { ...m, events: nextEvents, text: m.text + ev.data.text_delta };
            }
            if (ev.event === 'final') {
              return { ...m, events: nextEvents, text: ev.data.answer.explanation };
            }
            if (ev.event === 'run_end') {
              return { ...m, events: nextEvents, status: 'done' };
            }
            return { ...m, events: nextEvents };
          }),
        );
      }

      async function consume(res: Response, at: 'runs_stream' | 'resume'): Promise<FrontendToolInterrupt | null> {
        if (!res.ok) {
          const body = await res.text().catch(() => '');
          let detail: unknown = undefined;
          try {
            const parsed = JSON.parse(body) as unknown;
            if (parsed && typeof parsed === 'object' && 'detail' in (parsed as any)) detail = (parsed as any).detail;
          } catch {
            // Ignore JSON parse failure.
          }
          appendEvent({
            event: 'client_error',
            data: {
              at,
              status: res.status,
              statusText: res.statusText,
              detail,
              body: body.slice(0, 4000),
            },
          });
          throw new Error(`HTTP ${res.status} ${res.statusText}`);
        }

        let pendingInterrupt: FrontendToolInterrupt | null = null;
        try {
          for await (const ev of streamSse(res)) {
            if (ev.event === 'run_start') {
              runId = ev.data.run_id;
              if (typeof ev.data.protocol_version === 'string' && ev.data.protocol_version) {
                setProtocolVersion(ev.data.protocol_version);
              }
              if (typeof ev.data.llm_enabled === 'boolean') {
                setLlmEnabled(ev.data.llm_enabled);
              }
              if (typeof ev.data.llm_model === 'string') {
                setLlmModel(ev.data.llm_model);
              } else if (ev.data.llm_model === null) {
                setLlmModel(null);
              }
            }
            if (ev.event === 'interrupt') pendingInterrupt = ev;
            appendEvent(ev);
          }
        } catch (e) {
          const message = e instanceof Error ? e.message : String(e);
          appendEvent({ event: 'client_error', data: { at: 'sse', status: 0, statusText: message } });
          throw e;
        }
        return pendingInterrupt;
      }

      let pendingInterrupt = await consume(
        await fetch(`/api/threads/${effectiveThreadId}/runs/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            input: { user_text: userText },
            ui_context: { locale: 'zh-CN', debug: true, plan_mode: false },
          }),
        }),
        'runs_stream',
      );

      while (pendingInterrupt) {
        if (!runId) throw new Error('Missing run_id before interrupt');

        const cacheKey = pendingInterrupt.data.tool_call_id;
        let toolResult = toolResultCache.get(cacheKey);
        if (!toolResult) {
          toolResult = await runFrontendTool({
            toolName: pendingInterrupt.data.tool_name,
            input: pendingInterrupt.data.input,
            ggbApi,
          });
          toolResultCache.set(cacheKey, toolResult);
        }

        const resumePayload = {
          tool_name: pendingInterrupt.data.tool_name,
          tool_call_id: pendingInterrupt.data.tool_call_id,
          ok: toolResult.ok,
          output: toolResult.ok ? toolResult.output : null,
          error: toolResult.ok ? undefined : toolResult.error,
        };
        pendingInterrupt = await consume(
          await fetch(`/api/threads/${effectiveThreadId}/runs/${runId}/resume`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: { resume: resumePayload } }),
          }),
          'resume',
        );
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== assistantId || m.role !== 'assistant') return m;
          return { ...m, status: 'error', error: message };
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <div className="header">
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>GeoGebra AI Drawer (v2)</div>
          <div className="meta">{meta}</div>
        </div>
        <div className="headerActions">
          <button className="secondary" onClick={() => void startNewThread()} disabled={busy}>
            New thread
          </button>
          <button className="secondary" onClick={clearChat} disabled={busy}>
            Clear chat
          </button>
          <button className="secondary" onClick={clearCanvas} disabled={!ggbApi || busy}>
            Clear canvas
          </button>
        </div>
      </div>

      <div className="workspace">
        <div className="canvasPane">
          <div className="paneHeader">
            <div style={{ fontWeight: 700 }}>Canvas</div>
            <div className="meta">{ggbApi ? 'ggbApplet: ready' : 'ggbApplet: loading…'}</div>
          </div>
          <GeoGebraApplet className="canvasBody" onAppletReady={setGgbApi} />
        </div>

        <div className="chatPane">
          <div className="paneHeader">
            <div style={{ fontWeight: 700 }}>Chat</div>
            <div className="meta">Interrupt/resume via SSE</div>
          </div>

          <div className="panel">
            <details>
              <summary>Schema</summary>
              <div className="composer" style={{ marginTop: 8 }}>
                <button
                  className="secondary"
                  onClick={async () => {
                    setSchemaBusy(true);
                    setSchemaError(null);
                    try {
                      const res = await fetch('/api/schema/v2', { method: 'GET' });
                      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
                      const json = (await res.json()) as unknown;
                      setSchemaV2(json);
                    } catch (e) {
                      const message = e instanceof Error ? e.message : String(e);
                      setSchemaError(message);
                    } finally {
                      setSchemaBusy(false);
                    }
                  }}
                  disabled={schemaBusy}
                >
                  Fetch /api/schema/v2
                </button>
                <div className="meta">
                  {schemaBusy ? 'loading…' : schemaError ? `ERROR: ${schemaError}` : schemaV2 ? 'loaded' : 'not loaded'}
                </div>
              </div>
              {schemaV2 ? <pre>{JSON.stringify(schemaV2, null, 2)}</pre> : null}
            </details>

            <CanvasInspector ggbApi={ggbApi} />

            <div className="messages" ref={messagesRef}>
              {messages.map((m) => {
                if (m.role === 'user') {
                  return (
                    <div key={m.id} className="bubble user">
                      {m.text}
                    </div>
                  );
                }
                return (
                  <div key={m.id} className="bubble assistant">
                    {m.text || (m.status === 'running' ? 'thinking…' : '')}
                    {m.status === 'error' ? `\n\nERROR: ${m.error}` : null}
                    {m.events.length ? (
                      <div className="meta" style={{ marginTop: 8 }}>
                        {(() => {
                          const runStart = extractRunStart(m.events);
                          if (!runStart) return null;
                          const runId = runStart.data.run_id;
                          const thread = runStart.data.thread_id;
                          const execCommands = extractLatestExecCommands(m.events);
                          return (
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                              <span>
                                run_id: <code>{runId}</code>
                              </span>
                              <button className="secondary" onClick={() => void copyToClipboard(runId)}>
                                Copy run_id
                              </button>
                              <span>
                                thread_id: <code>{thread}</code>
                              </span>
                              <button className="secondary" onClick={() => void copyToClipboard(thread)}>
                                Copy thread_id
                              </button>
                              <button
                                className="secondary"
                                onClick={() =>
                                  void copyToClipboard(
                                    JSON.stringify({ run_id: runId, thread_id: thread, events: m.events }, null, 2),
                                  )
                                }
                              >
                                Copy debug JSON
                              </button>
                              {execCommands?.length ? (
                                <button className="secondary" onClick={() => void copyToClipboard(execCommands.join('\n'))}>
                                  Copy draw commands
                                </button>
                              ) : null}
                            </div>
                          );
                        })()}
                      </div>
                    ) : null}
                    {m.events.length ? (
                      <div className="timeline">
                        <div className="timelineHeader">Timeline</div>
                        <pre className="timelinePre">{renderTimeline(m.events).join('\n')}</pre>
                      </div>
                    ) : null}
                    <details>
                      <summary>Debug events ({m.events.length})</summary>
                      <pre>{JSON.stringify(m.events, null, 2)}</pre>
                    </details>
                  </div>
                );
              })}
            </div>

            <div className="composer">
              <textarea
                value={input}
                placeholder={ggbApi ? '输入一句话（v2 stub）' : '等待画板加载完成…'}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (ggbApi) void send();
                  }
                }}
              />
              <button onClick={() => void send()} disabled={!ggbApi || busy || !input.trim()}>
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
