export {};

declare global {
  // Minimal subset of GeoGebra Apps API we use in v2.
  // See: GeoGebra Apps API / deployggb.js embedding.
  interface GeoGebraAppletApi {
    evalCommand(command: string): boolean;
    evalCommandGetLabels(command: string): string;
    getErrorString?(): string;

    getAllObjectNames(): string[];
    getObjectType(objectName: string): string;

    getValueString(objectName: string): string;
    getDefinitionString(objectName: string): string;
    getCommandString(objectName: string): string;

    getVisible(objectName: string): boolean;
    deleteObject(objectName: string): boolean;

    setAxesVisible?(xAxis: boolean, yAxis: boolean): void;
    setGridVisible?(visible: boolean): void;
    setLabelVisible?(objectName: string, visible: boolean): void;
    getLabelVisible?(objectName: string): boolean;
    setCaption?(objectName: string, caption: string): void;
  }

  type GeoGebraAppletOnLoad = (api: GeoGebraAppletApi) => void;

  interface GeoGebraAppletParameters {
    id?: string;
    appName?: string;
    width?: number;
    height?: number;
    showToolBar?: boolean;
    showMenuBar?: boolean;
    showAlgebraInput?: boolean;
    showResetIcon?: boolean;
    enableShiftDragZoom?: boolean;
    allowUpscale?: boolean;
    scaleContainerClass?: string;
    appletOnLoad?: GeoGebraAppletOnLoad;
    [key: string]: unknown;
  }

  interface GeoGebraAppletInstance {
    inject(target: string | HTMLElement): void;
  }

  interface GeoGebraAppletConstructor {
    new (params: GeoGebraAppletParameters, useBrowserForJavaScript: boolean): GeoGebraAppletInstance;
  }

  interface Window {
    GGBApplet?: GeoGebraAppletConstructor;
  }
}
