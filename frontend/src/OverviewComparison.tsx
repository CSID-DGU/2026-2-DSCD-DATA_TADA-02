import AnalysisIcon from './AnalysisIcon';
import { averageOutlook, overviewSituation, PYEONG_M2 } from './report-metrics.mjs';
import type { ComparisonItem } from './types';

const num = (n: number, digits = 1) => n.toLocaleString('ko-KR', { maximumFractionDigits: digits });
const indicators = [
  { label: '총매출액', key: 'total_sales_krw', rate: 'sales_yoy_pct', color: 'sales', scale: 1e8, unit: '억' },
  { label: '점포 수', key: 'store_count', rate: 'stores_yoy_pct', color: 'stores', scale: 1, unit: '개' },
  { label: '총 거래 건수', key: 'transaction_count', rate: 'transactions_yoy_pct', color: 'transactions', scale: 1e4, unit: '만 건' },
] as const;

export const quarterLabel = (quarter: string) => `${quarter.slice(0, 4)}년 ${quarter.slice(-1)}분기`;
const previousQuarterOf = (quarter: string) => `${Number(quarter.slice(0, 4)) - 1}${quarter.slice(4)}`;

export function OverviewLegend({ quarter }: { quarter: string }) {
  return <div className="comparison-legend" aria-label="비교 기간">
    {([['previous', previousQuarterOf(quarter)], ['current', quarter]] as const).map(([period, value]) =>
      <span key={period}><span className="overview-swatches" aria-hidden="true">
        {indicators.map(metric => <i key={metric.key} className={`overview-${metric.color} ${period}-bar`} />)}
      </span>{quarterLabel(value)}</span>
    )}
  </div>;
}

export function OverviewCard({ item, quarter, open }: { item: ComparisonItem; quarter: string; open: () => void }) {
  const current = item.observations.find(row => row.quarter === quarter);
  const previousQuarter = previousQuarterOf(quarter);
  const previous = item.observations.find(row => row.quarter === previousQuarter);
  const m = item.metrics;
  const situation = overviewSituation(m?.sales_yoy_pct, m?.stores_yoy_pct, m?.transactions_yoy_pct);
  const rents = item.rentals.flatMap(r => r.monthly_rent_krw == null ? [] : [r.monthly_rent_krw / 10000]);
  const sizes = item.rentals.flatMap(r => r.area_m2 == null ? [] : [r.area_m2 / PYEONG_M2]);
  return <article className="panel comparison-card overview-card">
    <div className="overview-card-heading"><h3><AnalysisIcon name="pin" /> {item.area.name}</h3>
      <span className={`overview-situation ${situation.tone}`}>{situation.label}</span>
    </div>
    <p className="muted">{item.area.district} / {item.area.administrative_dong}</p>
    <div className="overview-indicators">{indicators.map(({ label, key, rate, color, scale, unit }) => {
      const before = previous?.[key] ?? null;
      const now = current?.[key] ?? null;
      const maximum = Math.max(1, before ?? 0, now ?? 0);
      const change = m?.[rate];
      const direction = change == null || change === 0 ? 'neutral' : change > 0 ? 'positive' : 'negative';
      const valueText = (value: number | null) => value == null ? '자료 없음' : `${num(value / scale)}${unit}`;
      return <section key={key} className={`overview-indicator overview-${color}`}
        aria-label={`${label}: ${previousQuarter} ${valueText(before)}, ${quarter} ${valueText(now)}`}>
        <h4>{label}</h4>
        <div className="paired-bars" aria-hidden="true">
          {([[before, 'previous'], [now, 'current']] as const).map(([value, period]) =>
            <div key={period} className={value == null ? 'missing-bar' : undefined}>
              <small>{valueText(value)}</small>
              <span className={`${period}-bar`} style={{ height: value == null ? 0 : `${value / maximum * 66}px` }} />
            </div>
          )}
        </div>
        <span className={`overview-rate ${direction}`}>{change == null ? '비교 자료 없음' :
          <>{change > 0 ? '+' : ''}{num(change)}% <span aria-hidden="true">{change > 0 ? '↑' : change < 0 ? '↓' : '→'}</span></>}
        </span>
      </section>;
    })}</div>
    <p className="overview-outlook">{m ? averageOutlook(m.sales_yoy_pct, m.stores_yoy_pct, m.transactions_yoy_pct) : item.missing_reason || '전년 동분기 비교 자료 부족'}</p>
    <dl className="overview-considerations"><dt>월세</dt><dd>{rents.length ? `${num(Math.min(...rents))}~${num(Math.max(...rents))}만 원/월` : '매물 자료 없음'}</dd><dt>매물 면적</dt><dd>{sizes.length ? `${num(Math.min(...sizes))}~${num(Math.max(...sizes))}평` : '면적 미확보'}</dd></dl>
    <button className="text-link" onClick={open}>이 상권 상세분석 <span aria-hidden="true">→</span></button>
  </article>;
}
