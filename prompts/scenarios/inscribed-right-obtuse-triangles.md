## Scenario: Two inscribed triangles (right + obtuse) on the same circle

When the user asks (examples):
- “画一个圆，并在同一个圆上画两个三角形：一个直角三角形，一个钝角三角形（都要内接在同一个圆上）”

### Goal
- One circle `c` with center `O`.
- Two triangles on the **same** circle:
  - `T_right`: an inscribed **right** triangle.
  - `T_obtuse`: an inscribed **obtuse** triangle.

### Reliable construction (recommended)
Use `Rotate` around the center `O` so all vertices are guaranteed to lie on the same circle.

1) Circle:
- `O=(0,0)`
- `A=(5,0)`
- `c=Circle(O,A)`

2) Right triangle on the circle (Thales theorem):
- `B=Rotate(A,180°,O)`  // AB is a diameter
- `C=Rotate(A,60°,O)`   // any other point on the circle
- `T_right=Polygon(A,B,C)` // ∠ACB = 90°

3) Obtuse triangle on the same circle (make one angle > 90°):
- Pick two points far apart (~170°) and one point very close to A (~10°), all on the circle:
  - `E=Rotate(A,10°,O)`
  - `F=Rotate(A,170°,O)`
  - `T_obtuse=Polygon(A,E,F)`  // angle at E is obtuse (≈95°)

### Notes
- Keep it minimal; avoid extra helper objects.
- Do NOT dump long explanations with `Text(...)`. If the user explicitly asks for labels, keep `Text(...)` very short.
