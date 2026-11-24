import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { DemandCharts } from './Charts';
import AreaDetailButton from './AreaDetailButton';
import ComparisonCarousel from './ComparisonCarousel';
import ExplanationPanel, { DemoExplanationPanel } from './ExplanationPanel';
import { detailCommentary, PRESENTATION_DATA_VERSION, PRESENTATION_QUARTER } from './demoCommentary';
import { StoreCard } from './LocationStores';
import RentComparison from './RentComparison';
import OverviewComparison, { quarterLabel } from './OverviewComparison';
import SalesDetail from './SalesDetail';
import DetailAreaPicker from './DetailAreaPicker';
import { PYEONG_M2 } from './report-metrics.mjs';
import MapPicker, { LocationMap } from './MapPicker';
import { MAX_CANDIDATES, toggleCandidate } from './selection.mjs';
import type { Area, Comparison, ComparisonItem, Config, Detail, Section, Store } from './types';

type Route = { view: 'map' | 'comparison' | 'detail'; section: Section; codes: string[]; code: string };
const sectionLabels: Record<Section, string> = { profitability: '매출', competition: '종합해설', demand: '수요성', rent: '임대료', location: '입지/주변환경' };
const number = (value: number | null | undefined, digits = 0) => value == null ? '자료 없음' : value.toLocaleString('ko-KR', { maximumFractionDigits: digits });
const money = (value: number | null | undefined) => value == null ? '미확보' : `${number(value / 10000)}만 원`;
const listingMoney = (value: number | null) => value == null ? '미확보' :
  value % 10000 === 0 ? `${number(value / 10000)}만 원` : `${number(value)}원`;
const NO_STORES: Store[] = [];
const COMPARISON_PREVIEW_DELAY_MS = 1000;
const PRESENTATION_CANDIDATES = [
  '3120052', // 성수역
  '3120030', // 중부경찰서(영화인의거리)
  '3120186', // 가로수길
  '3120006', // 종각역
  '3110565', // 홍익대
];

function parseRoute(): Route {
  const params = new URLSearchParams(location.hash.slice(1));
  const view = params.get('view');
  const section = params.get('section');
  return { view: view === 'comparison' || view === 'detail' ? view : 'map', section: section && Object.hasOwn(sectionLabels, section) ? section as Section : view === 'detail' ? 'profitability' : 'competition',
    codes: [...new Set((params.get('areas') || '').split(',').filter(Boolean))].slice(0, MAX_CANDIDATES), code: params.get('area') || '' };
}

function Change({ value }: { value: number | null }) {
  return <span className={`change ${value != null && value < 0 ? 'negative' : ''}`}>{value == null ? '비교 자료 없음' : `${value > 0 ? '↑' : value < 0 ? '↓' : '→'} ${number(Math.abs(value), 1)}%`}</span>;
}

function MetricBar({ value, maximum }: { value: number | null; maximum: number }) {
  return <div className="metric-bar" aria-hidden="true"><span style={{ width: `${value == null || maximum <= 0 ? 0 : Math.min(100, Math.max(0, value / maximum * 100))}%` }} /></div>;
}

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [areas, setAreas] = useState<Area[]>([]);
  const [route, setRoute] = useState<Route>(parseRoute);
  const [pendingComparison, setPendingComparison] = useState<Route | null>(null);
  const comparisonDialog = useRef<HTMLDialogElement>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [recent, setRecent] = useState(true);
  const [areaPyeong, setAreaPyeong] = useState(20);
  const [rentalFloor, setRentalFloor] = useState('');
  const [demandMetric, setDemandMetric] = useState<'transactions' | 'floating_population'>('transactions');
  const [locationView, setLocationView] = useState<'rentals' | 'stores'>('rentals');
  const [listingId, setListingId] = useState('');
  const [radius, setRadius] = useState<100 | 300 | 500>(300);
  const [nearby, setNearby] = useState<{ key: string; items: Store[]; error?: string } | null>(null);
  const [accessToken, setAccessToken] = useState('');
  const [loadVersion, setLoadVersion] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([api<Config>('/config'), api<{ items: Area[] }>('/areas')])
      .then(([settings, catalog]) => { if (active) { setConfig(settings); setAreas(catalog.items); } })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [loadVersion]);

  const navigate = useCallback((next: Route) => {
    setNotice(''); setRoute(next);
    const params = new URLSearchParams({ view: next.view, section: next.section, areas: next.codes.join(','), area: next.code });
    history.pushState(null, '', `#${params}`);
  }, []);
  useEffect(() => {
    const back = () => { setPendingComparison(null); setRoute(parseRoute()); };
    window.addEventListener('popstate', back); window.addEventListener('hashchange', back);
    return () => { window.removeEventListener('popstate', back); window.removeEventListener('hashchange', back); };
  }, []);

  useEffect(() => {
    if (!pendingComparison || !comparisonDialog.current) return;
    const dialog = comparisonDialog.current;
    dialog.showModal();

    // This delay previews the wait before comparison commentary generation is connected.
    const timer = window.setTimeout(() => {
      setPendingComparison(null);
      navigate(pendingComparison);
    }, COMPARISON_PREVIEW_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      dialog.close();
    };
  }, [pendingComparison, navigate]);

  const codesKey = route.codes.join(',');
  const detailCode = route.code || route.codes[0] || '';
  useEffect(() => {
    if (!config || route.view === 'map' || (route.view === 'detail' ? !detailCode : !route.codes.length)) return;
    let active = true;
    const controller = new AbortController();
    const started = performance.now();
    setLoading(true); setError(''); setDetail(null); setComparison(null);
    const promise = route.view === 'detail'
      ? api<Detail>(`/areas/${encodeURIComponent(detailCode)}/analysis`, { signal: controller.signal })
      : api<Comparison>('/comparisons', { method: 'POST', body: JSON.stringify({ area_codes: route.codes }), signal: controller.signal });
    promise.then(result => {
      if (!active) return;
      if ('observations' in result) { setDetail(result); setListingId(result.rentals[0]?.id || ''); }
      else setComparison(result);
      requestAnimationFrame(() => { if (active) performance.measure('ui:charts-ready', { start: started, end: performance.now() }); });
    }).catch(err => { if (active && err.name !== 'AbortError') setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
    // Section changes reuse the same data payload while changing the commentary context.
  }, [config, route.view, detailCode, codesKey, loadVersion]);

  const nearbyKey = detail && listingId ? `${detail.area.code}:${detail.meta.quarter}:${listingId}:${radius}` : '';
  const nearbyResult = nearby?.key === nearbyKey ? nearby : null;
  const stores = listingId ? nearbyResult?.items ?? NO_STORES : detail?.stores ?? NO_STORES;

  useEffect(() => {
    if (route.view !== 'detail' || route.section !== 'location' || locationView !== 'stores' || !listingId || !detail) return;
    let active = true;
    const controller = new AbortController();
    const params = new URLSearchParams({ listing_id: listingId, radius_m: String(radius), quarter: detail.meta.quarter });
    api<Store[]>(`/areas/${detail.area.code}/nearby-stores?${params}`, { signal: controller.signal })
      .then(values => { if (active) setNearby({ key: nearbyKey, items: values }); })
      .catch(err => { if (active && err.name !== 'AbortError') setNearby({ key: nearbyKey, items: [], error: err.message }); });
    return () => { active = false; controller.abort(); };
  }, [detail, listingId, radius, nearbyKey, locationView, route.view, route.section]);

  const toggle = useCallback((code: string) => {
    setRoute(previous => {
      try { const codes = toggleCandidate(previous.codes, code); setNotice(''); return { ...previous, codes }; }
      catch (err) { setNotice((err as Error).message); return previous; }
    });
  }, []);
  const selectListing = useCallback((id: string) => setListingId(id), []);
  const openDetail = (code: string, section = route.section) => navigate({ ...route, view: 'detail', code, section: section === 'rent' ? 'location' : section === 'competition' ? 'profitability' : section });
  const tabs: Section[] = route.view === 'detail' ? ['profitability', 'demand', 'location'] : ['competition', 'profitability', 'demand', 'rent'];
  const section = tabs.includes(route.section) ? route.section : 'profitability';
  const openComparison = (section: Section) => {
    const next: Route = { ...route, view: 'comparison', section };
    if (route.view === 'map') {
      setPendingComparison(previous => previous ?? next);
    } else {
      navigate(next);
    }
  };
  const selected = areas.filter(a => route.codes.includes(a.code)).sort((a, b) => route.codes.indexOf(a.code) - route.codes.indexOf(b.code));
  const floor = comparison?.items.some(item => item.rentals.some(rental => rental.floor === rentalFloor)) ? rentalFloor : '';
  const demoCommentary = route.view === 'detail' && !loading && config?.llm_enabled === false &&
    detail?.area.code === detailCode && detail.current && detail.meta.quarter === PRESENTATION_QUARTER &&
    (detail.meta.data_version === PRESENTATION_DATA_VERSION || detail.meta.data_version === 'seoul-cafe-20261106-locations-20261120') &&
    (section === 'profitability' || section === 'demand') ? detailCommentary(detailCode, section) : null;
  const context: Record<string, unknown> = { scope: route.view === 'detail' ? 'detail' : 'comparison', section,
    area_codes: route.view === 'detail' ? [detail?.area.code || detailCode] : [...route.codes].sort(), quarter: '2026Q2' };
  if (route.view === 'detail' && section === 'demand') context.demand_metric = demandMetric;
  if (route.view === 'detail' && section === 'location') Object.assign(context, { location_view: locationView, listing_id: locationView === 'stores' ? listingId || null : null, radius_m: radius });
  if (route.view === 'comparison' && section === 'rent') Object.assign(context, { rental_area_m2: areaPyeong * PYEONG_M2, rental_floor: floor });

  if (!config) return <main className="startup"><h1>상권 분석</h1>{error ? <><p role="alert">서버에 연결하지 못했습니다: {error}</p><button onClick={() => setLoadVersion(v => v + 1)}>다시 연결</button></> : <p>상권 위치 목록을 불러오고 있습니다.</p>}</main>;

  const isDemo = config.data_mode === 'demo';
  const [analysisYear, analysisQuarter] = config.quarters[0].split('Q');
  const selectPresentationCandidates = () => {
    const candidates = isDemo ? config.demo_area_codes : PRESENTATION_CANDIDATES;
    navigate({ view: 'map', section: 'competition', codes: candidates, code: '' });
  };

  return <>
    <a className="skip-link" href="#main" onClick={event => { event.preventDefault(); document.getElementById('main')?.focus(); }}>본문으로 이동</a>
    <header className="site-header"><button className="brand" onClick={() => navigate({ ...route, view: 'map' })}><span className="brand-pin" aria-hidden="true">⌖</span> 상권 분석</button>
      <nav aria-label="주 메뉴">
        <button className={route.view === 'map' ? 'active' : ''} onClick={() => navigate({ ...route, view: 'map' })}>상권 탐색</button>
        <button className={route.view === 'comparison' ? 'active' : ''} disabled={!route.codes.length} onClick={() => openComparison(section === 'location' ? 'rent' : section)}>후보 상권 비교</button>
        <button className={route.view === 'detail' ? 'active' : ''} aria-current={route.view === 'detail' ? 'page' : undefined} onClick={() => openDetail(detailCode, 'profitability')}>상세 상권 분석</button>
        <button className="presentation-preset" onClick={selectPresentationCandidates}>발표용</button>
      </nav><span className="header-meta">DATA TADA</span>
    </header>
    <main id="main" className="workspace" tabIndex={-1}>
      <p className="breadcrumb">상권 분석 / {route.view === 'map' ? '관심 상권 선택' : route.view === 'detail' ? '상세 상권 분석' : '후보 상권 비교'}</p>
      {route.view === 'detail' && route.codes.length > 0 && <button className="back-link" onClick={() => navigate({ ...route, view: 'comparison', section: section === 'location' ? 'rent' : section })}>후보 상권 비교로 돌아가기</button>}
      <div className="page-heading"><div><h1>{route.view === 'map' ? '어떤 상권을 비교해 볼까요?' : route.view === 'detail' ? (detailCode ? `${areas.find(a => a.code === detailCode)?.name || ''} 상세분석` : '상세 상권 분석') : '후보 상권 비교'}</h1><p>{route.view === 'map' ? `지도에서 관심 있는 상권을 최대 ${MAX_CANDIDATES}개까지 선택하세요.` : route.view === 'comparison' ? '관심 있는 상권의 카페를 같은 기준으로 비교해 보세요.' : '선택한 상권의 흐름과 주변 정보를 확인하세요.'}</p></div><div className="context-controls"><label className="sr-only" htmlFor="industry">업종</label><select id="industry" aria-label="업종"><option>카페</option></select><span className="analysis-period">분석 시점 : {analysisYear}년 {analysisQuarter}분기</span><span className="badge demo-badge">{isDemo ? '개발용 가상 분석' : '서울시 상권 통계'}</span></div></div>
      {route.view !== 'map' && <div className="notice info">{isDemo ? '상권 위치를 제외한 분석과 입지 자료는 개발용 가상 예시입니다.' : '매출, 거래, 점포와 유동인구는 서울시 상권 통계입니다. 임대 광고와 카페 메뉴는 수집 시점의 공개 자료입니다.'}</div>}
      {notice && <p className="notice alert" role="alert">{notice}</p>}
      {route.view !== 'detail' && <div className="candidate-toolbar"><div className="candidate-chips" aria-label="선택한 후보 상권">{selected.map((area, i) => <span className="candidate-chip" key={area.code}><b>{i + 1}</b>{area.name}{route.view === 'map' ? <button aria-label={`${area.name} 선택 해제`} onClick={() => toggle(area.code)}>×</button> : <button aria-label={`${area.name} 상세 보기`} onClick={() => openDetail(area.code)}>↗</button>}</span>)}{!selected.length && <span className="muted">아직 선택한 후보가 없습니다.</span>}</div><span className="muted">{route.codes.length} / {MAX_CANDIDATES}개</span>{route.view !== 'map' && <button onClick={() => navigate({ ...route, view: 'map' })}>후보 변경</button>}</div>}
      {route.view === 'map' ? <>
        <MapPicker areas={areas} selected={route.codes} onToggle={toggle} />
        <div className="map-actions"><button className="primary" disabled={!route.codes.length} onClick={() => openComparison('competition')}>선택한 {route.codes.length}개 상권 비교하기</button></div>
      </> : route.view === 'detail' && !detailCode ? <DetailAreaPicker areas={areas} selectedCode="" suggestedCodes={config.demo_area_codes} onSelect={code => openDetail(code, 'profitability')} />
        : route.view === 'comparison' && !route.codes.length ? <div className="panel"><p>비교할 상권을 먼저 선택하세요.</p><button onClick={() => navigate({ ...route, view: 'map' })}>상권 선택</button></div> : <>
        <nav className="section-tabs" aria-label="분석 항목">{tabs.map(tab => <button key={tab} className={section === tab ? 'active' : ''} aria-current={section === tab ? 'page' : undefined} onClick={() => navigate({ ...route, section: tab })}>{sectionLabels[tab]}</button>)}</nav>
        {demoCommentary && <div className="explanation-jump"><button onClick={() => {
          const title = document.getElementById('explanation-title');
          title?.closest('section')?.scrollIntoView({ block: 'start' });
          title?.focus({ preventScroll: true });
        }}>AI 상권 해설 바로 보기 ↓</button></div>}
        {route.view === 'detail' && <DetailAreaPicker areas={areas} selectedCode={detailCode} suggestedCodes={route.codes} onSelect={code => openDetail(code)} compact />}
        {loading && <p role="status" className="panel">분석 자료를 불러오고 있습니다.</p>}
        {error && <div role="alert" className="notice alert">{error} <button onClick={() => setLoadVersion(v => v + 1)}>다시 시도</button></div>}
        {!loading && comparison && route.view === 'comparison' && <>
          <div className="section-title"><div><h2>{section === 'profitability' ? '점포당 평균 매출 비교' : section === 'competition' ? '선택한 상권의 주요 지표 비교' : section === 'demand' ? '총 거래 건수와 평균 결제금액 비교' : '같은 면적 기준 임대료와 매출 대비 비율'}</h2><p className="muted">{section === 'rent' ? '기준 면적과 층 조건을 설정해 후보 상권을 비교하세요.' : section === 'competition' ? quarterLabel(comparison.meta.quarter) + ' 기준 (전년 동분기 대비)' : '분기 기준 / 변화율은 전년 동분기 대비'}</p></div></div>
          {section === 'competition' ? <OverviewComparison comparison={comparison} open={openDetail} />
            : section === 'profitability' ? <ComparisonCarousel>{comparison.items.map(item =>
              <ComparisonCard key={item.area.code} item={item} maximum={Math.max(...comparison.items.map(i => i.metrics?.average_sales_krw || 0))} open={() => openDetail(item.area.code)} />
            )}</ComparisonCarousel>
            : section === 'demand' ? <DemandComparison items={comparison.items} open={code => openDetail(code)} />
            : <RentComparison items={comparison.items} open={code => openDetail(code, 'rent')} areaPyeong={areaPyeong} setAreaPyeong={setAreaPyeong} floor={floor} setFloor={setRentalFloor} demo={isDemo} />}
          {section !== 'rent' && section !== 'competition' && <div className="notice info">평균 매출은 같은 상권, 업종, 분기의 총매출을 점포 수로 나눈 값입니다. 개별 점포의 매출과 다를 수 있으며 일부 점포에 매출이 집중될 수 있습니다.</div>}
        </>}
        {!loading && detail && route.view === 'detail' && (detail.current || section === 'demand' || section === 'location' ? <>
          {detail.current && section === 'profitability' && <SalesDetail detail={detail} current={detail.current} recent={recent} setRecent={setRecent} />}
          {section === 'demand' && <><div className="segmented sub-tabs"><button className={demandMetric === 'transactions' ? 'active' : ''} onClick={() => setDemandMetric('transactions')}>거래 건수</button><button className={demandMetric === 'floating_population' ? 'active' : ''} onClick={() => setDemandMetric('floating_population')}>유동인구</button></div>{detail.demand[demandMetric] ? <><section className="panel metric-summary"><div><h2>누가, 언제 {demandMetric === 'transactions' ? '결제하고' : '지나고'} 있을까요?</h2><p className="muted">2026년 2분기 / 카페 기준 거래와 상권 전체 유동인구는 서로 다른 자료입니다.</p></div>{demandMetric === 'transactions' && <div><span>분기 총거래 건수</span><strong>{detail.current?.transaction_count == null ? '자료 없음' : number(detail.current.transaction_count) + '건'}</strong></div>}</section><DemandCharts distribution={detail.demand[demandMetric]} /></> : <p className="panel">해당 분포 자료가 없습니다.</p>}<p className="notice info">거래 건수는 고유 고객 수와 다르며, 유동인구는 카페 구매자 수와 다릅니다. 요일은 일평균, 연령과 시간대는 분기 합계입니다.</p></>}
          {section === 'location' && <>
            <div className="segmented sub-tabs"><button className={locationView === 'rentals' ? 'active' : ''} onClick={() => setLocationView('rentals')}>임대매물</button><button className={locationView === 'stores' ? 'active' : ''} onClick={() => setLocationView('stores')}>주변 점포</button></div>
            {locationView === 'stores' && detail.rentals.length > 0 && <div className="panel location-filter">
              <label>카페 조회 기준<select value={listingId} onChange={e => setListingId(e.target.value)}>
                <option value="">상권 안의 카페</option>
                {detail.rentals.map(r => <option key={r.id} value={r.id}>{[r.title, r.floor].filter(Boolean).join(' / ')}</option>)}
              </select></label>
              {listingId && <label>탐색 반경<select value={radius} onChange={e => setRadius(Number(e.target.value) as 100 | 300 | 500)}>{[100, 300, 500].map(r => <option key={r} value={r}>{r}m</option>)}</select></label>}
            </div>}
            <div className="location-layout">
              <aside className="panel location-list">{locationView === 'rentals' ? <>
                <h2>{isDemo ? '예시 매물' : '임대 매물'} {detail.rentals.length}건</h2>
                <RentalList rentals={detail.rentals} selectedId={listingId} select={selectListing} nearby={() => setLocationView('stores')} />
              </> : <>
                <h2>{listingId ? `반경 ${radius}m 내 카페` : '상권 안의 카페'}{(!listingId || (nearbyResult && !nearbyResult.error)) && ` ${stores.length}곳`}</h2>
                {nearbyResult?.error && listingId ? <p role="alert">{nearbyResult.error}</p> :
                  listingId && !nearbyResult ? <p role="status">주변 카페를 불러오는 중입니다.</p> :
                  stores.length === 0 ? <p className="muted">이 범위에서 수집된 카페가 없습니다.</p> :
                  stores.map(store => <StoreCard key={store.id} store={store} />)}
              </>}</aside>
              <LocationMap area={detail.area} rentals={locationView === 'stores' ? detail.rentals.filter(r => r.id === listingId) : detail.rentals} stores={locationView === 'stores' ? stores : NO_STORES} selectedId={listingId} radius={locationView === 'stores' && listingId ? radius : undefined} onSelect={selectListing} demo={isDemo} />
            </div>
          </>}
        </> : <div className="panel"><h2>이 분기의 카페 자료 없음</h2><p>{detail.missing_reason}</p><p>자료가 없다는 뜻이며 매출이나 점포 수가 0이라는 뜻은 아닙니다.</p></div>)}
        {!loading && (comparison || detail) && <>
          {!demoCommentary && config.llm_auth_required && <label className="auth-input">해설 서비스 접근 인증<input type="password" value={accessToken} autoComplete="off" onChange={e => setAccessToken(e.target.value)} placeholder="접근 토큰, 이 화면의 메모리에만 보관" /></label>}
          {demoCommentary ? <DemoExplanationPanel {...demoCommentary} reportLayout={section === 'profitability'} />
            : !(route.view === 'detail' && section === 'location' && locationView === 'stores' && !listingId) &&
              <ExplanationPanel request={context} config={config} accessToken={accessToken} />}
          <details className="panel methods"><summary>계산 근거와 자료 기준 보기</summary><p>금액의 원래 단위는 원입니다. 점포당 평균 매출 = 분기 총매출 ÷ 같은 분기 카페 점포 수, 점포당 거래 건수 = 총거래 건수 ÷ 점포 수, 건당 평균 결제금액 = 총매출 ÷ 총거래 건수입니다.</p><p>전년 동분기 대비 변화율 = (현재 값 ÷ 1년 전 같은 분기 값 - 1) × 100입니다. 분모가 0이거나 자료가 없으면 값을 계산하지 않습니다.</p><p>종합해설의 평균 여건은 매출과 거래 건수의 변화율을 점포 수 변화율과 각각 비교합니다. 상권의 성장만으로 점포당 평균 여건의 개선을 판단하지 않습니다. 임대료는 매물의 면적당 월세를 설정 면적으로 환산하고, 점포당 분기 평균 매출을 3으로 나눈 월 환산값과 비교합니다.</p></details>
        </>}
      </>}
      <footer>상권 평균과 예측은 개별 신규점의 매출이나 창업 성공을 보장하지 않습니다. 실제 판단에는 현장 확인과 추가 자료 검토가 필요합니다.</footer>
    </main>
    <dialog ref={comparisonDialog} className="comparison-loading" aria-labelledby="comparison-loading-title"
      onCancel={event => event.preventDefault()}>
      <span className="comparison-loading-spinner" aria-hidden="true" />
      <p id="comparison-loading-title" role="status">상권 비교를 준비하고 있어요</p>
    </dialog>
  </>;
}

function ComparisonCard({ item, maximum, open }: { item: ComparisonItem; maximum: number; open: () => void }) {
  const metric = item.metrics;
  return <article className="panel comparison-card">
    <h3>{item.area.name}</h3><p className="muted">{item.area.district} / {item.area.administrative_dong}</p>
    {metric ? <><p>카페 1곳당 분기 평균</p><div className="large-value">{metric.average_sales_krw == null ? '자료 없음' : <>{number(metric.average_sales_krw / 10000)}<span>만 원</span></>}</div>
      <div className="change-line"><Change value={metric.average_sales_yoy_pct} /><span>전년 동분기 대비</span></div>
      <MetricBar value={metric.average_sales_krw} maximum={maximum} /><p className="bar-basis">선택한 전체 후보 중 최대값 기준</p>
      <dl className="calculation"><dt>상권 총매출</dt><dd>{money(metric.total_sales_krw)}</dd><dt>카페 점포 수</dt><dd>{number(metric.store_count)}개</dd></dl>
      <p className="formula">{money(metric.total_sales_krw)} ÷ {number(metric.store_count)}개</p>
    </> : <p>{item.missing_reason}</p>}<AreaDetailButton areaName={item.area.name} onClick={open} />
  </article>;
}

function DemandComparison({ items, open }: { items: ComparisonItem[]; open: (code: string) => void }) {
  const maxTransactions = Math.max(1, ...items.map(i => i.metrics?.transaction_count || 0));
  const maxPayment = Math.max(1, ...items.map(i => i.metrics?.average_payment_krw || 0));
  return <div className="panel table-scroll"><table className="demand-table"><thead><tr><th>상권</th><th>총 거래 건수 (건/분기)</th><th>건당 평균 결제금액 (원)</th></tr></thead><tbody>{items.map(item => <tr key={item.area.code}><th scope="row"><span className="demand-area-name">{item.area.name}</span><small>점포당 거래 {number(item.metrics?.transactions_per_store, 1)}건 / 점포 {number(item.metrics?.store_count)}개</small><AreaDetailButton areaName={item.area.name} onClick={() => open(item.area.code)} /></th><td><MetricBar value={item.metrics?.transaction_count ?? null} maximum={maxTransactions} /><strong>{number(item.metrics?.transaction_count)}{item.metrics?.transaction_count != null ? '건' : ''}</strong></td><td><MetricBar value={item.metrics?.average_payment_krw ?? null} maximum={maxPayment} /><strong>{number(item.metrics?.average_payment_krw)}{item.metrics?.average_payment_krw != null ? '원' : ''}</strong></td></tr>)}</tbody></table></div>;
}
function RentalList({ rentals, selectedId, select, nearby }: { rentals: Detail['rentals']; selectedId?: string; select?: (id: string) => void; nearby?: () => void }) {
  return <div className="rental-list">{rentals.map(r => <article key={r.id} className={`rental-item ${selectedId === r.id ? 'selected' : ''}`}>
    {select ? <button className="rental-name" onClick={() => select(r.id)} aria-pressed={selectedId === r.id}>{r.title}</button> : <h3>{r.title}</h3>}
    <strong className="rent-price">월세 {listingMoney(r.monthly_rent_krw)}</strong>
    <p>보증금 {listingMoney(r.deposit_krw)}</p>
    <p>{r.area_m2 == null ? '면적 미확보' : `${number(r.area_m2, 1)}㎡`} / {r.floor || '층 미확보'}</p>
    <small>{[r.source_name, `확인일 ${r.observed_at.slice(0, 10)}`].filter(Boolean).join(' / ')}</small>
    {r.maintenance_fee_krw != null && <p>관리비 {listingMoney(r.maintenance_fee_krw)}</p>}
    {r.is_transfer && <small>권리금 매물의 월세 및 보증금입니다.</small>}
    {r.source_url && <a href={r.source_url} target="_blank" rel="noopener noreferrer">광고 원문 보기</a>}
    {nearby && selectedId === r.id && <button className="primary" onClick={nearby}>이 매물 주변 점포 보기 →</button>}
  </article>)}{!rentals.length && <p className="muted">이 상권에서 수집된 임대 매물이 없습니다.</p>}</div>;
}
