import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { DemandCharts, TrendChart } from './Charts';
import ExplanationPanel from './ExplanationPanel';
import RentComparison from './RentComparison';
import MapPicker, { LocationMap } from './MapPicker';
import { toggleCandidate, visibleCandidates } from './selection.mjs';
import type { Area, Comparison, ComparisonItem, Config, Detail, Section, Store } from './types';

type Route = { view: 'map' | 'comparison' | 'detail'; section: Section; codes: string[]; code: string };
const sectionLabels: Record<Section, string> = { profitability: '수익성', competition: '경쟁 상황', demand: '수요성', rent: '임대료', location: '입지와 주변 환경' };
const number = (value: number | null | undefined, digits = 0) => value == null ? '자료 없음' : value.toLocaleString('ko-KR', { maximumFractionDigits: digits });
const money = (value: number | null | undefined) => value == null ? '미확보' : `${number(value / 10000)}만 원`;

function parseRoute(): Route {
  const params = new URLSearchParams(location.hash.slice(1));
  const view = params.get('view');
  const section = params.get('section');
  return { view: view === 'comparison' || view === 'detail' ? view : 'map', section: section && section in sectionLabels ? section as Section : 'profitability',
    codes: [...new Set((params.get('areas') || '').split(',').filter(Boolean))].slice(0, 5), code: params.get('area') || '' };
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
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [width, setWidth] = useState(window.innerWidth < 760 ? 1 : window.innerWidth < 1100 ? 2 : 3);
  const [recent, setRecent] = useState(true);
  const [demandMetric, setDemandMetric] = useState<'transactions' | 'floating_population'>('transactions');
  const [locationView, setLocationView] = useState<'rentals' | 'stores'>('rentals');
  const [listingId, setListingId] = useState('');
  const [radius, setRadius] = useState<100 | 300 | 500>(300);
  const [stores, setStores] = useState<Store[]>([]);
  const [nearbyError, setNearbyError] = useState('');
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
    setNotice(''); setRoute(next); setOffset(0);
    const params = new URLSearchParams({ view: next.view, section: next.section, areas: next.codes.join(','), area: next.code });
    history.pushState(null, '', `#${params}`);
  }, []);
  useEffect(() => {
    const back = () => { setRoute(parseRoute()); setOffset(0); };
    window.addEventListener('popstate', back); window.addEventListener('hashchange', back);
    return () => { window.removeEventListener('popstate', back); window.removeEventListener('hashchange', back); };
  }, []);
  useEffect(() => {
    const resize = () => setWidth(window.innerWidth < 760 ? 1 : window.innerWidth < 1100 ? 2 : 3);
    window.addEventListener('resize', resize); return () => window.removeEventListener('resize', resize);
  }, []);

  const codesKey = route.codes.join(',');
  useEffect(() => {
    if (!config || route.view === 'map' || !route.codes.length) return;
    let active = true;
    const controller = new AbortController();
    const started = performance.now();
    setLoading(true); setError(''); setDetail(null); setComparison(null);
    const promise = route.view === 'detail'
      ? api<Detail>(`/areas/${encodeURIComponent(route.code || route.codes[0])}/analysis`, { signal: controller.signal })
      : api<Comparison>('/comparisons', { method: 'POST', body: JSON.stringify({ area_codes: route.codes }), signal: controller.signal });
    promise.then(result => {
      if (!active) return;
      if ('observations' in result) { setDetail(result); setListingId(result.rentals[0]?.id || ''); }
      else setComparison(result);
      requestAnimationFrame(() => { if (active) performance.measure('ui:charts-ready', { start: started, end: performance.now() }); });
    }).catch(err => { if (active && err.name !== 'AbortError') setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
    // Section changes reuse the same data payload while changing the commentary context.
  }, [config, route.view, route.code, codesKey, loadVersion]);

  useEffect(() => {
    if (route.view !== 'detail' || route.section !== 'location' || locationView !== 'stores' || !listingId || !detail) return;
    let active = true;
    const controller = new AbortController();
    setStores([]); setNearbyError('');
    api<Store[]>(`/areas/${detail.area.code}/nearby-stores?listing_id=${encodeURIComponent(listingId)}&radius_m=${radius}`, { signal: controller.signal })
      .then(values => { if (active) setStores(values); })
      .catch(err => { if (active && err.name !== 'AbortError') setNearbyError(err.message); });
    return () => { active = false; controller.abort(); };
  }, [detail, listingId, radius, locationView, route.view, route.section]);

  const toggle = useCallback((code: string) => {
    setRoute(previous => {
      try { const codes = toggleCandidate(previous.codes, code); setNotice(''); return { ...previous, codes }; }
      catch (err) { setNotice((err as Error).message); return previous; }
    });
  }, []);
  const selectListing = useCallback((id: string) => setListingId(id), []);
  const openDetail = (code: string, section = route.section) => navigate({ ...route, view: 'detail', code, section: section === 'rent' ? 'location' : section });
  const tabs: Section[] = ['profitability', 'competition', 'demand', route.view === 'detail' ? 'location' : 'rent'];
  const section = tabs.includes(route.section) ? route.section : 'profitability';
  const selected = areas.filter(a => route.codes.includes(a.code)).sort((a, b) => route.codes.indexOf(a.code) - route.codes.indexOf(b.code));
  const visible = visibleCandidates(comparison?.items || [], offset, width);
  const [first, last] = [visible.start + 1, Math.min((comparison?.items.length || 0), visible.start + width)];
  const context: Record<string, unknown> = { scope: route.view === 'detail' ? 'detail' : 'comparison', section,
    area_codes: route.view === 'detail' ? [detail?.area.code || route.code] : [...route.codes].sort(), quarter: '2026Q2' };
  if (route.view === 'detail' && section === 'demand') context.demand_metric = demandMetric;
  if (route.view === 'detail' && section === 'location') Object.assign(context, { location_view: locationView, listing_id: locationView === 'stores' ? listingId || null : null, radius_m: radius });

  if (!config) return <main className="startup"><h1>상권 분석</h1>{error ? <><p role="alert">서버에 연결하지 못했습니다: {error}</p><button onClick={() => setLoadVersion(v => v + 1)}>다시 연결</button></> : <p>상권 위치 목록을 불러오고 있습니다.</p>}</main>;

  const isDemo = config.data_mode === 'demo';
  return <>
    <a className="skip-link" href="#main" onClick={event => { event.preventDefault(); document.getElementById('main')?.focus(); }}>본문으로 이동</a>
    <header className="site-header"><button className="brand" onClick={() => navigate({ ...route, view: 'map' })}><span className="brand-pin" aria-hidden="true">⌖</span> 상권 분석</button><nav aria-label="주 메뉴"><button className={route.view === 'map' ? 'active' : ''} onClick={() => navigate({ ...route, view: 'map' })}>상권 탐색</button><button className={route.view === 'comparison' ? 'active' : ''} disabled={!route.codes.length} onClick={() => navigate({ ...route, view: 'comparison', section: section === 'location' ? 'rent' : section })}>후보 상권 비교</button>{route.view === 'detail' && <button className="active">상권 상세분석</button>}</nav><span className="header-meta">DATA TADA</span></header>
    <main id="main" className="workspace" tabIndex={-1}>
      <p className="breadcrumb">상권 분석 / {route.view === 'map' ? '관심 상권 선택' : route.view === 'detail' ? '상권 상세분석' : '후보 상권 비교'}</p>
      {route.view === 'detail' && <button className="back-link" onClick={() => navigate({ ...route, view: 'comparison', section: section === 'location' ? 'rent' : section })}>← 후보 상권 비교로 돌아가기</button>}
      <div className="page-heading"><div><h1>{route.view === 'map' ? '어떤 상권을 비교해 볼까요?' : route.view === 'detail' ? `${detail?.area.name || areas.find(a => a.code === route.code)?.name || ''} 상세분석` : '후보 상권 비교'}</h1><p>{route.view === 'map' ? '지도에서 관심 있는 상권을 최대 5개까지 선택하세요.' : route.view === 'comparison' ? '관심 있는 상권의 카페를 같은 기준으로 비교해 보세요.' : '선택한 상권의 흐름과 주변 정보를 확인하세요.'}</p></div><div className="context-controls"><label className="sr-only" htmlFor="industry">업종</label><select id="industry" aria-label="업종"><option>카페</option></select><select aria-label="기준 분기"><option>2026년 2분기</option></select><span className="badge demo-badge">{isDemo ? '개발용 가상 분석' : '서울시 상권 통계'}</span></div></div>
      <div className="notice info">{isDemo ? '상권 위치를 제외한 분석과 입지 자료는 개발용 가상 예시입니다.' : '매출, 거래, 점포와 유동인구는 서울시 상권 통계입니다. 예측은 Ridge 기준 모델 결과이며 매물과 메뉴는 발표용 가상 예시입니다.'}</div>
      {notice && <p className="notice alert" role="alert">{notice}</p>}
      <div className="candidate-toolbar"><div className="candidate-chips" aria-label="선택한 후보 상권">{selected.map((area, i) => <span className="candidate-chip" key={area.code}><b>{i + 1}</b>{area.name}{route.view === 'map' ? <button aria-label={`${area.name} 선택 해제`} onClick={() => toggle(area.code)}>×</button> : <button aria-label={`${area.name} 상세 보기`} onClick={() => openDetail(area.code)}>↗</button>}</span>)}{!selected.length && <span className="muted">아직 선택한 후보가 없습니다.</span>}</div><span className="muted">{route.codes.length} / 5개</span>{route.view !== 'map' && <button onClick={() => navigate({ ...route, view: 'map' })}>후보 변경</button>}</div>
      {route.view === 'map' ? <>
        <MapPicker areas={areas} selected={route.codes} onToggle={toggle} />
        <div className="map-actions"><button className="primary" disabled={!route.codes.length} onClick={() => navigate({ ...route, view: 'comparison', section: 'profitability' })}>선택한 {route.codes.length}개 상권 비교하기 →</button></div>
      </> : !route.codes.length ? <div className="panel"><p>비교할 상권을 먼저 선택하세요.</p><button onClick={() => navigate({ ...route, view: 'map' })}>상권 선택</button></div> : <>
        <nav className="section-tabs" aria-label="분석 항목">{tabs.map(tab => <button key={tab} className={section === tab ? 'active' : ''} aria-current={section === tab ? 'page' : undefined} onClick={() => navigate({ ...route, section: tab })}>{sectionLabels[tab]}</button>)}</nav>
        {route.view === 'detail' && <label className="detail-area-switch">다른 후보 상세 보기<select value={route.code || route.codes[0]} onChange={e => openDetail(e.target.value)}>{selected.map(a => <option key={a.code} value={a.code}>{a.name}</option>)}</select></label>}
        {loading && <p role="status" className="panel">분석 자료를 불러오고 있습니다.</p>}
        {error && <div role="alert" className="notice alert">{error} <button onClick={() => setLoadVersion(v => v + 1)}>다시 시도</button></div>}
        {!loading && comparison && route.view === 'comparison' && <>
          <div className="section-title"><div><h2>{section === 'profitability' ? '점포당 평균 매출' : section === 'competition' ? '상권의 변화와 경쟁 상황' : section === 'demand' ? '거래 규모와 결제금액 한눈에 비교' : '발표용 임대 매물 조건 비교'}</h2><p className="muted">{section === 'rent' ? '발표용으로 만든 매물의 보증금, 월세와 면적을 비교합니다.' : '분기 기준 / 변화율은 전년 동분기 대비'}</p></div>{(section === 'profitability' || section === 'competition') && <div className="carousel-controls"><button aria-label="이전 후보 카드" disabled={visible.start === 0} onClick={() => setOffset(visible.start - 1)}>←</button><span aria-live="polite">{first}~{last} / 전체 {comparison.items.length}개</span><button aria-label="다음 후보 카드" disabled={last >= comparison.items.length} onClick={() => setOffset(visible.start + 1)}>→</button></div>}</div>
          {section === 'profitability' || section === 'competition' ? <div className="comparison-cards">{visible.values.map(item => <ComparisonCard key={item.area.code} item={item} section={section} maximum={Math.max(...comparison.items.map(i => i.metrics?.average_sales_krw || 0))} open={() => openDetail(item.area.code)} />)}</div> : section === 'demand' ? <DemandComparison items={comparison.items} open={code => openDetail(code)} /> : <RentComparison items={comparison.items} open={code => openDetail(code, 'rent')} />}
          {section !== 'rent' && <div className="notice info">평균 매출은 같은 상권, 업종, 분기의 총매출을 점포 수로 나눈 값입니다. 개별 점포의 매출과 다를 수 있으며 일부 점포에 매출이 집중될 수 있습니다.</div>}
        </>}
        {!loading && detail && route.view === 'detail' && (detail.current || section === 'demand' || section === 'location' ? <>
          {detail.current && (section === 'profitability' || section === 'competition') && <>
            <section className="panel metric-summary">{section === 'profitability' ? <><div><span>최근 분기 점포당 평균 매출</span><strong>{money(detail.current.average_sales_krw)}</strong><Change value={detail.current.average_sales_yoy_pct} /></div><div><span>다음 분기 점포당 예상 매출</span><strong>{money(detail.forecast?.points[0]?.average_sales_krw)}</strong><span className="badge">{isDemo ? '가상 예측' : 'Ridge 기준 예측'}</span></div></> : <><div className="type-block"><span>현재 상권 유형</span><strong>{detail.current.competition_type}</strong></div><div><span>총매출 변화율</span><Change value={detail.current.sales_yoy_pct} /></div><div><span>점포 수 변화율</span><Change value={detail.current.stores_yoy_pct} /></div></>}</section>
            <section className="panel"><div className="section-title"><h2>{section === 'profitability' ? '점포당 평균 매출 추세' : '총매출과 점포 수 변화율 추세'}</h2><div className="segmented"><button className={recent ? 'active' : ''} onClick={() => setRecent(true)}>최근 3년</button><button className={!recent ? 'active' : ''} onClick={() => setRecent(false)}>전체</button></div></div><TrendChart detail={detail} competition={section === 'competition'} recent={recent} /></section>
            {detail.forecast && <div className="notice info">{isDemo ? '점선과 80%/90% 음영은 화면 검증용 가상 예측입니다.' : detail.forecast.interval_method}</div>}
          </>}
          {section === 'demand' && <><div className="segmented sub-tabs"><button className={demandMetric === 'transactions' ? 'active' : ''} onClick={() => setDemandMetric('transactions')}>거래 건수</button><button className={demandMetric === 'floating_population' ? 'active' : ''} onClick={() => setDemandMetric('floating_population')}>유동인구</button></div>{detail.demand[demandMetric] ? <><section className="panel metric-summary"><div><h2>누가, 언제 {demandMetric === 'transactions' ? '결제하고' : '지나고'} 있을까요?</h2><p className="muted">2026년 2분기 / 카페 기준 거래와 상권 전체 유동인구는 서로 다른 자료입니다.</p></div>{demandMetric === 'transactions' && <div><span>분기 총거래 건수</span><strong>{detail.current?.transaction_count == null ? '자료 없음' : number(detail.current.transaction_count) + '건'}</strong></div>}</section><DemandCharts distribution={detail.demand[demandMetric]} /></> : <p className="panel">해당 분포 자료가 없습니다.</p>}<p className="notice info">거래 건수는 고유 고객 수와 다르며, 유동인구는 카페 구매자 수와 다릅니다. 요일은 일평균, 연령과 시간대는 분기 합계입니다.</p></>}
          {section === 'location' && <>
            <div className="segmented sub-tabs"><button className={locationView === 'rentals' ? 'active' : ''} onClick={() => setLocationView('rentals')}>임대매물</button><button className={locationView === 'stores' ? 'active' : ''} onClick={() => setLocationView('stores')}>주변 점포</button></div>
            {locationView === 'stores' && <div className="panel location-filter"><label>기준 매물<select value={listingId} onChange={e => setListingId(e.target.value)}>{detail.rentals.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select></label><label>탐색 반경<select value={radius} onChange={e => setRadius(Number(e.target.value) as 100 | 300 | 500)}>{[100, 300, 500].map(r => <option key={r} value={r}>{r}m</option>)}</select></label></div>}
            {nearbyError && locationView === 'stores' && <p className="notice alert" role="alert">{nearbyError}</p>}
            <div className="location-layout"><aside className="panel location-list">{locationView === 'rentals' ? <><h2>예시 매물 {detail.rentals.length}개</h2><RentalList rentals={detail.rentals} selectedId={listingId} select={selectListing} nearby={() => setLocationView('stores')} /></> : <><h2>반경 {radius}m 내 예시 카페 {stores.length}곳</h2>{stores.map(store => <article key={store.id} className="store-row"><h3>{store.name}</h3><small>{number(store.distance_m)}m / 확인일 {store.observed_at}</small>{store.menu.length ? store.menu.map(menu => <p key={menu.name}>{menu.name}<strong>{menu.price_krw == null ? '가격 미확보' : `${number(menu.price_krw)}원`}</strong></p>) : <p className="muted">메뉴와 가격 미확보</p>}</article>)}{!listingId && <p>먼저 기준 매물을 선택하세요.</p>}</>}</aside><LocationMap area={detail.area} rentals={locationView === 'stores' ? detail.rentals.filter(r => r.id === listingId) : detail.rentals} stores={locationView === 'stores' ? stores : []} selectedId={listingId} radius={locationView === 'stores' ? radius : undefined} onSelect={selectListing} /></div>
          </>}
        </> : <div className="panel"><h2>이 분기의 카페 자료 없음</h2><p>{detail.missing_reason}</p><p>자료가 없다는 뜻이며 매출이나 점포 수가 0이라는 뜻은 아닙니다.</p></div>)}
        {!loading && (comparison || detail) && <>
          <details className="panel methods"><summary>계산 근거와 자료 기준 보기</summary><p>금액의 원래 단위는 원입니다. 점포당 평균 매출 = 분기 총매출 ÷ 같은 분기 카페 점포 수, 점포당 거래 건수 = 총거래 건수 ÷ 점포 수, 건당 평균 결제금액 = 총매출 ÷ 총거래 건수입니다.</p><p>전년 동분기 대비 변화율 = (현재 값 ÷ 1년 전 같은 분기 값 - 1) × 100입니다. 분모가 0이거나 자료가 없으면 값을 계산하지 않습니다. 임대광고 조건은 환산하거나 평균 매출과 비율로 결합하지 않습니다.</p><p>미래 경쟁 유형을 확정하지 않습니다. 현재 유형은 총매출과 점포 수 변화의 부호를 조합하며, 한쪽이 0이면 경계로 표시합니다. 경쟁 사분면은 사용자 화면에 표시하지 않습니다.</p></details>
          {config.llm_auth_required && <label className="auth-input">해설 서비스 접근 인증<input type="password" value={accessToken} autoComplete="off" onChange={e => setAccessToken(e.target.value)} placeholder="접근 토큰, 이 화면의 메모리에만 보관" /></label>}
          {!(route.view === 'detail' && section === 'location' && locationView === 'stores' && !listingId) && <ExplanationPanel request={context} config={config} accessToken={accessToken} />}
        </>}
      </>}
      <footer>상권 평균과 예측은 개별 신규점의 매출이나 창업 성공을 보장하지 않습니다. 실제 판단에는 현장 확인과 추가 자료 검토가 필요합니다.</footer>
    </main>
  </>;
}

function ComparisonCard({ item, section, maximum, open }: { item: ComparisonItem; section: Section; maximum: number; open: () => void }) {
  const metric = item.metrics;
  return <article className="panel comparison-card"><h3><span aria-hidden="true">⌖</span> {item.area.name}</h3><p className="muted">{item.area.district} / {item.area.administrative_dong}</p>{metric ? section === 'profitability' ? <><p>카페 1곳당 분기 평균</p><div className="large-value">{metric.average_sales_krw == null ? '자료 없음' : <>{number(metric.average_sales_krw / 10000)}<span>만 원</span></>}</div><div className="change-line"><Change value={metric.average_sales_yoy_pct} /><span>전년 동분기 대비</span></div><MetricBar value={metric.average_sales_krw} maximum={maximum} /><p className="bar-basis">선택한 전체 후보 중 최대값 기준</p><dl className="calculation"><dt>상권 총매출</dt><dd>{money(metric.total_sales_krw)}</dd><dt>카페 점포 수</dt><dd>{number(metric.store_count)}개</dd></dl><p className="formula">{money(metric.total_sales_krw)} ÷ {number(metric.store_count)}개</p></> : <><div className={`type-block ${metric.sales_yoy_pct != null && metric.sales_yoy_pct < 0 ? 'warm' : ''}`}><strong>{metric.competition_type}</strong><span>총매출과 점포 수 변화의 조합</span></div><div className="competition-changes"><div><p>총매출 변화율</p><Change value={metric.sales_yoy_pct} /></div><div><p>점포 수 변화율</p><Change value={metric.stores_yoy_pct} /></div></div><dl className="calculation"><dt>점포당 평균 매출</dt><dd>{money(metric.average_sales_krw)}</dd></dl></> : <p>{item.missing_reason}</p>}<button className="text-link" onClick={open}>이 상권의 추세 자세히 보기 →</button></article>;
}

function DemandComparison({ items, open }: { items: ComparisonItem[]; open: (code: string) => void }) {
  const maxTransactions = Math.max(1, ...items.map(i => i.metrics?.transactions_per_store || 0));
  const maxPayment = Math.max(1, ...items.map(i => i.metrics?.average_payment_krw || 0));
  return <div className="panel table-scroll"><table className="demand-table"><thead><tr><th>상권</th><th>점포당 거래 건수 (건/분기)</th><th>건당 평균 결제금액 (원)</th></tr></thead><tbody>{items.map(item => <tr key={item.area.code}><th><button onClick={() => open(item.area.code)}>{item.area.name} ↗</button><small>{item.metrics?.transaction_count == null ? '거래 자료 없음' : '총 ' + number(item.metrics.transaction_count) + '건'} / 점포 {number(item.metrics?.store_count)}</small></th><td><MetricBar value={item.metrics?.transactions_per_store ?? null} maximum={maxTransactions} /><strong>{number(item.metrics?.transactions_per_store, 1)}{item.metrics?.transactions_per_store != null ? '건' : ''}</strong></td><td><MetricBar value={item.metrics?.average_payment_krw ?? null} maximum={maxPayment} /><strong>{number(item.metrics?.average_payment_krw)}{item.metrics?.average_payment_krw != null ? '원' : ''}</strong></td></tr>)}</tbody></table></div>;
}

function RentalList({ rentals, selectedId, select, nearby }: { rentals: Detail['rentals']; selectedId?: string; select?: (id: string) => void; nearby?: () => void }) {
  return <div className="rental-list">{rentals.map(r => <article key={r.id} className={`rental-item ${selectedId === r.id ? 'selected' : ''}`}>
    {select ? <button className="rental-name" onClick={() => select(r.id)} aria-pressed={selectedId === r.id}>{r.title}</button> : <h3>{r.title}</h3>}<strong className="rent-price">월세 {money(r.monthly_rent_krw)}</strong><p>보증금 {money(r.deposit_krw)}</p><p>{r.area_m2 == null ? '면적 미확보' : `${number(r.area_m2, 1)}㎡`} / {r.floor || '층 미확보'}</p><small>관리비 {money(r.maintenance_fee_krw)} / 확인일 {r.observed_at}</small>{r.source_url && <a href={r.source_url} target="_blank" rel="noreferrer">광고 원문 보기</a>}{nearby && selectedId === r.id && <button className="primary" onClick={nearby}>이 매물 주변 점포 보기 →</button>}
  </article>)}{!rentals.length && <p className="muted">이 상권에는 발표용 매물 예시가 없습니다.</p>}</div>;
}
