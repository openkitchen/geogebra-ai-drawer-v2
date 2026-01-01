type AnyRecord = Record<string, unknown>;

export type FrontendToolOk = {
  ok: true;
  output: unknown;
};

export type FrontendToolErr = {
  ok: false;
  error: { message: string };
};

export type FrontendToolResult = FrontendToolOk | FrontendToolErr;

function safe<T>(fn: () => T): T | null {
  try {
    return fn();
  } catch {
    return null;
  }
}

function isLikelyAlgebra(commands: string[]): boolean {
  const joined = commands.join('\n').toLowerCase();
  return (
    /(^|\n)\s*[a-z]\w*\(x\)\s*=/.test(joined) ||
    /(^|\n)\s*y\s*=/.test(joined) ||
    /\bsin\b|\bcos\b|\btan\b|\blog\b|\bexp\b/.test(joined) ||
    /\bfunction\b|\bderivative\b|\bintegral\b/.test(joined)
  );
}

function applyCanvasPreset(kind: 'geometry' | 'algebra', api: GeoGebraAppletApi): void {
  try {
    if (kind === 'geometry') {
      api.setAxesVisible?.(false, false);
      api.setGridVisible?.(false);
    } else {
      api.setAxesVisible?.(true, true);
      api.setGridVisible?.(true);
    }
  } catch {
    // Best-effort only.
  }
}

function showKeyLabels(api: GeoGebraAppletApi): void {
  const names = safe(() => api.getAllObjectNames()) ?? [];
  const keyPoints = names.filter((n) => /^[A-Z]([A-Za-z0-9_]+)?$/.test(n));
  for (const p of keyPoints.slice(0, 24)) {
    const typ = safe(() => api.getObjectType(p));
    if (typeof typ === 'string' && typ.toLowerCase() !== 'point') continue;
    try {
      api.setCaption?.(p, p);
      api.setLabelVisible?.(p, true);
    } catch {
      // ignore
    }
  }
}

function hideAngleValueLabels(api: GeoGebraAppletApi): void {
  const names = safe(() => api.getAllObjectNames()) ?? [];
  for (const n of names.slice(0, 200)) {
    let isAngle = false;
    const typ = safe(() => api.getObjectType(n));
    if (typeof typ === 'string' && typ.toLowerCase() === 'angle') isAngle = true;
    if (!isAngle && /^ang/i.test(n)) isAngle = true;
    if (!isAngle) continue;
    try {
      api.setLabelVisible?.(n, false);
    } catch {
      // ignore
    }
  }
}

function validateDiagram(api: GeoGebraAppletApi): string[] {
  const warnings: string[] = [];
  const names = safe(() => api.getAllObjectNames()) ?? [];
  const angles: string[] = [];
  for (const n of names.slice(0, 400)) {
    let isAngle = false;
    const typ = safe(() => api.getObjectType(n));
    if (typeof typ === 'string' && typ.toLowerCase() === 'angle') isAngle = true;
    if (!isAngle && /^ang/i.test(n)) isAngle = true;
    if (isAngle) angles.push(n);
  }
  if (angles.length > 6) {
    warnings.push(`Too many angle objects (${angles.length}); keep only necessary arcs.`);
  }
  for (const ang of angles.slice(0, 50)) {
    const visible = safe(() => api.getLabelVisible?.(ang));
    if (visible === true) warnings.push(`Angle label still visible: ${ang} (should hide numeric labels).`);
  }
  return warnings;
}

function parseLabelsString(labels: unknown): string[] | null {
  if (typeof labels !== 'string') return null;
  const parts = labels
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  return parts.length ? parts : null;
}

function getCanvasRoot(): HTMLElement | null {
  // Prefer a dedicated root to avoid accidentally treating our own UI buttons as GeoGebra dialogs.
  const el = document.getElementById('ggb-canvas-root');
  return el instanceof HTMLElement ? el : null;
}

function consumeGeoGebraDialogs(): string[] {
  // GeoGebra often reports failures via in-app dialogs (OK/Close) instead of throwing.
  // We extract messages and close dialogs so the app can continue.
  const btnTexts = ['close', 'ok', '确定', '关闭'];
  const root = getCanvasRoot() ?? document.body;
  const btns = Array.from(root.querySelectorAll('button')) as HTMLButtonElement[];
  const targetBtn =
    btns.find((b) => btnTexts.some((t) => (b.textContent || '').trim().toLowerCase() === t)) ||
    btns.find((b) => btnTexts.some((t) => (b.textContent || '').toLowerCase().includes(t.toLowerCase())));
  if (!targetBtn) return [];

  // Walk up to find a container with error text.
  let node: HTMLElement | null = targetBtn;
  let best: HTMLElement | null = null;
  for (let i = 0; i < 12 && node; i++) {
    const t = (node.innerText || '').trim();
    if (
      t.includes('Unknown command') ||
      t.includes('Circular definition') ||
      t.includes('Undefined variable') ||
      t.includes('Please check your input') ||
      t.includes('Error') ||
      t.includes('错误') ||
      t.includes('未定义')
    ) {
      best = node;
    }
    node = node.parentElement;
  }

  const rawText = ((best || targetBtn.parentElement) as HTMLElement | null)?.innerText || '';

  // Close the dialog to unblock UI.
  targetBtn.click();

  const lines = rawText
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

  // Prefer concise, high-signal error line(s)
  const picked =
    lines.find((l) => l.includes('Unknown command')) ||
    lines.find((l) => l.includes('Circular definition')) ||
    lines.find((l) => l.includes('Undefined variable')) ||
    lines.find((l) => l.toLowerCase().includes('error')) ||
    null;

  return [picked || (lines.length ? lines.slice(0, 6).join(' | ') : 'GeoGebra dialog error')].filter(Boolean);
}

function toIncludeList(input: unknown): string[] {
  if (!input || typeof input !== 'object') return ['objects'];
  const include = (input as AnyRecord).include;
  if (!Array.isArray(include)) return ['objects'];
  return include.filter((x): x is string => typeof x === 'string');
}

function getCanvasState(input: unknown, api: GeoGebraAppletApi): unknown {
  const include = toIncludeList(input);
  const result: AnyRecord = {};

  if (include.includes('objects')) {
    const names = safe(() => api.getAllObjectNames()) ?? [];
    result.objects = names.map((name) => {
      const type = safe(() => api.getObjectType(name));
      return {
        name,
        type,
        visible: safe(() => api.getVisible(name)),
        valueString: safe(() => api.getValueString(name)),
        definitionString: safe(() => api.getDefinitionString(name)),
        commandString: safe(() => api.getCommandString(name)),
      };
    });
  }

  return result;
}

function evalExpression(input: unknown, api: GeoGebraAppletApi): unknown {
  if (!input || typeof input !== 'object') throw new Error('Missing input');
  const expr = (input as AnyRecord).expression;
  if (typeof expr !== 'string' || !expr.trim()) throw new Error('Missing input.expression');

  const ok = api.evalCommand(expr);
  const labelsText = safe(() => api.evalCommandGetLabels(expr));
  const labels = parseLabelsString(labelsText);
  const dialogs: string[] = [];
  for (let i = 0; i < 8; i++) {
    const drained = consumeGeoGebraDialogs();
    if (!drained.length) break;
    dialogs.push(...drained);
  }
  return { ok, labels, dialogs: dialogs.length ? dialogs : null };
}

function parseFirstNumber(valueString: unknown): number | null {
  if (typeof valueString !== 'string') return null;
  const s = valueString.trim();
  if (!s) return null;
  const cleaned = s.replaceAll('°', '').replaceAll('deg', '').replaceAll('rad', '');
  const m = cleaned.match(/[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/);
  if (!m) return null;
  const n = Number(m[0]);
  return Number.isFinite(n) ? n : null;
}

function evalNumeric(input: unknown, api: GeoGebraAppletApi): unknown {
  if (!input || typeof input !== 'object') throw new Error('Missing input');
  const expressionsRaw = (input as AnyRecord).expressions;
  if (!Array.isArray(expressionsRaw)) throw new Error('Missing input.expressions');
  const expressions = expressionsRaw
    .filter((e): e is string => typeof e === 'string')
    .map((e) => e.trim())
    .filter((e) => e.length > 0);
  if (!expressions.length) throw new Error('Missing input.expressions');

  const dialogs: string[] = [];
  const results = expressions.slice(0, 24).map((expression) => {
    // Drain dialogs before each expression to avoid blocking.
    for (let i = 0; i < 8; i++) {
      const drained = consumeGeoGebraDialogs();
      if (!drained.length) break;
      dialogs.push(...drained);
    }

    if (expression.includes('=')) {
      return {
        expression,
        ok: false,
        value: null,
        value_string: null,
        temp_label: null,
        error: { message: 'eval_numeric expressions must not contain "=" (no side effects)' },
      };
    }

    const tempLabel = `__m_${crypto.randomUUID().replaceAll('-', '').slice(0, 10)}`;
    const okValue = safe(() => api.evalCommand(`${tempLabel} = ${expression}`));
    const ok = okValue === true;
    const valueString = ok ? safe(() => api.getValueString(tempLabel)) : null;
    const valueFromApi = ok ? safe(() => (api as any).getValue?.(tempLabel)) : null;
    const value =
      typeof valueFromApi === 'number' && Number.isFinite(valueFromApi) ? valueFromApi : parseFirstNumber(valueString);

    if (ok) safe(() => api.deleteObject(tempLabel));

    for (let i = 0; i < 8; i++) {
      const drained = consumeGeoGebraDialogs();
      if (!drained.length) break;
      dialogs.push(...drained);
    }

    const errorString = safe(() => (api as any).getErrorString?.()) as unknown;
    const error =
      ok
        ? null
        : typeof errorString === 'string' && errorString.trim()
          ? { message: errorString.trim() }
          : { message: 'Expression failed' };

    return {
      expression,
      ok,
      value: value ?? null,
      value_string: typeof valueString === 'string' && valueString.trim() ? valueString.trim() : null,
      temp_label: tempLabel,
      error,
    };
  });

  return { results, dialogs: dialogs.length ? dialogs : null };
}

function execGeogebraCommands(input: unknown, api: GeoGebraAppletApi): unknown {
  if (!input || typeof input !== 'object') throw new Error('Missing input');
  const commands = (input as AnyRecord).commands;
  if (!Array.isArray(commands)) throw new Error('Missing input.commands');
  const lines = commands.filter((c): c is string => typeof c === 'string' && c.trim().length > 0);
  const beforeNames = safe(() => api.getAllObjectNames()) ?? [];
  const beforeSet = new Set(beforeNames);

  const preset: 'geometry' | 'algebra' = isLikelyAlgebra(lines) ? 'algebra' : 'geometry';
  applyCanvasPreset(preset, api);

  const dialogs: string[] = [];
  const results = lines.map((command) => {
    // Drain any existing dialogs before issuing a new command (they can block input).
    for (let i = 0; i < 8; i++) {
      const drained = consumeGeoGebraDialogs();
      if (!drained.length) break;
      dialogs.push(...drained);
    }

    const okValue = safe(() => api.evalCommand(command));
    const ok = okValue === true;
    const labelsText = safe(() => api.evalCommandGetLabels(command));
    const labels = parseLabelsString(labelsText);
    const errorString = safe(() => (api as any).getErrorString?.()) as unknown;
    const error =
      ok
        ? null
        : typeof errorString === 'string' && errorString.trim()
          ? { message: errorString.trim() }
          : { message: 'Command failed' };
    return { command, ok, labels, error };
  });

  // Drain dialogs after execution too.
  for (let i = 0; i < 8; i++) {
    const drained = consumeGeoGebraDialogs();
    if (!drained.length) break;
    dialogs.push(...drained);
  }

  const afterNames = safe(() => api.getAllObjectNames()) ?? [];
  const afterSet = new Set(afterNames);
  const createdObjects = afterNames.filter((n) => !beforeSet.has(n));
  const deletedObjects = beforeNames.filter((n) => !afterSet.has(n));

  const hasHardFailure = results.some((r) => !r.ok);
  let rolledBackObjects: string[] = [];
  let rollbackErrors: Array<{ object_name: string; message: string }> = [];

  if (hasHardFailure && createdObjects.length) {
    for (const name of createdObjects) {
      safe(() => api.deleteObject(name));
    }

    const afterRollbackNames = safe(() => api.getAllObjectNames()) ?? [];
    const afterRollbackSet = new Set(afterRollbackNames);
    rolledBackObjects = createdObjects.filter((n) => !afterRollbackSet.has(n));
    rollbackErrors = createdObjects
      .filter((n) => afterRollbackSet.has(n))
      .map((object_name) => ({ object_name, message: 'Object still present after rollback' }));
  }

  if (!hasHardFailure) {
    if (preset === 'geometry') {
      showKeyLabels(api);
      hideAngleValueLabels(api);
    }
  }

  const qualityWarnings = preset === 'geometry' && !hasHardFailure ? validateDiagram(api) : [];

  return {
    results,
    created_objects: createdObjects,
    deleted_objects: deletedObjects,
    rolled_back_objects: rolledBackObjects.length ? rolledBackObjects : null,
    rollback_errors: rollbackErrors.length ? rollbackErrors : null,
    dialogs: dialogs.length ? dialogs : null,
    preset_applied: preset,
    quality_warnings: qualityWarnings.length ? qualityWarnings : null,
  };
}

function deleteObjects(input: unknown, api: GeoGebraAppletApi): unknown {
  if (!input || typeof input !== 'object') throw new Error('Missing input');
  const objects = (input as AnyRecord).objects;
  if (!Array.isArray(objects)) throw new Error('Missing input.objects');

  const names = objects.filter((n): n is string => typeof n === 'string' && n.trim().length > 0);
  const beforeNames = safe(() => api.getAllObjectNames()) ?? [];
  const beforeSet = new Set(beforeNames);
  let deleted: string[] = [];
  let failed: Array<{ object_name: string; message: string }> = [];
  const dialogs: string[] = [];

  for (const name of names) {
    for (let i = 0; i < 8; i++) {
      const drained = consumeGeoGebraDialogs();
      if (!drained.length) break;
      dialogs.push(...drained);
    }
    safe(() => api.deleteObject(name));
  }

  for (let i = 0; i < 8; i++) {
    const drained = consumeGeoGebraDialogs();
    if (!drained.length) break;
    dialogs.push(...drained);
  }

  const afterNames = safe(() => api.getAllObjectNames()) ?? [];
  const afterSet = new Set(afterNames);
  deleted = names.filter((n) => beforeSet.has(n) && !afterSet.has(n));
  failed = [
    ...names.filter((n) => afterSet.has(n)).map((object_name) => ({ object_name, message: 'Object still present after deletion' })),
    ...names.filter((n) => !beforeSet.has(n)).map((object_name) => ({ object_name, message: 'Object not found' })),
  ];

  return {
    deleted_objects: deleted,
    failed_objects: failed.length ? failed : null,
    dialogs: dialogs.length ? dialogs : null,
  };
}

export async function runFrontendTool(args: {
  toolName: string;
  input: unknown;
  ggbApi: GeoGebraAppletApi | null;
}): Promise<FrontendToolResult> {
  try {
    const api = args.ggbApi;
    if (!api) throw new Error('ggbApplet is not ready');

    if (args.toolName === 'get_canvas_state') {
      return { ok: true, output: getCanvasState(args.input, api) };
    }

    if (args.toolName === 'eval_expression') {
      return { ok: true, output: evalExpression(args.input, api) };
    }

    if (args.toolName === 'eval_numeric') {
      return { ok: true, output: evalNumeric(args.input, api) };
    }

    if (args.toolName === 'exec_geogebra_commands') {
      return { ok: true, output: execGeogebraCommands(args.input, api) };
    }

    if (args.toolName === 'delete_objects') {
      return { ok: true, output: deleteObjects(args.input, api) };
    }

    return { ok: false, error: { message: `Unknown frontend tool: ${args.toolName}` } };
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return { ok: false, error: { message } };
  }
}
