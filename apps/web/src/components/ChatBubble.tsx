import { useState } from 'react';
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
  const runInfo = extractRunInfo(message.events);

  return (
    <div className="bubble-row assistant">
      <div className="bubble assistant">
        <div className="content">
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

        {/* Dev Mode Trace Info */}
        {devMode && message.events.length > 0 && (
          <div className="trace-details">
            <div 
              className="trace-summary" 
              onClick={() => setShowTrace(!showTrace)}
            >
              <span>{showTrace ? '▼' : '▶'}</span>
              <span>
                Trace Info 
                {runInfo ? ` (Run: ${shortId(runInfo.runId)})` : ''} 
                · {message.events.length} events
              </span>
            </div>
            
            {showTrace && (
              <div className="trace-log">
                {runInfo && (
                  <div style={{ marginBottom: 4 }}>
                    <strong>Run ID:</strong> {runInfo.runId}<br/>
                    <strong>Thread ID:</strong> {runInfo.threadId}
                  </div>
                )}
                {/* Simple event summary list */}
                {message.events.map((ev, idx) => (
                  <div key={idx} style={{ marginBottom: 2 }}>
                    <span style={{ color: '#64748b' }}>[{ev.event}]</span> 
                    {'tool_name' in ev.data ? ` ${ev.data.tool_name}` : ''}
                    {'answer' in ev.data ? ` (final answer)` : ''}
                  </div>
                ))}
                <div style={{ marginTop: 8 }}>
                  <button 
                    className="secondary" 
                    style={{ fontSize: 10, padding: '2px 6px' }}
                    onClick={() => navigator.clipboard.writeText(JSON.stringify(message.events, null, 2))}
                  >
                    Copy Full JSON
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

