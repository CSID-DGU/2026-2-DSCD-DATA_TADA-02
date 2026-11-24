import { Area, Bar, BarChart, CartesianGrid, ComposedChart, DefaultTooltipContent, Line, ResponsiveContainer, Tooltip, usePlotArea, useXAxisScale, useYAxisScale, XAxis, YAxis } from 'recharts';
import AnalysisIcon from './AnalysisIcon';
import type { Detail, Distribution } from './types';

const totalColor = 'var(--sales-total)';
const averageColor = 'var(--sales-average)';
const shortQuarter = (quarter: string) => `${quarter.slice(2, 4)}.${quarter.slice(-1)}Q`;
const totalLabel = (value: unknown) => Number(value).toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const averageLabel = (value: unknown) => Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 0 });

export function TrendChart({ detail, recent, setRecent }: { detail: Detail; recent: boolean; setRecent: (recent: boolean) => void }) {
  const isDemo = detail.meta.data_mode === 'demo';
  const forecastLabel = isDemo ? '가상 예측' : '예측';
  const observations = recent ? detail.observations.slice(-12) : detail.observations;
  const lastObservedQuarter = observations.at(-1)?.quarter;
  const forecastPoints = detail.forecast?.points.slice(0, 2) ?? [];
  const hasTotalForecast = forecastPoints.some(point => point.total_sales_krw != null);
  const hasAverageForecast = forecastPoints.some(point => point.average_sales_krw != null);
  const hasForecast = hasTotalForecast || hasAverageForecast;
  const actual = observations.map((row, i) => {
    const latest = i === observations.length - 1;
    const total = row.total_sales_krw == null ? null : row.total_sales_krw / 1e8;
    const average = row.average_sales_krw == null ? null : row.average_sales_krw / 10000;
    return { quarter: row.quarter, total, average,
      forecastTotal: latest && hasTotalForecast ? total : null,
      forecastAverage: latest && hasAverageForecast ? average : null,
    };
  });
  const future = forecastPoints.map(point => {
    const total = point.total_sales_krw == null ? null : point.total_sales_krw / 1e8;
    const average = point.average_sales_krw == null ? null : point.average_sales_krw / 10000;
    return { quarter: point.quarter, total: null, average: null, forecastTotal: total, forecastAverage: average,
      range80: point.lower80_krw != null && point.upper80_krw != null ? [point.lower80_krw / 10000, point.upper80_krw / 10000] : null,
      range90: point.lower90_krw != null && point.upper90_krw != null ? [point.lower90_krw / 10000, point.upper90_krw / 10000] : null,
    };
  });
  const hasRange80 = future.some(point => point.range80 != null);
  const hasRange90 = future.some(point => point.range90 != null);
  const data = [...actual, ...future];
  return <section className="panel sales-trend">
    <div className="sales-trend-heading">
      <h2>매출 추세 <small>총매출액 / 점포당 평균 매출액</small></h2>
      <div className="segmented" aria-label="표시 기간">
        <button className={recent ? 'active' : ''} aria-pressed={recent} onClick={() => setRecent(true)}>최근 3년</button>
        <button className={!recent ? 'active' : ''} aria-pressed={!recent} onClick={() => setRecent(false)}>전체</button>
      </div>
      <div className="sales-legend" aria-label="그래프 범례">
        <span><i className="line-key total-key" aria-hidden="true" />총매출액(좌측)</span>
        <span><i className="line-key average-key" aria-hidden="true" />점포당 매출액(우측)</span>
        {hasForecast && <span><i className="forecast-key" aria-hidden="true" />예측</span>}
        {(hasRange80 || hasRange90) && <span><i className="range-key" aria-hidden="true" />점포당 매출 예측 범위</span>}
      </div>
    </div>
    <div className="sales-axis-labels"><span>총매출액 (억 원)</span><span>점포당 매출액 (만 원)</span></div>
    <div className="chart-container" role="img" aria-label={hasForecast ? '총매출액과 점포당 평균 매출의 과거 실선과 예측 점선' : '총매출액과 점포당 평균 매출의 과거 추세'}>
      <ResponsiveContainer width="100%" height={330}>
        <ComposedChart data={data} margin={{ top: 34, right: 10, bottom: 10, left: 6 }} accessibilityLayer>
          <CartesianGrid stroke="#dce7ef" strokeDasharray="4 4" vertical={false} />
          <XAxis dataKey="quarter" tick={{ fill: '#405777', fontSize: 12 }} tickFormatter={shortQuarter} tickMargin={8} minTickGap={15} padding={{ left: 22, right: 22 }} />
          <YAxis yAxisId="total" tick={{ fill: totalColor, fontSize: 12 }} domain={['auto', 'auto']} width={43} tickFormatter={v => String(v)} />
          <YAxis yAxisId="average" orientation="right" tick={{ fill: averageColor, fontSize: 12 }} domain={['auto', 'auto']} width={57} tickFormatter={averageLabel} />
          <Tooltip
            content={props => <DefaultTooltipContent {...props} payload={props.label === lastObservedQuarter
              ? props.payload.filter(({ dataKey }) => dataKey !== 'forecastTotal' && dataKey !== 'forecastAverage')
              : props.payload} />}
            labelFormatter={label => typeof label === 'string' ? shortQuarter(label) : label}
            formatter={(value, name) => [Array.isArray(value) ? value.map(averageLabel).join('~') : formatNumber(value), name]}
          />
          {hasRange90 && <Area yAxisId="average" dataKey="range90" type="linear" name="점포당 90% 범위 (만 원)" fill="#b9eceb" fillOpacity={.35} stroke="none" />}
          {hasRange80 && <Area yAxisId="average" dataKey="range80" type="linear" name="점포당 80% 범위 (만 원)" fill="#6fd3d2" fillOpacity={.4} stroke="none" />}
          <Line yAxisId="total" dataKey="total" name="총매출액 (억 원)" stroke={totalColor} strokeWidth={2.5} dot={{ r: 3, fill: totalColor }} connectNulls={false} isAnimationActive={false} />
          <Line yAxisId="average" dataKey="average" name="점포당 평균 매출액 (만 원)" stroke={averageColor} strokeWidth={2.5} dot={{ r: 3, fill: averageColor }} connectNulls={false} isAnimationActive={false} />
          {hasTotalForecast && <Line yAxisId="total" dataKey="forecastTotal" name={`총매출액 ${forecastLabel} (억 원)`} stroke={totalColor} strokeWidth={2}
            strokeDasharray="7 5" dot={false} isAnimationActive={false} />}
          {hasAverageForecast && <Line yAxisId="average" dataKey="forecastAverage" name={`점포당 ${forecastLabel} (만 원)`} stroke={averageColor} strokeWidth={2}
            strokeDasharray="7 5" dot={false} isAnimationActive={false} />}
          <SalesChartAnnotations points={data.map(row => ({
            quarter: row.quarter, total: row.total ?? row.forecastTotal, average: row.average ?? row.forecastAverage,
          }))} observedCount={actual.length} recent={recent} hasForecast={hasForecast} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
    {hasForecast && <p className="sales-forecast-note"><AnalysisIcon name="info" /><span>점선은 예측값이며 실제 매출은 달라질 수 있습니다. {hasRange80 || hasRange90 ? '옅은 영역은 점포당 평균 매출의 예측 범위입니다.' : '점포당 평균 매출의 예측 구간은 제공하지 않습니다.'}</span></p>}
    <details className="chart-data"><summary>그래프 수치 표로 보기</summary><div className="table-scroll"><table><thead><tr><th>분기</th><th>총매출액 (억 원)</th><th>점포당 평균 매출액 (만 원)</th><th>자료 구분</th></tr></thead>
      <tbody>{data.map((row, i) => <tr key={row.quarter}><td>{row.quarter}</td><td>{formatNumber(row.total ?? row.forecastTotal)}</td><td>{formatNumber(row.average ?? row.forecastAverage)}</td><td>{i < actual.length ? (isDemo ? '과거 예시' : '관측 통계') : forecastLabel}</td></tr>)}</tbody>
    </table></div></details>
  </section>;
}

function SalesChartAnnotations({ points, observedCount, recent, hasForecast }: {
  points: { quarter: string; total: number | null; average: number | null }[];
  observedCount: number;
  recent: boolean;
  hasForecast: boolean;
}) {
  const x = useXAxisScale();
  const totalY = useYAxisScale('total');
  const averageY = useYAxisScale('average');
  const plot = usePlotArea();
  if (!x || !totalY || !averageY || !plot) return null;

  const pointSpacing = plot.width / Math.max(1, points.length);
  const firstFuture = points[observedCount];
  const lastObserved = points[observedCount - 1];
  const observedX = lastObserved && x(lastObserved.quarter);
  const futureX = firstFuture && x(firstFuture.quarter);
  const boundaryX = hasForecast && observedX != null && futureX != null ? (observedX + futureX) / 2 : null;
  return <g className="sales-point-labels" aria-hidden="true" pointerEvents="none">
    {boundaryX != null && <g>
      <line x1={boundaryX} x2={boundaryX} y1={plot.y} y2={plot.y + plot.height} stroke="#5976a3" strokeDasharray="5 5" />
      <text x={boundaryX} y={plot.y - 11} fill="#39537d" textAnchor="middle" className="sales-point-label">예측 시작</text>
    </g>}
    {points.map(({ quarter, total, average }, index) => {
      const forecast = index >= observedCount;
      const emphasized = index >= observedCount - 1;
      if (!emphasized && (!recent || pointSpacing < 46)) return null;
      // On a narrow chart the first of two forecast labels would overlap its neighbors.
      const showLabel = pointSpacing >= 34 || index !== observedCount || index === points.length - 1;
      const position = x(quarter);
      const blueY = total == null ? undefined : totalY(total);
      const tealY = average == null ? undefined : averageY(average);
      if (position == null) return null;
      const blueAbove = tealY == null || (blueY != null && blueY <= tealY);
      return <g key={quarter} className={emphasized ? 'sales-point-label' : 'sales-history-label'} textAnchor="middle">
        {forecast && blueY != null && <circle cx={position} cy={blueY} r={4} fill="#fff" stroke={totalColor} strokeWidth={2} />}
        {forecast && tealY != null && <circle cx={position} cy={tealY} r={4} fill="#fff" stroke={averageColor} strokeWidth={2} />}
        {showLabel && blueY != null && <text x={position} y={blueY + (blueAbove ? -9 : 15)} fill={totalColor}>{totalLabel(total)}</text>}
        {showLabel && tealY != null && <text x={position} y={tealY + (blueY != null && blueAbove ? 15 : -9)} fill={averageColor}>{averageLabel(average)}</text>}
      </g>;
    })}
  </g>;
}

function formatNumber(value: unknown) { return value == null ? '자료 없음' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 }); }

export function DemandCharts({ distribution }: { distribution: Distribution }) {
  return <div className="demand-grid">{(['age', 'weekday', 'time'] as const).map((dimension, index) => <section className={`panel ${dimension === 'time' ? 'wide' : ''}`} key={dimension}>
    <h2>{['연령별', '요일별', '시간대별'][index]} 분포</h2>
    <p className="muted">{distribution[`${dimension}_basis`]} / 단위: {distribution.unit}</p>
    <ResponsiveContainer width="100%" height={245}>
      <BarChart data={distribution[dimension]} layout={dimension === 'age' ? 'vertical' : 'horizontal'} margin={{ left: dimension === 'age' ? 35 : 10, right: 20, bottom: 5 }} accessibilityLayer>
        <CartesianGrid stroke="#dce7ef" strokeDasharray="4 4" horizontal={dimension !== 'age'} vertical={dimension === 'age'} />
        {dimension === 'age' ? <><XAxis type="number" /><YAxis type="category" dataKey="label" width={65} /></> : <><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis /></>}
        <Tooltip formatter={value => Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })} />
        <Bar dataKey="value" name={distribution.unit} fill="#009da5" radius={dimension === 'age' ? [0, 4, 4, 0] : [4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
    <details className="chart-data"><summary>분포 수치 보기</summary><table><thead><tr><th>구분</th><th>{distribution.unit}</th><th>분기 구성비 (%)</th></tr></thead><tbody>{distribution[dimension].map(bin => <tr key={bin.label}><td>{bin.label}</td><td>{formatNumber(bin.value)}</td><td>{formatNumber(bin.share_pct)}</td></tr>)}</tbody></table></details>
  </section>)}</div>;
}
