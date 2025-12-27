
import React, { useState, useRef, useEffect } from 'react';
import { EndpointStatus, Message } from '../types';

interface ChatInterfaceProps {
  messages: Message[];
  onSendMessage: (text: string) => void;
  isLoading: boolean;
  endpointId: string; // 'auto' or a specific endpoint id
  onEndpointChange: (id: string) => void;
  endpoints: EndpointStatus[];
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({
  messages,
  onSendMessage,
  isLoading,
  endpointId,
  onEndpointChange,
  endpoints
}) => {
  const [input, setInput] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const [copyToast, setCopyToast] = useState<{ key: string; status: 'ok' | 'fail' } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const adjustTextareaHeight = () => {
    const el = inputRef.current;
    if (!el) return;
    // Auto-grow up to a reasonable height to keep the chat layout stable.
    el.style.height = '0px';
    const next = Math.min(el.scrollHeight, 160);
    el.style.height = `${next}px`;
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // 当加载结束时，自动将焦点还给输入框，防止 GeoGebra 干扰
  useEffect(() => {
    if (!isLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading]);

  useEffect(() => {
    adjustTextareaHeight();
  }, [input, isLoading]);

  const send = () => {
    // Prefer reading from the DOM input to avoid React state timing/composition edge cases.
    const raw = inputRef.current?.value ?? input;
    const text = raw.trim();
    if (!text || isLoading || isComposing) return;
    onSendMessage(text);
    setInput('');
    // 发送后立即锁定焦点
    setTimeout(() => inputRef.current?.focus(), 10);
  };

  const copyCommands = async (messageKey: string, commands: string[]) => {
    const text = (Array.isArray(commands) ? commands : []).join('\n').trim();
    if (!text) return;
    let ok = false;
    try {
      await navigator.clipboard?.writeText(text);
      ok = true;
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand('copy') === true;
        document.body.removeChild(ta);
      } catch {
        // ignore
      }
    }

    setCopyToast({ key: messageKey, status: ok ? 'ok' : 'fail' });
    window.setTimeout(() => setCopyToast(null), 900);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    send();
  };

  return (
    <div className="flex flex-col h-full bg-white border-r border-gray-200 shadow-sm w-full md:w-96">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-indigo-600 text-white shrink-0">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          GeoGebra AI
        </h2>
        <div className="flex items-center gap-3">
          <select
            value={endpointId}
            disabled={isLoading}
            onChange={(e) => onEndpointChange(e.target.value)}
            className="text-xs bg-white/10 text-white border border-white/20 rounded-lg px-2 py-1 outline-none focus:ring-2 focus:ring-white/30"
            title="选择模型（Auto 会在失败时自动切换）"
          >
            <option value="auto">Auto（自动降级）</option>
            {endpoints.map((p) => (
              <option key={p.id} value={p.id} disabled={!p.enabled}>
                {p.label}{p.enabled ? "" : "（未配置）"}
              </option>
            ))}
          </select>

        {isLoading && (
          <div className="flex space-x-1">
            <div className="w-1.5 h-1.5 bg-white/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-1.5 h-1.5 bg-white/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-1.5 h-1.5 bg-white/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
          </div>
        )}
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50/30">
        {messages.length === 0 && (
          <div className="text-center text-slate-400 mt-10 space-y-3 px-4">
            <div className="w-12 h-12 bg-indigo-50 text-indigo-400 rounded-full flex items-center justify-center mx-auto mb-2">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            </div>
            <p className="font-bold text-slate-600">您好！我是数学智能助手</p>
            <p className="text-xs leading-relaxed">您可以尝试说：<br/>"画一个圆心在 (0,0) 半径为 5 的圆"<br/>"绘制函数 y = sin(x) * x"</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[88%] rounded-2xl p-3 shadow-sm ${
              msg.role === 'user' 
                ? 'bg-indigo-600 text-white rounded-tr-none' 
                : 'bg-white text-slate-800 border border-slate-200 rounded-tl-none'
            }`}>
              <div className="text-sm leading-relaxed whitespace-pre-wrap break-words">{msg.content}</div>
              {msg.role !== 'user' && msg.meta?.runRecord && (
                <details className="mt-2 pt-2 border-t border-slate-100">
                  <summary className="cursor-pointer select-none text-xs text-slate-500 font-semibold flex items-center justify-between gap-2">
                    <span>
                      运行记录（{Array.isArray(msg.meta.runRecord?.attempts) ? msg.meta.runRecord.attempts.length : 0}）
                    </span>
                    <span className="text-[10px] text-slate-400">默认收起 · 点击展开</span>
                  </summary>
                  <div className="mt-2 text-[11px] leading-relaxed text-slate-700 space-y-2">
                    <div className="text-[10px] text-slate-500">
                      runId: <span className="font-mono">{String(msg.meta.runRecord?.runId || '')}</span>
                    </div>
                    <div className="text-[10px] text-slate-500">
                      retries: <span className="font-mono">{String(msg.meta.runRecord?.retries ?? '')}</span>
                    </div>
                    <pre className="text-[11px] leading-relaxed font-mono bg-slate-50 text-slate-700 rounded-lg p-3 border border-slate-200 overflow-x-auto whitespace-pre">
                      {JSON.stringify(msg.meta.runRecord, null, 2)}
                    </pre>
                  </div>
                </details>
              )}
              {msg.commands && msg.commands.length > 0 && (
                <details className="mt-2 pt-2 border-t border-slate-100">
                  <summary className="cursor-pointer select-none text-xs text-slate-500 font-semibold flex items-center justify-between gap-2">
                    <span>绘图步骤（{msg.commands.length}）</span>
                    <span className="text-[10px] text-slate-400">默认收起 · 点击展开</span>
                  </summary>
                  <div className="mt-2">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => copyCommands(`${msg.timestamp}-${i}`, msg.commands || [])}
                        className="text-[10px] font-bold text-slate-500 hover:text-indigo-600 tracking-widest px-2 py-1 rounded-md border border-slate-200 bg-white shadow-sm"
                        title="复制绘图命令"
                      >
                        {copyToast?.key === `${msg.timestamp}-${i}`
                          ? (copyToast.status === 'ok' ? '已复制' : '复制失败')
                          : '复制'}
                      </button>
                    </div>
                    <pre className="mt-2 text-[11px] leading-relaxed font-mono bg-slate-50 text-slate-700 rounded-lg p-3 border border-slate-200 overflow-x-auto whitespace-pre">
                      {(msg.commands || []).join('\n')}
                    </pre>
                  </div>
                </details>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="max-w-[88%] rounded-2xl p-3 shadow-sm bg-white text-slate-800 border border-slate-200 rounded-tl-none">
              <div className="text-sm leading-relaxed whitespace-pre-wrap break-words flex items-center gap-2">
                <span className="font-mono text-slate-500">thinking...</span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                  <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                  <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="p-4 border-t border-slate-100 bg-white shrink-0">
        <div className="relative group">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              adjustTextareaHeight();
            }}
            disabled={isLoading}
            autoFocus
            rows={1}
            placeholder={isLoading ? "AI 正在思考并绘图中..." : "输入绘图指令..."}
            className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all outline-none text-sm placeholder:text-slate-400 resize-none leading-relaxed"
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                // Make Enter reliably send even if focus is weird.
                e.preventDefault();
                send();
              }
            }}
          />
          <button
            type="button"
            aria-label="发送"
            onClick={(e) => {
              e.preventDefault();
              send();
            }}
            // Don't disable based on React state text length; some input methods / automation can lag behind state.
            // send() validates the DOM value anyway.
            disabled={isLoading}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-indigo-600 disabled:text-slate-300 hover:bg-indigo-50 rounded-lg transition-colors"
          >
            {isLoading ? (
               <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ChatInterface;
