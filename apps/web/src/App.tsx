import { useEffect, useRef, useState } from 'react';
import { GeoGebraApplet } from './GeoGebraApplet';
import { runFrontendTool } from './frontendTools';
import { RunStreamEvent, streamSse } from './sse';
import { ChatMessage } from './types';
import { ChatBubble } from './components/ChatBubble';
import { DebugDrawer } from './components/DebugDrawer';
import { WelcomeScreen } from './components/WelcomeScreen';

type FrontendToolInterrupt = Extract<RunStreamEvent, { event: 'interrupt' }>;

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  // Dev Mode & State
  const [devMode, setDevMode] = useState(false);
  const [debugDrawerOpen, setDebugDrawerOpen] = useState(false);

  const forceHardMode = (() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const raw = params.get('forceHardMode') ?? params.get('force_hard_mode') ?? params.get('force_hard');
      if (!raw) return false;
      const v = raw.trim().toLowerCase();
      return v === '1' || v === 'true' || v === 'yes' || v === 'y' || v === 'on';
    } catch {
      return false;
    }
  })();

  // Auto-scroll
  const lastAssistantStatus = (() => {
    const last = messages.length ? messages[messages.length - 1] : null;
    return last && last.role === 'assistant' ? last.status : null;
  })();

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, lastAssistantStatus]); // Also scroll on status change

  // Focus input on load and after busy
  useEffect(() => {
    if (!busy && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [busy]);

  async function startNewThread() {
    if (busy) return;
    const newId = await createThreadId();
    setThreadId(newId);
    setMessages([]);
    setInput('');
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

  // Handle hitting Enter in textarea
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const textarea = e.currentTarget as HTMLTextAreaElement;
      const text = textarea.value.trim();
      console.log('[handleKeyDown] Enter pressed, textarea.value=' + text);
      if (text) {
        void send(text);
      }
    }
  };

  async function send(textOverride?: string, intentHint?: Record<string, unknown>) {
    const userText = (textOverride ?? input).trim();
    console.log('[send] called:', 'textOverride=' + (textOverride || '(undefined)'), 'input=' + input, 'userText=' + userText);
    if (!userText) {
      console.log('[send] blocked: empty text');
      return;
    }
    if (busy) {
      console.log('[send] blocked: busy');
      return;
    }
    if (!ggbApi) {
      console.warn('[send] blocked: ggbApi not ready yet');
      return;
    }
    console.log('[send] sending:', userText);
    
    setInput('');
    // Reset textarea height if we had auto-grow logic (not strictly needed with fixed styles but good practice)
    
    const userId = crypto.randomUUID();
    setMessages((prev) => [...prev, { id: userId, role: 'user', text: userText }]);

    setBusy(true);
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', text: '', events: [], status: 'running' },
    ]);

    try {
      // In dev, the API server can hot-reload and lose in-memory threads, which causes 404s.
      // Recover by creating a new thread and retrying once.
      let effectiveThreadId = threadId ?? (await createThreadId());
      if (!threadId) setThreadId(effectiveThreadId);

      let runId: string | null = null;
      const toolResultCache = new Map<string, Awaited<ReturnType<typeof runFrontendTool>>>();

      function appendEvent(ev: RunStreamEvent) {
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId || m.role !== 'assistant') return m;
            const nextEvents = [...m.events, ev];
            if (ev.event === 'final') {
              return { ...m, events: nextEvents, text: ev.data.answer.explanation };
            }
            if (ev.event === 'run_end') {
              return { ...m, events: nextEvents, status: 'done' };
            }
            if (ev.event === 'client_error') {
              return { ...m, events: nextEvents, status: 'error', error: `HTTP ${ev.data.status}` };
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
          const errorMsg = `HTTP ${res.status} ${res.statusText}`;
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
           // Also update the message text to show error
           setMessages(prev => prev.map(m => {
             if (m.id === assistantId) return { ...m, status: 'error', error: errorMsg };
             return m;
           }));
          throw new Error(errorMsg);
        }

        let pendingInterrupt: FrontendToolInterrupt | null = null;
        try {
          for await (const ev of streamSse(res)) {
            if (ev.event === 'run_start') {
              runId = ev.data.run_id;
              console.log('[consume] run_start, runId=', runId);
            }
            if (ev.event === 'interrupt') {
              pendingInterrupt = ev;
              console.log('[consume] interrupt received:', ev.data);
            }
            appendEvent(ev);
          }
        } catch (e) {
          const message = e instanceof Error ? e.message : String(e);
          console.error('[consume] error:', message);
          appendEvent({ event: 'client_error', data: { at: 'sse', status: 0, statusText: message } });
          throw e;
        }
        console.log('[consume] done, pendingInterrupt=', pendingInterrupt ? 'yes' : 'no');
        return pendingInterrupt;
      }

      const makeRunsStreamRequest = (tid: string) =>
        fetch(`/api/threads/${tid}/runs/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            input: { user_text: userText },
            ui_context: {
              locale: 'zh-CN',
              debug: devMode,
              plan_mode: devMode, // Plan is for developer timeline
              intent_hint: (() => {
                const hinted = intentHint ?? null;
                if (!forceHardMode) return hinted;
                const obj: Record<string, unknown> = hinted && typeof hinted === 'object' ? { ...(hinted as any) } : {};
                if (obj.difficulty == null) obj.difficulty = 'hard';
                // NOTE: any intent_hint bypasses strict intent classification on the server,
                // so we must also set wants_draw to keep draw flows working in dev/acceptance.
                if (obj.wants_draw == null) obj.wants_draw = true;
                return obj;
              })(),
            },
          }),
        });

      let res = await makeRunsStreamRequest(effectiveThreadId);
      if (res.status === 404) {
        console.warn('[send] thread not found (404), creating a new thread and retrying once');
        effectiveThreadId = await createThreadId();
        setThreadId(effectiveThreadId);
        res = await makeRunsStreamRequest(effectiveThreadId);
      }

      let pendingInterrupt = await consume(res, 'runs_stream');

      while (pendingInterrupt) {
        console.log('[send] processing interrupt:', pendingInterrupt.data);
        if (!runId) throw new Error('Missing run_id before interrupt');

        const cacheKey = pendingInterrupt.data.tool_call_id;
        let toolResult = toolResultCache.get(cacheKey);
        if (!toolResult) {
          console.log('[send] executing tool:', pendingInterrupt.data.tool_name);
          toolResult = await runFrontendTool({
            toolName: pendingInterrupt.data.tool_name,
            input: pendingInterrupt.data.input,
            ggbApi,
          });
          console.log('[send] tool result:', toolResult.ok ? 'ok' : 'error');
          toolResultCache.set(cacheKey, toolResult);
        } else {
          console.log('[send] using cached tool result');
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
        <div className="headerTitle">
          <svg className="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          GeoGebra AI
        </div>
        <div className="headerActions">
          <button className="secondary" data-testid="new-thread" onClick={() => void startNewThread()} disabled={busy} title="New Thread">
            New
          </button>
          <button className="secondary" data-testid="clear-canvas" onClick={clearCanvas} disabled={!ggbApi || busy} title="Clear Canvas">
             Clear
          </button>
          
          <div style={{ width: 1, height: 24, background: 'var(--border-color)', margin: '0 4px' }}></div>
          
          <button 
            className={`secondary ${devMode ? 'active' : ''}`} 
            data-testid="dev-toggle"
            onClick={() => {
              setDevMode(!devMode);
              // Don't auto-open drawer, let user control it separately
            }}
            title={devMode ? "Exit Developer Mode" : "Enter Developer Mode"}
          >
            {devMode ? 'Dev: ON' : 'Dev'}
          </button>
          
          {devMode && (
             <button 
               className="secondary" 
               data-testid="tools-toggle"
               onClick={() => setDebugDrawerOpen(!debugDrawerOpen)}
               title={debugDrawerOpen ? "Hide Tools" : "Show Tools"}
             >
               {debugDrawerOpen ? 'Tools: ON' : 'Tools'}
             </button>
          )}
        </div>
      </div>

      <div className="workspace">
        <div className="canvasPane">
          <GeoGebraApplet className="canvasBody" onAppletReady={setGgbApi} />
        </div>

        <div className="chatPane">
          <div className="messages" ref={messagesRef}>
            {messages.length === 0 ? (
              <WelcomeScreen onSuggestionClick={(text, hint) => send(text, hint)} />
            ) : (
              messages.map((m) => (
                <ChatBubble 
                  key={m.id} 
                  message={m} 
                  devMode={devMode}
                />
              ))
            )}
          </div>

          <div className="composer-area">
             <form 
               className="input-wrapper"
               onSubmit={(e) => {
                 e.preventDefault();
                 const textarea = textareaRef.current;
                 const text = textarea ? textarea.value.trim() : input.trim();
                 console.log('[form onSubmit]', { textarea: !!textarea, textareaValue: textarea?.value, input, text });
                 if (text) {
                   void send(text);
                 }
               }}
             >
               <textarea
                 ref={textareaRef}
                 className="chat-input"
                 data-testid="chat-input"
                 value={input}
                 placeholder={ggbApi ? '描述你想画的图形...' : '等待画板加载...'}
                 onChange={(e) => setInput(e.target.value)}
                // Some IME/composition paths can fail to update React state promptly via onChange.
                // Keep state in sync so the send button becomes enabled as the user types.
                onInput={(e) => setInput((e.target as HTMLTextAreaElement).value)}
                onCompositionEnd={(e) => setInput(e.currentTarget.value)}
                 onKeyDown={handleKeyDown}
                 rows={1}
               />
               <button 
                 type="submit"
                 className="send-btn" 
                 data-testid="send-button"
                 disabled={!ggbApi || busy || !input.trim()}
               >
                 <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                 </svg>
               </button>
             </form>
          </div>
        </div>

        {/* Debug Drawer Layer */}
        {devMode && (
          <DebugDrawer 
            isOpen={debugDrawerOpen} 
            onClose={() => setDebugDrawerOpen(false)}
            ggbApi={ggbApi}
          />
        )}
      </div>
    </div>
  );
}
