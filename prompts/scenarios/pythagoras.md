## Scenario: Pythagorean theorem (what / explain / demo)

When the user asks:
- “什么是勾股定理，解释，然后画一个示意图”
- “证明勾股定理 / 演示证明”

### Explain (kid-friendly)
- State the theorem: in a right triangle, \(a^2+b^2=c^2\).
- Explain what are “直角边” and “斜边”.

### Diagram levels (important)
We have two levels:
1) **示意图（默认）**：只画一个直角三角形即可（最小、最清晰）。
2) **演示/证明（可选）**：才画边上正方形（步骤多，容易出错，只有在用户明确要“演示证明/画边上正方形”时才做）。

#### Level 1: minimal right-triangle diagram (default)
- STRONG RULE: If the user did NOT explicitly ask for squares / proof demo, DO NOT draw any extra constructions (circles, perpendicular helpers, squares).
- `A=(0,0)`, `B=(3,0)`, `C=(0,4)`
- `TriangleABC=Polygon(A,B,C)`
- Optional: add a small right-angle marker (keep it minimal):
  - `angA=Angle(B,A,C)`
  - `SetLabelVisible(angA,false)`
  - `Text("直角",(0.2,0.2))`

#### Level 2: squares on sides (only when explicitly requested)
Given our environment stability constraints, keep Level 2 minimal and avoid `Intersect(...,1)`.
If you must show “squares”, only draw the two axis-aligned squares on the legs (AB and AC) for demonstration:
- Square on AB (AB is horizontal in our chosen coordinates):
  - `D=(0,3)`
  - `E=(3,3)`
  - `sqAB=Polygon(A,B,E,D)`
- Square on AC (AC is vertical):
  - `F=(4,0)`
  - `G=(4,4)`
  - `sqAC=Polygon(A,F,G,C)`

If anything fails, fall back to Level 1 only.


