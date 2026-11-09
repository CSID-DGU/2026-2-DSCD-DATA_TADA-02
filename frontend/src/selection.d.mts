export const MAX_CANDIDATES: number;
export function toggleCandidate(selected: string[], code: string): string[];
export function visibleCandidates<T>(selected: T[], offset: number, width: number): { start: number; values: T[] };
