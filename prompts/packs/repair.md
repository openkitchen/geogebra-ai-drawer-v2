## Phase: repair（执行失败后的修复）
- 依据反馈逐条定位错误命令（Unknown command / evalCommand=false / Object not created）。
- 用白名单写法替换：先造点再造线；平行用 `Line(P,l)`；避免 `Line((0,0),(4,0))`。
- 删除本次失败产生的对象，再重建；不要动用户已有对象。
- 重发完整命令列表，保持命名一致。
- 仍然优先保持简洁：不要因为修复添加额外冗余对象。

### 典型报错 → 推荐替换
- `Unknown command: RegularPolygon/Square`：
  - **最稳简化**：直接画一个坐标轴对齐的正方形（不追求“基于用户给的线段”也可以先满足“画出来”）：  
    - `A=(0,0)` `B=(3,0)` `D=(0,3)` `E=(3,3)` `sq=Polygon(A,B,E,D)`
  - 若用户明确要求“以 AB 为边作正方形”，再在后续迭代中补更严谨的构造。
- `evalCommand=false` 且命令含 `Intersect(..., 1)` / `Intersection(..., 1)`：
  - 改为不带索引的 `Intersect(obj1,obj2)`，或换一种更稳的构造（优先 Midpoint + PerpendicularLine）。

