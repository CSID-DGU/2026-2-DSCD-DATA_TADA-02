import { estimateRent, PYEONG_M2 } from './report-metrics.mjs';
import type { ComparisonItem } from './types';
import './rent-comparison.css';

const num = (n: number | null, digits = 1) => n == null ? '자료 없음' : n.toLocaleString('ko-KR', { maximumFractionDigits: digits });

export default function RentComparison({ items, open, areaPyeong, setAreaPyeong, floor, setFloor }: {
  items: ComparisonItem[]; open: (code: string) => void; areaPyeong: number; setAreaPyeong: (n: number) => void;
  floor: string; setFloor: (floor: string) => void;
}) {
  const floors = [...new Set(items.flatMap(i => i.rentals.flatMap(r => r.floor ? [r.floor] : [])))].sort();
  const estimates = items.map(item => estimateRent(item.rentals, areaPyeong * PYEONG_M2, item.metrics?.average_sales_krw, floor));
  const maximum = Math.max(1, ...estimates.map(e => e.monthlyRent || 0));
  return <section className="panel rent-overview" aria-label="동일 면적 기준 임대료 비교">
    <div className="rent-toolbar"><label>기준 면적 <select value={areaPyeong} onChange={e => setAreaPyeong(Number(e.target.value))}>
      {[10, 15, 20, 25, 30, 40, 50].map(n => <option key={n} value={n}>{n}평 ({num(n * PYEONG_M2)}㎡)</option>)}
    </select></label><label>층 조건 <select value={floor} onChange={e => setFloor(e.target.value)}><option value="">전체 층</option>{floors.map(f => <option key={f}>{f}</option>)}</select></label></div>
    <div className="table-scroll"><table className="rent-table"><thead><tr><th scope="col">상권</th><th scope="col">예상 월 임대료 <small>동일 {areaPyeong}평 기준</small></th><th scope="col">월 환산 매출 대비 비율</th><th scope="col">계산에 사용한 매물</th></tr></thead>
      <tbody>{items.map((item, index) => { const e = estimates[index]; return <tr key={item.area.code}>
        <th scope="row">{item.area.name}</th><td><div className="metric-bar" aria-hidden="true"><span style={{ width: `${(e.monthlyRent || 0) / maximum * 100}%` }} /></div><strong className="rent-estimate">{e.monthlyRent == null ? '자료 없음' : `${num(e.monthlyRent / 10000)}만 원/월`}</strong></td>
        <td><strong className="rent-estimate">{e.salesRatio == null ? '계산 불가' : `${num(e.salesRatio)}%`}</strong><small>점포당 분기 평균 매출 ÷ 3 기준</small></td>
        <td>{e.count}건<br /><button className="text-link" onClick={() => open(item.area.code)}>매물 상세 보기</button></td>
      </tr>; })}</tbody></table></div>
    <details className="rent-note"><summary>임대료 계산 기준</summary><p>예상 월 임대료 = 조건에 맞는 매물의 월세 합계 ÷ 면적 합계 × 설정 면적입니다. 매출 대비 비율 = 예상 월 임대료 ÷ (점포당 분기 평균 매출 ÷ 3) × 100입니다. 보증금과 관리비는 포함하지 않습니다.</p></details>
    <p className="notice info">발표용 가상 매물로 계산한 참고값입니다. 실제 시세나 설정 면적의 실제 매물 가격을 의미하지 않으며, 상권 평균 매출은 해당 면적 점포의 예상 매출과 다를 수 있습니다.</p>
  </section>;
}
