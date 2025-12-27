// Utility to check/adjust triangle obtuse angle at given vertex (A) while preserving anchor.

export function isObtuseAtA(A, B, C) {
  const vAB = [B[0] - A[0], B[1] - A[1]];
  const vAC = [C[0] - A[0], C[1] - A[1]];
  const dot = vAB[0] * vAC[0] + vAB[1] * vAC[1];
  return dot < 0; // dot<0 -> obtuse at A
}

export function adjustTriangleForObtuseAtA(A, B, C) {
  if (isObtuseAtA(A, B, C)) return { A, B, C, adjusted: false };
  // Simple adjustment: swing C upward/left relative to A to increase angle at A
  const dx = B[0] - A[0];
  const dy = B[1] - A[1];
  const newC = [A[0] - Math.abs(dy || 1), A[1] + Math.abs(dx || 2)];
  if (isObtuseAtA(A, B, newC)) return { A, B, C: newC, adjusted: true };
  // Fallback: widen base and raise C
  const widerB = [A[0] + (dx || 4) + 2, A[1]];
  const higherC = [A[0] - 1, A[1] + Math.abs(dx || 3)];
  return { A, B: widerB, C: higherC, adjusted: true };
}
