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
  const appletRef = useRef<GeoGebraAppletApi | null>(null);
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

        // Measure container explicitly
        const width = host.clientWidth;
        const height = host.clientHeight;

        host.innerHTML = '';

        if (!window.GGBApplet) throw new Error('GeoGebra script loaded but GGBApplet is not available');

        // Robust Configuration:
        // 1. Explicit dimensions (width/height) matching container
        // 2. No 'autoHeight' or 'scaleContainerClass' to avoid conflict with manual sizing
        // 3. Perspective '2' (Geometry) to hide Algebra view sidebar
        // 4. scale: 1 (default) or rely on setGlobalFontSize for UI scaling
        const params: GeoGebraAppletParameters = {
          id: appletId,
          appName: 'classic',
          perspective: '2', // Geometry view (hides algebra)
          width: width || 800,
          height: height || 600,
          showToolBar: true,
          showMenuBar: false,
          showAlgebraInput: false,
          showResetIcon: true,
          enableShiftDragZoom: true,
          allowUpscale: false, // Prevent weird scaling
          scaleContainerClass: undefined, // Disable auto-scaler
          autoHeight: false, // Disable auto-height
          appletOnLoad: (api) => {
            if (cancelled) return;
            setStatus('ready');
            appletRef.current = api;
            
            // Set smaller font size for "compact" look
            try {
              if (api.setGlobalFontSize) api.setGlobalFontSize(12);
            } catch (e) {
              console.warn('Failed to set font size', e);
            }

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
      appletRef.current = null;
    };
  }, [appletId, onAppletReady]);

  // ResizeObserver to keep GGB in sync with container
  useEffect(() => {
    if (!hostRef.current) return;
    
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (appletRef.current && appletRef.current.setSize) {
          const { width, height } = entry.contentRect;
          if (width > 0 && height > 0) {
            appletRef.current.setSize(width, height);
          }
        }
      }
    });

    ro.observe(hostRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div className={className}>
      <div className="ggb-status">
        <span className={`ggb-pill ${status}`}>applet: {status}</span>
        {status === 'error' ? <span className="ggb-error">{error}</span> : null}
      </div>
      <div ref={hostRef} className="ggb-host" id="ggb-canvas-root" style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }} />
    </div>
  );
}
