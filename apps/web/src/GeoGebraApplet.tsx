import { useEffect, useMemo, useRef, useState } from 'react';

let deployScriptPromise: Promise<void> | null = null;

function loadDeployScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.reject(new Error('window is undefined'));
  if (window.GGBApplet) return Promise.resolve();
  if (deployScriptPromise) return deployScriptPromise;

  deployScriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector('script[data-geogebra-deploy="true"]') as HTMLScriptElement | null;
    if (existing) {
      const onLoad = () => resolve();
      const onError = () => reject(new Error('Failed to load GeoGebra deploy script'));
      existing.addEventListener('load', onLoad, { once: true });
      existing.addEventListener('error', onError, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://www.geogebra.org/apps/deployggb.js';
    script.dataset.geogebraDeploy = 'true';
    script.addEventListener('load', () => resolve(), { once: true });
    script.addEventListener('error', () => reject(new Error('Failed to load GeoGebra deploy script')), { once: true });
    document.head.appendChild(script);
  });

  return deployScriptPromise;
}

type Status = 'loading' | 'ready' | 'error';

export type GeoGebraAppletProps = {
  className?: string;
  onAppletReady?: (api: GeoGebraAppletApi) => void;
};

export function GeoGebraApplet({ className, onAppletReady }: GeoGebraAppletProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState<string | null>(null);
  const appletId = useMemo(() => `ggbApplet-${crypto.randomUUID()}`, []);

  useEffect(() => {
    let cancelled = false;

    async function mount() {
      try {
        setStatus('loading');
        setError(null);
        await loadDeployScript();
        if (cancelled) return;

        const host = hostRef.current;
        if (!host) throw new Error('Missing GeoGebra host element');

        host.innerHTML = '';

        if (!window.GGBApplet) throw new Error('GeoGebra script loaded but GGBApplet is not available');

        const params: GeoGebraAppletParameters = {
          id: appletId,
          appName: 'classic',
          showToolBar: true,
          showMenuBar: false,
          showAlgebraInput: false,
          showResetIcon: true,
          enableShiftDragZoom: true,
          allowUpscale: true,
          scaleContainerClass: 'ggb-host',
          autoHeight: true,
          scale: 0.8,
          appletOnLoad: (api) => {
            if (cancelled) return;
            setStatus('ready');
            onAppletReady?.(api);
          },
        };

        const applet = new window.GGBApplet(params, true);
        applet.inject(host);
      } catch (e) {
        if (cancelled) return;
        const message = e instanceof Error ? e.message : String(e);
        setStatus('error');
        setError(message);
      }
    }

    void mount();

    return () => {
      cancelled = true;
      if (hostRef.current) hostRef.current.innerHTML = '';
    };
  }, [appletId, onAppletReady]);

  return (
    <div className={className}>
      <div className="ggb-status">
        <span className={`ggb-pill ${status}`}>applet: {status}</span>
        {status === 'error' ? <span className="ggb-error">{error}</span> : null}
      </div>
      <div ref={hostRef} className="ggb-host" id="ggb-canvas-root" />
    </div>
  );
}
