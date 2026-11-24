export const MAX_CANDIDATES: number;
export function toggleCandidate(selected: string[], code: string): string[];
export function cardScrollTarget(position: number, step: number, maximum: number, offset?: number): number;
export function cardWindow(position: number, step: number, maximum: number, total: number): { start: number; lastStart: number; total: number };
