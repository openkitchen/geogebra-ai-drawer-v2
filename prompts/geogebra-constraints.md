# GeoGebra Constraints (Supplement)

- Commands are executed via GeoGebra Classic Input Bar (evalCommand). Do NOT output JS API / UI-only calls (e.g. ShowLabel/SetLabelVisible/SetCaption/ShowAxes/ShowGrid) as commands.
- Limited style whitelist: ONLY when the user explicitly asks for color/style emphasis, you may use:
  - `SetColor(obj, r, g, b)` (0..255 ints)
  - `SetLineThickness(obj, width)`
  - `SetLineStyle(obj, style)`
  - Keep it minimal (max 3 objects).
- Angles must be interior: when marking triangle angles, ensure < 180°; adjust point order or use `InteriorAngles(Polygon(A,B,C))`.
- Prefer point-order `Angle(B,A,C)` (vertex in the middle) and avoid commands that create exterior angles unless explicitly asked.
- `Text("...")` should only be used for **short labels/annotations** (<= 30 chars each, max 2). Do NOT dump long explanations onto the canvas.
