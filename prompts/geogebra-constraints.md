# GeoGebra Constraints (Supplement)

- Commands are executed via GeoGebra Classic Input Bar (evalCommand). Do NOT output JS API / UI-only calls (e.g. ShowLabel/SetLabelVisible/SetCaption/SetColor/ShowAxes/ShowGrid) as commands.
- Angles must be interior: when marking triangle angles, ensure < 180°; adjust point order or use `InteriorAngles(Polygon(A,B,C))`.
- Prefer point-order `Angle(B,A,C)` (vertex in the middle) and avoid commands that create exterior angles unless explicitly asked.
- `Text("...")` should only be used for **short labels/annotations** (<= 30 chars each, max 2). Do NOT dump long explanations onto the canvas.
