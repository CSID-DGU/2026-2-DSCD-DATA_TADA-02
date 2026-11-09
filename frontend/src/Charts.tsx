import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Detail, Distribution } from './types';

export function TrendChart({ detail, competition, recent }: { detail: Detail; competition: boolean; recent: boolean }) {
  const isDemo = detail.meta.data_mode === 'demo';
  const forecastLabel = isDemo ? '가상 예측' : 'Ridge 기준 예측';
  const observations = recent ? detail.observations.slice(-12) : detail.observations;
  const data: Record<string, unknown>[] = observations.map((row, i) => ({ quarter: row.quarter,
    actual: row.average_sales_krw === null ? null : row.average_sales_krw / 10000,
    sales: row.sales_yoy_pct, stores: row.stores_yoy_pct,
    forecast: i === observations.length - 1 && row.average_sales_krw !== null ? row.average_sales_krw / 10000 : null,
    forecastSales: i === observations.length - 1 ? row.sales_yoy_pct : null,
    forecastStores: i === observations.length - 1 ? row.stores_yoy_pct : null,
  }));
  for (const point of detail.forecast?.points || []) data.push({ quarter: point.quarter,
    forecast: point.average_sales_krw == null ? null : point.average_sales_krw / 10000, forecastSales: point.sales_yoy_pct, forecastStores: point.stores_yoy_pct,
    range80: point.lower80_krw != null && point.upper80_krw != null ? [point.lower80_krw / 10000, point.upper80_krw / 10000] : null,
    range90: point.lower90_krw != null && point.upper90_krw != null ? [point.lower90_krw / 10000, point.upper90_krw / 10000] : null,
  });
  return <div className="chart-container" role="img" aria-label={(competition ? '총매출과 점포 수의 전년 동분기 대비 변화율' : '점포당 분기 평균 매출') + ', 실선은 과거, 점선은 ' + forecastLabel}>
    <ResponsiveContainer width="100%" height={360}>
      <ComposedChart data={data} margin={{ top: 20, right: 25, bottom: 10, left: 15 }} accessibilityLayer>
        <CartesianGrid stroke="#dce7ef" strokeDasharray="4 4" vertical={false} />
        <XAxis dataKey="quarter" tick={{ fill: '#526784', fontSize: 12 }} tickFormatter={v => String(v).replace('20', '')} />
        <YAxis tick={{ fill: '#526784', fontSize: 12 }} domain={competition ? ['auto', 'auto'] : [0, 'auto']} unit={competition ? '%' : ''} />
        <Tooltip formatter={(value, name) => [Array.isArray(value) ? value.map(v => Number(v).toLocaleString()).join(' ~ ') : Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 }), name]} />
        <Legend />
        <ReferenceLine x={observations.at(-1)?.quarter} stroke="#7c8da9" strokeDasharray="6 5" />
        {competition ? <>
          <ReferenceLine y={0} stroke="#879bb5" />
          <Line dataKey="sales" name="총매출 변화율" stroke="#009da5" strokeWidth={3} connectNulls={false} />
          <Line dataKey="stores" name="점포 수 변화율" stroke="#377ce7" strokeWidth={3} connectNulls={false} />
          <Line dataKey="forecastSales" name={'총매출 ' + forecastLabel} stroke="#009da5" strokeWidth={2} strokeDasharray="7 5" />
          <Line dataKey="forecastStores" name={'점포 수 ' + forecastLabel} stroke="#377ce7" strokeWidth={2} strokeDasharray="7 5" />
        </> : <>
          {isDemo && <Area dataKey="range90" name="가상 90% 범위" fill="#b9eceb" fillOpacity={.35} stroke="none" />}
          {isDemo && <Area dataKey="range80" name="가상 80% 범위" fill="#6fd3d2" fillOpacity={.4} stroke="none" />}
          <Line dataKey="actual" name={isDemo ? '과거 예시 (만원/분기)' : '관측 통계 (만원/분기)'} stroke="#009da5" strokeWidth={3} />
          <Line dataKey="forecast" name={forecastLabel} stroke="#009da5" strokeWidth={2} strokeDasharray="7 5" />
        </>}
      </ComposedChart>
    </ResponsiveContainer>
    <details className="chart-data"><summary>그래프 수치 표로 보기</summary><div className="table-scroll"><table><thead><tr><th>분기</th><th>{competition ? '총매출 변화율 (%)' : '점포당 평균 매출 (만원)'}</th>{competition && <th>점포 수 변화율 (%)</th>}</tr></thead><tbody>{data.map(row => <tr key={String(row.quarter)}><td>{String(row.quarter)}</td><td>{formatNumber(row[competition ? 'sales' : 'actual'] ?? row[competition ? 'forecastSales' : 'forecast'])}</td>{competition && <td>{formatNumber(row.stores ?? row.forecastStores)}</td>}</tr>)}</tbody></table></div></details>
  </div>;
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
