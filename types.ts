
export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  commands?: string[];
  // Optional, non-user-facing metadata for UI rendering (e.g., tool usage / retries).
  meta?: Record<string, any>;
  timestamp: number;
}

export interface GGBResponse {
  explanation: string;
  commands: string[];
  overlayText?: OverlayText;
}

export type Corner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
export interface OverlayText {
  corner: Corner;
  text: string;
}

export type ChatRole = 'user' | 'assistant' | 'tool';

export interface ChatMessage {
  role: ChatRole;
  content: string;
  commands?: string[];
  meta?: Record<string, any>;
}

export type EndpointId = string;

export interface EndpointStatus {
  id: EndpointId;
  label: string;
  provider: 'openai' | 'google' | 'openai-compatible';
  enabled: boolean;
  modelId?: string;
}

export interface GeoGebraApplet {
  evalCommand: (cmd: string) => void;
  reset: () => void;
  deleteObject: (obj: string) => void;
  getAllObjectNames: () => string[];
  exists: (obj: string) => boolean; // 新增：用于检查对象是否存在
  
  setPerspective: (perspective: string) => void;
  setCoordSystem: (xmin: number, xmax: number, ymin: number, ymax: number) => void;
  setGridVisible: (visible: boolean) => void;
  setAxesVisible: (xAxis: boolean, yAxis: boolean) => void;
  setAxesRatio: (x: number, y: number) => void;
  setSize: (width: number, height: number) => void;
}

/**
 * Interface representing the global AI Studio helper for API key management.
 * Defined here to match the expected global AIStudio type in the execution context.
 */
export interface AIStudio {
  hasSelectedApiKey: () => Promise<boolean>;
  openSelectKey: () => Promise<void>;
}

declare global {
  interface Window {
    GGBApplet: any;
    ggbApplet: GeoGebraApplet;
    // Fix: Use the explicit AIStudio interface to match environmental declarations and resolve TS errors.
    aistudio: AIStudio;
  }
}
