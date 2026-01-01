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
      void send();
    }
  };

  async function send(textOverride?: string) {
    const userText = (textOverride ?? input).trim();
    if (!userText || busy) return;
    if (!ggbApi) return;
    
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
      const effectiveThreadId = threadId ?? (await createThreadId());
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
            ui_context: { locale: 'zh-CN', debug: devMode, plan_mode: devMode }, // Plan is for developer timeline
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
        <div className="headerTitle">
          <svg className="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          GeoGebra AI
        </div>
        <div className="headerActions">
          <button className="secondary" onClick={() => void startNewThread()} disabled={busy} title="New Thread">
            New
          </button>
          <button className="secondary" onClick={clearCanvas} disabled={!ggbApi || busy} title="Clear Canvas">
             Clear
          </button>
          
          <div style={{ width: 1, height: 24, background: 'var(--border-color)', margin: '0 4px' }}></div>
          
          <button 
            className={`secondary ${devMode ? 'active' : ''}`} 
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
              <WelcomeScreen onSuggestionClick={(text) => send(text)} />
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
             <div className="input-wrapper">
               <textarea
                 ref={textareaRef}
                 className="chat-input"
                 value={input}
                 placeholder={ggbApi ? '描述你想画的图形...' : '等待画板加载...'}
                 onChange={(e) => setInput(e.target.value)}
                 onKeyDown={handleKeyDown}
                 rows={1}
               />
               <button 
                 className="send-btn" 
                 onClick={() => void send()} 
                 disabled={!ggbApi || busy || !input.trim()}
               >
                 <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                 </svg>
               </button>
             </div>
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
