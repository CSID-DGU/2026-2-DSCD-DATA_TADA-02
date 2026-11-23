import { averageOutlook, PYEONG_M2 } from './report-metrics.mjs';
import type { ComparisonItem, Observation } from './types';

const num = (n: number | null | undefined, digits = 1) => n == null ? '자료 없음' : n.toLocaleString('ko-KR', { maximumFractionDigits: digits });
const compact = (n: number | null | undefined, key: keyof Observation) => n == null ? '자료 없음' : key === 'total_sales_krw' ? `${num(n / 1e8)}억` : key === 'transaction_count' ? `${num(n / 1e4)}만 건` : `${num(n, 0)}개`;

export function OverviewCard({ item, quarter, open }: { item: ComparisonItem; quarter: string; open: () => void }) {
  const current = item.observations.find(r => r.quarter === quarter);
  const previousQuarter = `${Number(quarter.slice(0, 4)) - 1}${quarter.slice(4)}`;
  const previous = item.observations.find(r => r.quarter === previousQuarter);
  const m = item.metrics;
  const rents = item.rentals.flatMap(r => r.monthly_rent_krw == null ? [] : [r.monthly_rent_krw / 10000]);
  const sizes = item.rentals.flatMap(r => r.area_m2 == null ? [] : [r.area_m2 / PYEONG_M2]);
  return <article className="panel comparison-card overview-card">
    <h3>{item.area.name}</h3><p className="muted">{item.area.district} / {item.area.administrative_dong}</p>
    {m ? <>
      <div className="overview-indicators">{([
        ['총매출액', 'total_sales_krw', m.sales_yoy_pct],
        ['점포 수', 'store_count', m.stores_yoy_pct],
        ['총 거래 건수', 'transaction_count', m.transactions_yoy_pct],
      ] as const).map(([label, key, rate]) => {
        const before = previous?.[key] ?? null, now = current?.[key] ?? null;
        const max = Math.max(1, before ?? 0, now ?? 0);
        return <section key={key} className="overview-indicator" aria-label={`${label}: ${previousQuarter} ${compact(before, key)}, ${quarter} ${compact(now, key)}`}>
          <h4>{label}</h4><div className="paired-bars" aria-hidden="true">
            <div><small>{compact(before, key)}</small><span className="previous-bar" style={{ height: `${before == null ? 0 : before / max * 72}px` }} /></div>
            <div><small>{compact(now, key)}</small><span className="current-bar" style={{ height: `${now == null ? 0 : now / max * 72}px` }} /></div>
          </div><span className={`overview-rate ${rate != null && rate < 0 ? 'negative' : ''}`}>{rate == null ? '비교 자료 없음' : `${rate > 0 ? '+' : ''}${num(rate)}%`}</span>
        </section>;
      })}</div>
      <p className="overview-outlook">{averageOutlook(m.sales_yoy_pct, m.stores_yoy_pct, m.transactions_yoy_pct)}</p>
      <dl className="overview-considerations"><dt>월세 범위</dt><dd>{rents.length ? `${num(Math.min(...rents))}~${num(Math.max(...rents))}만 원/월` : '매물 자료 없음'}</dd><dt>매물 면적</dt><dd>{sizes.length ? `${num(Math.min(...sizes))}~${num(Math.max(...sizes))}평` : '면적 미확보'}</dd></dl>
    </> : <p>{item.missing_reason}</p>}
    <button className="text-link" onClick={open}>이 상권 상세분석</button>
    <section className="overview-commentary" aria-label={`${item.area.name} AI 해설`}>
      <h4><span aria-hidden="true">✧</span> 상권별 AI 해설</h4>
      <p className="muted">이 상권의 해설이 여기에 표시됩니다.</p>
    </section>
  </article>;
}

