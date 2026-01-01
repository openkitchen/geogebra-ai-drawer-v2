## Scenario: Triangle angle sum = 180°

When the user asks:
- “如何证明三角形的内角和是180度”

### Explain (kid-friendly)
- Use the classic parallel-line proof:
  - Through vertex A draw a line parallel to BC.
  - Alternate interior angles show the three angles form a straight line (180°).

### Diagram (reliable & minimal)
1. Base triangle:
   - `A=(0,0)`
   - `B=(4,0)`
   - `C=(1,3)`
   - `TriangleABC = Polygon(A,B,C)` (optional)
2. Key lines:
   - `lBC = Line(B,C)`                    // baseline
   - `l   = Line(A, lBC)`                 // through A parallel to BC
   - `lAB = Line(A,B)` ; `lAC = Line(A,C)` // for angle references
3. Angle arcs（只画必要的角，避免反射角）:
   - `angA=Angle(B,A,C)`      // ∠A
   - `angB=Angle(C,B,A)`      // ∠B（避免 360-∠B）
   - `angC=Angle(A,C,B)`      // ∠C（避免 360-∠C）
   - `angB2=Angle(lAB,l)`     // 对应 ∠B
   - `angC2=Angle(l,lAC)`     // 对应 ∠C
4. Text anchors（用文字而不是额外角对象来减轻拥挤；角度数值标签由应用层隐藏）:
   - `Text("α",(0.4,0.4))`
   - `Text("β",(3.7,0.3))`
   - `Text("γ",(1.1,2.6))`
   - `Text("∠A+∠B+∠C = 180°",(0,-1))`

### Keep it minimal (important)
- 不要添加额外的辅助点/线；不要做坐标偏移构造（如 `D = C + (-2,0)`）。
- 只保留上述角对象；若模型发现角对象过多或标签拥挤，应删减而不是再新增。
- 依赖前端的几何预设（隐藏轴/网格、显示关键点标签），不必额外开坐标系。

