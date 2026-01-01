import { useState } from 'react';
import { CanvasInspector } from '../CanvasInspector';

interface DebugDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  ggbApi: any; // Using any for simplicity, ideally import GeoGebraAppletApi
}

export function DebugDrawer({ isOpen, onClose, ggbApi }: DebugDrawerProps) {
  const [schemaV2, setSchemaV2] = useState<unknown | null>(null);
  const [schemaBusy, setSchemaBusy] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const [langGraphMermaid, setLangGraphMermaid] = useState<string | null>(null);
  const [langGraphBusy, setLangGraphBusy] = useState(false);
  const [langGraphError, setLangGraphError] = useState<string | null>(null);

  async function fetchSchema() {
    setSchemaBusy(true);
    setSchemaError(null);
    try {
      const res = await fetch('/api/schema/v2', { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
      const json = await res.json();
      setSchemaV2(json);
    } catch (e: any) {
      setSchemaError(e.message || String(e));
    } finally {
      setSchemaBusy(false);
    }
  }

  async function fetchGraph() {
    setLangGraphBusy(true);
    setLangGraphError(null);
    try {
      const res = await fetch('/api/graph/v2/mermaid', { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
      const text = await res.text();
      setLangGraphMermaid(text);
    } catch (e: any) {
      setLangGraphError(e.message || String(e));
    } finally {
      setLangGraphBusy(false);
    }
  }

  const togglePerspective = (code: string) => {
    if (ggbApi && ggbApi.setPerspective) {
      ggbApi.setPerspective(code);
    }
  };

  const toggleOption = (option: 'algebra' | 'spreadsheet') => {
    if (!ggbApi) return;
    // Note: GeoGebra JS API doesn't have direct toggle setters for everything, 
    // but perspective strings are the reliable way. 
    // 'G' = Geometry (no algebra), 'A' = Algebra + Graphics
    // Or we can use `showAlgebraInput(bool)` if exposed, but standard API uses perspectives.
    // For simplicity, let's expose buttons to switch standard perspectives.
  };

  return (
    <div className={`debug-drawer ${!isOpen ? 'closed' : ''}`}>
      <div className="debug-header">
        <span>Developer Tools</span>
        <button className="icon-btn" onClick={onClose}>
          ✕
        </button>
      </div>
      <div className="debug-content">
        
        {/* GeoGebra Controls */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ marginBottom: 8, fontWeight: 600 }}>GeoGebra UI</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="secondary" style={{ fontSize: 11 }} onClick={() => togglePerspective('G')}>
              Geometry (Clean)
            </button>
            <button className="secondary" style={{ fontSize: 11 }} onClick={() => togglePerspective('A')}>
              Algebra (Formulas)
            </button>
            <button className="secondary" style={{ fontSize: 11 }} onClick={() => togglePerspective('S')}>
              Spreadsheet
            </button>
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: '#64748b' }}>
            Use these to inspect internal state or formulas.
          </div>
        </div>

        {/* Canvas Inspector */}
        <div style={{ marginBottom: 24 }}>
          <CanvasInspector ggbApi={ggbApi} />
        </div>

        {/* Schema */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <strong>API Schema</strong>
            <button className="secondary" style={{ fontSize: 10, padding: '4px 8px' }} onClick={fetchSchema} disabled={schemaBusy}>
              {schemaBusy ? 'Loading...' : 'Fetch'}
            </button>
          </div>
          {schemaError && <div style={{ color: 'red', fontSize: 11 }}>{schemaError}</div>}
          {schemaV2 ? <pre style={{ maxHeight: 200, overflow: 'auto' }}>{JSON.stringify(schemaV2, null, 2)}</pre> : null}
        </div>

        {/* LangGraph */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <strong>LangGraph</strong>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="secondary" style={{ fontSize: 10, padding: '4px 8px' }} onClick={fetchGraph} disabled={langGraphBusy}>
                {langGraphBusy ? 'Loading...' : 'Fetch'}
              </button>
              {langGraphMermaid && (
                <button 
                  className="secondary" 
                  style={{ fontSize: 10, padding: '4px 8px' }} 
                  onClick={() => window.open('/api/graph/v2/mermaid.png', '_blank')}
                >
                  PNG
                </button>
              )}
            </div>
          </div>
          {langGraphError && <div style={{ color: 'red', fontSize: 11 }}>{langGraphError}</div>}
          {langGraphMermaid && <pre style={{ maxHeight: 200, overflow: 'auto' }}>{langGraphMermaid}</pre>}
        </div>
      </div>
    </div>
  );
}
