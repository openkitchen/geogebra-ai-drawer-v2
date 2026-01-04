import type { RunStreamEvent as ProtocolRunStreamEvent } from './schema';

export type ClientErrorEvent = {
  event: 'client_error';
  data: { at: 'runs_stream' | 'resume' | 'sse'; status: number; statusText: string; detail?: unknown; body?: string };
};

export type VerificationEvent = { event: 'verification'; data: { label: string; ok: boolean; details?: unknown } };

export type ReflectionEvent = { event: 'reflection'; data: { summary: string; failure_code?: string; next_step?: string } };

export type ApprovalRequestEvent = {
  event: 'approval_request';
  data: {
    request_id: string;
    kind: 'dangerous_action' | 'tool' | 'write';
    message: string;
    data?: unknown;
  };
};

export type ApprovalResultEvent = { event: 'approval_result'; data: { request_id: string; decision: 'approve' | 'reject' | 'edit'; data?: unknown } };

export type RunStreamEvent =
  | ProtocolRunStreamEvent
  | ClientErrorEvent
  | VerificationEvent
  | ReflectionEvent
  | ApprovalRequestEvent
  | ApprovalResultEvent;

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
