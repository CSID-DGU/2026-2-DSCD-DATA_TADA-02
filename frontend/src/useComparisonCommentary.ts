import { useCallback, useEffect, useReducer, useRef } from 'react';
import { api } from './api';
import type { Explanation } from './types';

export const COMPARISON_SECTIONS = ['competition', 'profitability', 'demand', 'rent'] as const;
type ComparisonSection = typeof COMPARISON_SECTIONS[number];
type ComparisonRequest = {
  scope: 'comparison';
  section: ComparisonSection;
  area_codes: string[];
  quarter: string;
  rental_area_m2?: number;
  rental_floor?: string;
};
type DetailRequest = {
  scope: 'detail';
  section: 'profitability' | 'demand' | 'location';
  area_codes: [string];
  quarter: string;
  demand_metric?: 'transactions' | 'floating_population';
  location_view?: 'rentals';
};
const DETAIL_TABS = ['sales', 'transactions', 'floating_population', 'rentals'] as const;
type DetailTab = typeof DETAIL_TABS[number];
type Request = ComparisonRequest | DetailRequest;
type Entry = { result?: Explanation; error?: string };
type Session = {
  group: string;
  token: string;
  controller: AbortController;
  results: Map<string, Entry>;
};

function requestKey(request: Request) {
  return JSON.stringify(request);
}

function nextPoll(signal: AbortSignal, seconds: number) {
  return new Promise<void>(resolve => {
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    };
    const timer = setTimeout(done, seconds * 1000);
    signal.addEventListener('abort', done, { once: true });
  });
}

async function loadExplanation(key: string, session: Session, update: () => void) {
  const signal = session.controller.signal;
  const started = performance.now();
  session.results.set(key, {});
  update();
  try {
    for (let attempt = 0; attempt <= 35 && !signal.aborted; attempt++) {
      const result = await api<Explanation>('/explanations', {
        method: 'POST', body: key, signal,
        headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
      });
      if (signal.aborted) return;
      if (result.status !== 'running') {
        session.results.set(key, { result });
        performance.measure('ui:commentary-ready', { start: started, end: performance.now() });
        update();
        return;
      }
      if (attempt < 35) await nextPoll(signal, result.retry_after_seconds || 2);
    }
    if (!signal.aborted) {
      session.results.set(key, { error: '생성 대기가 길어졌습니다. 잠시 후 다시 시도하세요.' });
      update();
    }
  } catch (error) {
    if (signal.aborted) return;
    session.results.set(key, { error: error instanceof Error ? error.message : String(error) });
    update();
  }
}

export function useComparisonCommentary({ active, areaKey, quarter, rentalArea, rentalFloor, accessToken, authRequired }: {
  active: boolean;
  areaKey: string;
  quarter: string;
  rentalArea: number;
  rentalFloor: string;
  accessToken: string;
  authRequired: boolean;
}) {
  const session = useRef<Session | null>(null);
  const [, redraw] = useReducer((revision: number) => revision + 1, 0);
  const group = `${quarter}:${areaKey}`;
  const requestNeedsAuth = authRequired && !accessToken;
  const current = session.current?.group === group && session.current.token === accessToken
    ? session.current : null;

  const requestFor = useCallback((section: ComparisonSection): ComparisonRequest => {
    const base: ComparisonRequest = { scope: 'comparison', section, area_codes: areaKey ? areaKey.split(',') : [], quarter };
    return section === 'rent' ? { ...base, rental_area_m2: rentalArea, rental_floor: rentalFloor } : base;
  }, [areaKey, quarter, rentalArea, rentalFloor]);

  useEffect(() => {
    if (!active || !areaKey || requestNeedsAuth) return;
    let work = session.current;
    if (!work || work.group !== group || work.token !== accessToken) {
      work?.controller.abort();
      work = { group, token: accessToken, controller: new AbortController(), results: new Map() };
      session.current = work;
    }
    for (const section of COMPARISON_SECTIONS) {
      const key = requestKey(requestFor(section));
      if (!work.results.has(key)) void loadExplanation(key, work, redraw);
    }
  }, [active, areaKey, group, requestFor, accessToken, requestNeedsAuth]);

  useEffect(() => () => {
    session.current?.controller.abort();
    session.current = null;
  }, []);

  return {
    requestNeedsAuth,
    requestFor,
    entryFor: (section: ComparisonSection) => current?.results.get(requestKey(requestFor(section))),
    retry: (section: ComparisonSection) => {
      if (current && !requestNeedsAuth) void loadExplanation(requestKey(requestFor(section)), current, redraw);
    },
  };
}

function detailRequestFor(areaCode: string, quarter: string, tab: DetailTab): DetailRequest {
  const area_codes: [string] = [areaCode];
  const base = { scope: 'detail' as const, area_codes, quarter };
  if (tab === 'sales') return { ...base, section: 'profitability' };
  if (tab === 'rentals') return { ...base, section: 'location', location_view: 'rentals' };
  return { ...base, section: 'demand', demand_metric: tab };
}

export function useDetailCommentary({ active, areaCode, quarter, tab, accessToken, authRequired }: {
  active: boolean;
  areaCode: string;
  quarter: string;
  tab: DetailTab | null;
  accessToken: string;
  authRequired: boolean;
}) {
  const session = useRef<Session | null>(null);
  const [, redraw] = useReducer((revision: number) => revision + 1, 0);
  const requestNeedsAuth = authRequired && !accessToken;
  const group = areaCode ? quarter + ':' + areaCode : '';
  const request = areaCode && tab ? detailRequestFor(areaCode, quarter, tab) : null;
  const key = request ? requestKey(request) : '';
  const current = session.current?.group === group && session.current.token === accessToken
    ? session.current : null;

  useEffect(() => {
    if (!active || !areaCode || requestNeedsAuth) return;
    let work = session.current;
    if (!work || work.group !== group || work.token !== accessToken) {
      work?.controller.abort();
      work = { group, token: accessToken, controller: new AbortController(), results: new Map() };
      session.current = work;
    }
    for (const tab of DETAIL_TABS) {
      const key = requestKey(detailRequestFor(areaCode, quarter, tab));
      if (!work.results.has(key)) void loadExplanation(key, work, redraw);
    }
  }, [active, areaCode, quarter, group, accessToken, requestNeedsAuth]);

  useEffect(() => () => {
    session.current?.controller.abort();
    session.current = null;
  }, []);

  return {
    request,
    requestNeedsAuth,
    entry: current?.results.get(key),
    retry: () => {
      if (active && key && current && !requestNeedsAuth) void loadExplanation(key, current, redraw);
    },
  };
}
