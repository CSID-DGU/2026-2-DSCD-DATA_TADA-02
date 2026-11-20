export const MAX_CANDIDATES = 5;

export function toggleCandidate(selected, code) {
  if (selected.includes(code)) return selected.filter(value => value !== code);
  if (selected.length >= MAX_CANDIDATES) throw new Error('후보 상권은 최대 5개까지 선택할 수 있습니다.');
  return [...selected, code];
}

export function visibleCandidates(selected, offset, width) {
  const start = Math.max(0, Math.min(offset, Math.max(0, selected.length - width)));
  return { start, values: selected.slice(start, start + width) };
}
