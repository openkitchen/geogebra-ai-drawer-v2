import { useMemo, useState } from 'react';
import { runFrontendTool } from './frontendTools';

type CanvasObject = {
  name: string;
  type?: string | null;
  visible?: boolean | null;
  valueString?: string | null;
  definitionString?: string | null;
  commandString?: string | null;
};

type CanvasStateOutput = {
  objects?: CanvasObject[];
};

export type CanvasInspectorProps = {
  ggbApi: GeoGebraAppletApi | null;
};

export function CanvasInspector({ ggbApi }: CanvasInspectorProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<CanvasStateOutput | null>(null);

  const objects = useMemo(() => {
    const list = output?.objects;
    return Array.isArray(list) ? list : [];
  }, [output]);

  async function refresh() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await runFrontendTool({
        toolName: 'get_canvas_state',
        input: { include: ['objects'] },
        ggbApi,
      });
      if (!result.ok) throw new Error(result.error.message);
      setOutput(result.output as CanvasStateOutput);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details>
      <summary>Canvas Inspector</summary>
      <div className="inspector">
        <div className="inspectorActions">
          <button className="secondary" onClick={() => void refresh()} disabled={!ggbApi || busy}>
            Refresh objects
          </button>
          <div className="meta">
            {!ggbApi ? 'ggbApplet not ready' : busy ? 'loading…' : error ? `ERROR: ${error}` : `objects: ${objects.length}`}
          </div>
        </div>

        {output ? <pre className="inspectorPre">{JSON.stringify(output, null, 2)}</pre> : null}

        {objects.length ? (
          <div className="inspectorList">
            {objects.map((obj) => {
              const title = `${obj.name}${obj.type ? ` (${obj.type})` : ''}${obj.visible === false ? ' [hidden]' : ''}`;
              return (
                <details key={obj.name} className="inspectorItem">
                  <summary>{title}</summary>
                  <div className="inspectorKV">
                    <div>
                      <span className="inspectorKey">valueString</span>
                      <span className="inspectorVal">{obj.valueString ?? ''}</span>
                    </div>
                    <div>
                      <span className="inspectorKey">definitionString</span>
                      <span className="inspectorVal">{obj.definitionString ?? ''}</span>
                    </div>
                    <div>
                      <span className="inspectorKey">commandString</span>
                      <span className="inspectorVal">{obj.commandString ?? ''}</span>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
        ) : null}
      </div>
    </details>
  );
}

