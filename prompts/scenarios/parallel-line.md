## Scenario: Parallel line through an external point

When the user asks:
- “过直线外一点，如何做平行线，有几种方法，给我画示意图”

### Teaching goals
- Explain at least 2 methods:
  1) **Construct parallel via perpendicular twice**: a line perpendicular to a perpendicular is parallel.
  2) **Copy angle** (more advanced) if feasible; if not, explain conceptually without full construction.

### Diagram (method 0, most reliable in our env)
Prefer the direct GeoGebra pattern “Line through point parallel to a line”:
1. Create two points and line `l` (avoid `Line((0,0),(4,0))` which may fail here):
   - `A=(0,0)`
   - `B=(4,0)`
   - `l=Line(A,B)`
2. Create an external point `P`:
   - `P=(1,2)`
3. Construct the parallel line through `P`:
   - `m=Line(P,l)`   // through P parallel to l

Explain (kid-friendly): “过 P 作一条和 l 同方向的直线”，在 GeoGebra 里就是 `Line(P,l)`。

### Avoid common failure patterns (important)
- Avoid `Line((0,0),(4,0))` — create points first then `Line(A,B)`.
- Prefer `Line(P,l)` over “double perpendicular” when the goal is just a parallel.

### Optional Diagram (method 1, perpendicular twice)
If you also want to show the “两次作垂线”的思路，可在上面的基础上补充：
- `p=PerpendicularLine(P,l)`
- `m2=PerpendicularLine(P,p)`  // m2 ∥ l

If the user provides their own line/point names, reuse them.


