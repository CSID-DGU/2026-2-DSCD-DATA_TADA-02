import AnalysisIcon from './AnalysisIcon';
import { TrendChart } from './Charts';
import { quarterLabel } from './OverviewComparison';
import type { Detail, Metrics } from './types';

const figure = (amount: number, decimals = 0) => amount.toLocaleString('ko-KR', {
  minimumFractionDigits: decimals, maximumFractionDigits: decimals,
});

export default function SalesDetail({ detail, current, recent, setRecent }: {
  detail: Detail; current: Metrics; recent: boolean; setRecent: (recent: boolean) => void;
}) {
  const metrics = [
    { label: '총매출액', icon: 'coins', amount: current.total_sales_krw, unit: '억 원', scale: 1e8, decimals: 1, change: current.sales_yoy_pct },
    { label: '점포당 평균 매출액', icon: 'store', amount: current.average_sales_krw, unit: '만 원', scale: 1e4, decimals: 0, change: current.average_sales_yoy_pct },
  ] as const;
  return <>
    <div className="sales-summary">{metrics.map(({ label, icon, amount, unit, scale, decimals, change }) =>
      <section key={label} className="panel sales-stat">
        <div className="sales-stat-label"><AnalysisIcon name={icon} /><div><h2>{label}</h2><span>{quarterLabel(detail.meta.quarter)}</span></div></div>
        <strong className="sales-stat-amount">{amount == null ? '자료 없음' : <>{figure(amount / scale, decimals)} <small>{unit}</small></>}</strong>
        <div className="sales-stat-change">
          <strong className={`overview-rate ${change == null || change === 0 ? 'neutral' : change > 0 ? 'positive' : 'negative'}`}>
            {change == null ? '비교 자료 없음' : <><span aria-hidden="true">{change > 0 ? '↑' : change < 0 ? '↓' : '→'}</span> {change > 0 ? '+' : ''}{figure(change, 1)}%</>}
          </strong>
          <small>전년 동분기 대비</small>
        </div>
      </section>
    )}</div>
    <TrendChart detail={detail} recent={recent} setRecent={setRecent} />
  </>;
}
