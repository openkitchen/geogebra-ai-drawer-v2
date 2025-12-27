## Phase: edit（基于现状的修改）
- 只做增量：复用已有对象名；不要重建整张图。
- 先读取当前对象与状态（前端已提供）；只修改相关对象。
- 删除操作：精确删除指定对象；不要删用户未知对象。
- 新命名沿用主图风格（A,B,C,l,m...）；避免引入无用辅助对象。
- 保持原有可读性：新增元素不要遮挡关键角/点/文本。

### 常见增量修改的稳定 recipe（优先用这些）
- 画 BC 的垂直平分线（已存在点 B、C）：
  - `M=Midpoint(B,C)`
  - `lBC=Line(B,C)`
  - `perpBC=PerpendicularLine(M,lBC)`（不要依赖自动生成的边段名 a/b/c）
- 外接圆圆心（外心）：
  - 先作两条边的垂直平分线（如 AB、AC），再取交点：
  - `Mab=Midpoint(A,B)`; `Mac=Midpoint(A,C)`
  - `lAB=Line(A,B)`; `lAC=Line(A,C)`
  - `pAB=PerpendicularLine(Mab,lAB)`; `pAC=PerpendicularLine(Mac,lAC)`
  - `O=Intersect(pAB,pAC)`
  - `circ=Circle(O,A)`

### 禁止（高失败率）
- 不要用 `Intersection(..., Circle(...), 1)` / `Intersect(..., ..., 1)` 来找外心/交点；优先用“垂直平分线交点”。

