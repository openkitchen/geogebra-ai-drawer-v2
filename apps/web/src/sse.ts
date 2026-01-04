export type RunStreamEvent =
  | {
      event: 'run_start';
      data: {
        run_id: string;
        thread_id: string;
        protocol_version?: string;
        llm_enabled?: boolean;
        llm_model?: string | null;
        llm_base_url?: string | null;
      };
    }
  | { event: 'node_start'; data: { name: string } }
  | { event: 'plan_update'; data: { plan: Array<{ id: string; text: string; done?: boolean }> } }
  | { event: 'token'; data: { text_delta: string; channel?: 'content' | 'reasoning' | 'meta' } }
  | { event: 'tool_start'; data: { tool_name: string; tool_call_id: string; input: unknown } }
  | { event: 'interrupt'; data: { kind: 'frontend_tool'; tool_name: string; tool_call_id: string; input: unknown } }
  | { event: 'tool_end'; data: { tool_name: string; tool_call_id: string; output: unknown; ok: boolean; error?: unknown } }
  | {
      event: 'client_error';
      data: { at: 'runs_stream' | 'resume' | 'sse'; status: number; statusText: string; detail?: unknown; body?: string };
    }
  | { event: 'verification'; data: { label: string; ok: boolean; details?: unknown } }
  | { event: 'reflection'; data: { summary: string; failure_code?: string; next_step?: string } }
  | {
      event: 'approval_request';
      data: {
        request_id: string;
        kind: 'dangerous_action' | 'tool' | 'write';
        message: string;
        data?: unknown;
      };
    }
  | { event: 'approval_result'; data: { request_id: string; decision: 'approve' | 'reject' | 'edit'; data?: unknown } }
  | { event: 'budget'; data: { model_calls_used?: number; model_calls_limit?: number; tool_calls_used?: number; tool_calls_limit?: number } }
  | { event: 'node_end'; data: { name: string } }
  | { event: 'final'; data: { answer: { explanation: string; overlay_text?: unknown } } }
  | { event: 'run_end'; data: {} };

type ParsedSseMessage = { event?: string; data?: string };

function parseSseBlock(block: string): ParsedSseMessage {
  const lines = block.split('\n');
  const dataLines: string[] = [];
  let event: string | undefined;
  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line) continue;
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim();
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart());
      continue;
    }
  }
  return { event, data: dataLines.length ? dataLines.join('\n') : undefined };
}

export async function* streamSse(response: Response): AsyncGenerator<RunStreamEvent> {
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`HTTP ${response.status} ${response.statusText}: ${text}`);
  }
  if (!response.body) throw new Error('Missing response body');

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replaceAll('\r\n', '\n');

    while (true) {
      const sepIndex = buffer.indexOf('\n\n');
      if (sepIndex === -1) break;
      const block = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const msg = parseSseBlock(block);
      if (!msg.event || msg.data == null) continue;
      try {
        const parsed = JSON.parse(msg.data) as unknown;
        const ev = { event: msg.event as RunStreamEvent['event'], data: parsed as any } as RunStreamEvent;
        yield ev;

        // Important: some servers keep the SSE connection open even after `run_end`.
        // If we don't proactively stop, the UI can get stuck in `busy=true`,
        // which disables the send button ("paper plane") forever.
        if (ev.event === 'run_end') {
          try {
            await reader.cancel();
          } catch {
            // Ignore cancel errors.
          }
          return;
        }
      } catch {
        // Ignore non-JSON payloads in v2.
      }
    }
  }
}
