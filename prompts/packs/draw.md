## Phase: draw（非证明的首次作图）
- 目标：最小可用、清晰可读、对象少。
- 命名：A,B,C,...；辅助线 l,m; 圆 c1...；避免随机命名。
- 少即是多：只有必要的点/线/圆；避免多余延长线与重复角。
- 标签/可见性/样式由应用层 deterministic 处理；不要在 `commands` 里输出 `Label/SetCaption/SetLabelVisible/ShowAxes/ShowGrid` 等 UI/JS API 调用。
- 角度：如需角弧，优先 `Angle(P,Q,R)`，尽量避免反射角；不必显示度数。
- 不使用高阶构造（RegularPolygon/Square等）；先造点再造线。

### “示意图”强规则（避免过度构造）
- 如果用户说“示意图/解释/是什么”，默认只画**最小示意**，不要自动加复杂构造（例如不要自动画正方形、不要加很多辅助线/圆）。
- 只有当用户明确说“证明/演示证明/画边上的正方形/面积法”时，才画更复杂的辅助构造。

### 可靠写法白名单（强烈推荐）
- 造线：`A=(0,0)`、`B=(4,0)`、`l=Line(A,B)`（避免 `Line((0,0),(4,0))`）
- 平行：`m=Line(P,l)`
- 垂线：`p=PerpendicularLine(P,l)`
- 中点（最稳）：`M=Midpoint(B,C)`（不要依赖自动生成的 a/b/c）
- 垂直平分线（最稳）：`M=Midpoint(B,C)` + `lBC=Line(B,C)` + `perp=PerpendicularLine(M,lBC)`

### 禁用/慎用写法（容易导致空白图/修复循环）
- `Intersect(..., 1)`/`Intersection(..., 1)` 这类“带索引选交点”的写法（不稳定、易失败）
- `Line((x1,y1),(x2,y2))`（在我们环境里经常失败）

### 示例：勾股定理（示意图默认）
- `A=(0,0)` `B=(3,0)` `C=(0,4)` `TriangleABC=Polygon(A,B,C)`
- 可选：直角标记（保持极简）：`angA=Angle(B,A,C)` + `Text("直角",(0.2,0.2))`（角度数值标签由应用层隐藏）
