import { tool, zodSchema } from 'ai';
import { z } from 'zod';

// Build tool map for ai-sdk (key -> tool definition)
export function buildTools({ canvasState }) {
  const CornerSchema = z.enum(['top-left', 'top-right', 'bottom-left', 'bottom-right']);

  const getCanvasState = tool({
    description: '获取当前画布摘要（对象名称/坐标/角度等）。',
    inputSchema: zodSchema(z.object({})),
    execute: async () => ({ canvasState: canvasState || '' }),
  });

  const setCornerText = tool({
    description:
      'Set a UI overlay text pinned to a viewport corner (NOT a GeoGebra command). ' +
      'Use this after drawing to show a kid-friendly step summary.',
    inputSchema: zodSchema(z.object({
      corner: CornerSchema,
      text: z.string().max(280),
    })),
    execute: async (input) => input,
  });

  return {
    get_canvas_state: getCanvasState,
    set_corner_text: setCornerText,
  };
}
