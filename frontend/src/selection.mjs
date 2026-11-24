export const MAX_CANDIDATES = 5;

export function toggleCandidate(selected, code) {
  if (selected.includes(code)) return selected.filter(value => value !== code);
  if (selected.length >= MAX_CANDIDATES) throw new Error(`후보 상권은 최대 ${MAX_CANDIDATES}개까지 선택할 수 있습니다.`);
  return [...selected, code];
}

export function cardScrollTarget(position, step, maximum, offset = 0) {
  if (!(step > 0)) return 0;
  const index = Math.round(position / step) + offset;
  return Math.min(maximum, Math.max(0, index * step));
}
