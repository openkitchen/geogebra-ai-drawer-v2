import React, { useEffect, useRef, useState, memo } from 'react';
import { Corner } from '../types';

interface GGBViewProps {
  onReady: (applet: any) => void;
  overlayTexts?: Partial<Record<Corner, string>>;
}

const GGBView: React.FC<GGBViewProps> = ({ onReady, overlayTexts }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState('准备中...');
  const appletRef = useRef<any>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    
    let isMounted = true;

    const startInjection = () => {
      if (!containerRef.current || !isMounted) return;

      // 检查 GGB 脚本是否加载
      if (typeof window.GGBApplet === 'undefined') {
        setTimeout(startInjection, 500);
        return;
      }

      const width = containerRef.current.clientWidth;
      const height = containerRef.current.clientHeight;

      // 关键：如果容器没有高度，GGB 渲染会失败
      if (width === 0 || height === 0) {
        setTimeout(startInjection, 200);
        return;
      }

      setStatus('启动引擎...');

      const parameters = {
        "appName": "classic",
        "width": width,
        "height": height,
        "showToolBar": true,
        "showMenuBar": false,
        "showAlgebraInput": false,
        "showResetIcon": true,
        "enableLabelDrags": true,
        "enableShiftDragZoom": true,
        "enableRightClick": true,
        "autoHeight": true, // 让 GGB 自动填满容器
        "allowStyleBar": true,
        "useBrowserForJS": true,
        "preventFocus": true,
        "appletOnLoad": (obj: any) => {
          if (isMounted) {
            console.log("GeoGebra 就绪");
            appletRef.current = obj;
            window.ggbApplet = obj;
            setStatus('Ready');
            onReady(obj);
          }
        }
      };

      try {
        const applet = new window.GGBApplet(parameters, '5.0');
        applet.inject('ggb-canvas-root');
        initialized.current = true;
      } catch (err) {
        console.error("GGB 注入失败:", err);
      }
    };

    // 稍微延迟一下确保容器布局完成
    const timer = setTimeout(startInjection, 300);

    const handleResize = () => {
      if (appletRef.current && containerRef.current) {
        appletRef.current.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      isMounted = false;
      clearTimeout(timer);
      window.removeEventListener('resize', handleResize);
    };
  }, [onReady]);

  return (
    <div ref={containerRef} className="w-full h-full bg-white relative rounded-2xl overflow-hidden shadow-2xl border border-slate-200">
      {status !== 'Ready' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-50 z-50">
          <div className="w-10 h-10 border-4 border-indigo-100 border-t-indigo-600 rounded-full animate-spin"></div>
          <p className="mt-4 text-slate-400 text-xs font-bold uppercase tracking-widest">{status}</p>
        </div>
      )}
      {status === 'Ready' && (
        <div className="absolute inset-0 pointer-events-none z-40">
          {(['top-left', 'top-right', 'bottom-left', 'bottom-right'] as Corner[]).map((corner) => {
            const text = overlayTexts?.[corner];
            if (!text || String(text).trim().length === 0) return null;
            const pos =
              corner === 'top-left'
                ? 'top-3 left-3 text-left'
                : corner === 'top-right'
                  ? 'top-3 right-3 text-right'
                  : corner === 'bottom-left'
                    ? 'bottom-3 left-3 text-left'
                    : 'bottom-3 right-3 text-right';
            return (
              <div
                key={corner}
                className={`absolute ${pos} max-w-[48%]`}
              >
                <div className="text-[12px] leading-snug text-slate-700 bg-white/85 border border-slate-200 rounded-lg px-3 py-2 shadow-sm backdrop-blur-sm whitespace-pre-wrap">
                  {String(text)}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div 
        id="ggb-canvas-root" 
        style={{ width: '100%', height: '100%' }}
      ></div>
    </div>
  );
};

export default memo(GGBView);
