import { useState, useMemo } from 'react';
import { ChatMessage } from '../types';
import { RunStreamEvent } from '../sse';

interface ChatBubbleProps {
  message: ChatMessage;
  devMode: boolean;
}

function shortId(id: string): string {
  return id.length <= 8 ? id : id.slice(0, 8);
}

function extractRunInfo(events: RunStreamEvent[]) {
  const runStart = events.find(e => e.event === 'run_start') as Extract<RunStreamEvent, { event: 'run_start' }> | undefined;
  if (!runStart) return null;
  return {
    runId: runStart.data.run_id,
    threadId: runStart.data.thread_id,
  };
}

export function ChatBubble({ message, devMode }: ChatBubbleProps) {
  const isUser = message.role === 'user';
  const [showTrace, setShowTrace] = useState(false);
  const events = message.role === 'assistant' ? message.events : null;

  // Extract useful info for trace summary
  const toolUsage = useMemo(() => {
    if (!events || events.length === 0) return null;
    const tools = events
      .filter(e => e.event === 'tool_start')
      .map(e => (e as any).data.tool_name);
    return tools.length > 0 ? `Tools: ${tools.join(', ')}` : null;
  }, [events]);

  // NOTE: we intentionally do NOT render token streams in the UI right now.
  // Use server-side logs (logs/v2/run-*.jsonl) for debugging raw provider deltas.

  if (isUser) {
    return (
      <div className="bubble-row user">
        <div className="bubble user">
          <div className="content">
            {message.text}
          </div>
        </div>
      </div>
    );
  }

  // Assistant Logic
  const isThinking = message.status === 'running';
  const hasError = message.status === 'error';
  const runInfo = events && events.length > 0 ? extractRunInfo(events) : null;

  return (
    <div className="bubble-row assistant">
      <div className="bubble assistant">
        {/* Dev Mode Trace Info (Folded by default) - Always show if devMode is on, even if events is empty */}
        {devMode && (
          <div className="trace-details">
            <div
              className="trace-summary"
              data-testid="trace-summary"
              onClick={() => setShowTrace(!showTrace)}
              style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#64748b' }}
            >
              <span style={{ fontSize: 9 }}>{showTrace ? '▼' : '▶'}</span>
              <span>
                <strong>Run:</strong> {runInfo ? shortId(runInfo.runId) : '...'} 
                {toolUsage ? ` · ${toolUsage}` : events && events.length > 0 ? ` · ${events.length} events` : ' · No events'}
              </span>
            </div>

            {showTrace && (
              <div
                className="trace-log"
                data-testid="trace-log"
                style={{ marginTop: 8, padding: 8, background: '#f8fafc', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 11, overflowX: 'auto' }}
              >
                {!events || events.length === 0 ? (
                  <div style={{ color: '#64748b', fontStyle: 'italic' }}>No events recorded for this message.</div>
                ) : (
                  <>
                    {runInfo && (
                      <div style={{ marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid #e2e8f0' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 12px', alignItems: 'center' }}>
                          <strong style={{ color: '#475569' }}>Run ID:</strong> 
                          <code style={{ userSelect: 'all' }}>{runInfo.runId}</code>
                          
                          <strong style={{ color: '#475569' }}>Thread ID:</strong> 
                          <code style={{ userSelect: 'all' }}>{runInfo.threadId}</code>
                        </div>
                        <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                          <button className="secondary" style={{ padding: '2px 6px', fontSize: 10 }} onClick={() => navigator.clipboard.writeText(runInfo.runId)}>Copy Run ID</button>
                          <button className="secondary" style={{ padding: '2px 6px', fontSize: 10 }} onClick={() => navigator.clipboard.writeText(JSON.stringify(events, null, 2))}>Copy Full Log</button>
                        </div>
                      </div>
                    )}
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {events.map((ev, idx) => {
                        // Show token events in dev mode (collapsed by default)
                        if (ev.event === 'token') {
                          const channel = ev.data.channel ?? 'content';
                          const len = ev.data.text_delta?.length ?? 0;
                          return (
                            <details key={idx} style={{ fontSize: 10 }}>
                              <summary style={{ cursor: 'pointer', color: '#64748b' }}>
                                [token:{channel}] len={len}
                              </summary>
                              <div style={{ marginTop: 4, padding: 4, background: '#f8fafc', borderRadius: 4, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                (hidden)
                              </div>
                            </details>
                          );
                        }
                        return (
                          <div key={idx} style={{ fontFamily: 'monospace', color: '#334155' }}>
                            <span style={{ color: '#94a3b8', marginRight: 6 }}>[{ev.event}]</span>
                            {'tool_name' in ev.data ? (
                              <span style={{ color: '#0f172a', fontWeight: 500 }}>{ev.data.tool_name}</span>
                            ) : 'answer' in ev.data ? (
                              <span style={{ color: '#16a34a' }}>Final Answer</span>
                            ) : null}
                            {'input' in ev.data ? (
                              <span style={{ color: '#64748b', marginLeft: 6 }}>{JSON.stringify((ev.data as any).input).slice(0, 40)}...</span>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}

        <div className="content">
          {/* Show final answer */}
          {message.text ? (
            <div style={{ whiteSpace: 'pre-wrap' }}>{message.text}</div>
          ) : null}
          
          {isThinking && (
            <div className="thinking-dots">
              <div className="dot"></div>
              <div className="dot"></div>
              <div className="dot"></div>
            </div>
          )}

          {hasError && (
            <div style={{ color: '#ef4444', marginTop: 8, fontSize: 13 }}>
              ⚠️ {message.error || 'Unknown error occurred'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
