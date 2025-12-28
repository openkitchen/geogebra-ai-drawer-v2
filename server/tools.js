import { tool, zodSchema } from 'ai';
import { z } from 'zod';

// Build tool map for ai-sdk (key -> tool definition)
export function buildTools() {
  const CornerSchema = z.enum(['top-left', 'top-right', 'bottom-left', 'bottom-right']);

  const getCanvasState = tool({
    description: '获取当前画布摘要（对象名称/坐标/角度等）。',
    inputSchema: zodSchema(z.object({})),
    // NOTE: the real canvas lives in the browser. The server cannot read it directly.
    // This tool call is used as a request signal; the client will execute it and send TOOL_RESULT in a follow-up request.
    execute: async () => ({ requested: true }),
  });

  const setCornerText = tool({
    description:
      'Set a UI overlay text pinned to a viewport corner (NOT a GeoGebra command). ' +
      'Use this after drawing to show a kid-friendly step summary.',
    inputSchema: zodSchema(z.object({
      corner: CornerSchema,
      text: z.string().max(280),
    })),
    // This is a frontend-visible UI action; the client will apply it.
    execute: async (input) => ({ ...input, requested: true }),
  });

  return {
    get_canvas_state: getCanvasState,
    set_corner_text: setCornerText,
  };
}
