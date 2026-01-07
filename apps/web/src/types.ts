import { RunStreamEvent } from './sse';

export type ChatMessage =
  | { id: string; role: 'user'; text: string }
  | {
      id: string;
      role: 'assistant';
      text: string;
      events: RunStreamEvent[];
      status: 'running' | 'done' | 'error';
      overlay?: Record<string, unknown> | null;
      error?: string;
    };
