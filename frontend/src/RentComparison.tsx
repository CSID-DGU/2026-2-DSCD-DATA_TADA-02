import { estimateRent, isRentEstimateSample, PYEONG_M2 } from './report-metrics.mjs';
import type { ComparisonItem } from './types';
import AreaDetailButton from './AreaDetailButton';
import './rent-comparison.css';

const num = (n: number | null, digits = 1) => n == null ? '자료 없음' : n.toLocaleString('ko-KR', { maximumFractionDigits: digits });

export default function RentComparison({ items, open, areaPyeong, setAreaPyeong, floor, setFloor, demo }: {
  items: ComparisonItem[]; open: (code: string) => void; areaPyeong: number; setAreaPyeong: (n: number) => void;
  floor: string; setFloor: (floor: string) => void; demo: boolean;
}) {
  const floorCounts = new Map<string, number>();
  let total = 0;
  for (const { rentals } of items) {
    for (const rental of rentals) {
      if (!isRentEstimateSample(rental)) continue;
      const key = rental.floor || '';
      floorCounts.set(key, (floorCounts.get(key) ?? 0) + 1);
      total++;
    }
  }
  const floors = [...floorCounts].filter(([label]) => label).sort(([a], [b]) => a.localeCompare(b, 'ko', { numeric: true }));
  const largestFloor = Math.max(1, ...floors.map(([, count]) => count));
  const areaLabel = `${areaPyeong}평 (${num(areaPyeong * PYEONG_M2)}㎡)`;
  const estimates = items.map(item => estimateRent(item.rentals, areaPyeong * PYEONG_M2, item.metrics?.average_sales_krw, floor));
  const maximum = Math.max(1, ...estimates.map(e => e.monthlyRent || 0));
  return <section className="panel rent-overview" aria-label="동일 면적 기준 임대료 비교">
    <div className="rent-toolbar">
      <div className="rent-area-control">
        <label htmlFor="rent-area">기준 면적</label>
        <output htmlFor="rent-area">{areaLabel}</output>
        <input id="rent-area" type="range" min={10} max={50} step={5} value={areaPyeong} aria-valuetext={areaLabel}
          onChange={event => setAreaPyeong(event.currentTarget.valueAsNumber)} />
        <span aria-hidden="true">10평</span><span aria-hidden="true">50평</span>
      </div>
      <div className="rent-floor-filter" role="group" aria-labelledby="rent-floor-title">
        <div className="rent-floor-controls">
          <span id="rent-floor-title">층 조건</span>
          <button type="button" className="rent-all-floors" aria-pressed={!floor} onClick={() => setFloor('')}>전체 층 {num(total, 0)}건</button>
          {floorCounts.has('') && <p>층 미확인 {num(floorCounts.get('') ?? 0, 0)}건</p>}
        </div>
        {floors.length > 0 &&
          <div className="rent-floor-chart">
            {floors.map(([label, count]) => <button type="button" key={label} aria-pressed={floor === label} onClick={() => setFloor(label)}>
              <span className="rent-floor-count">{num(count, 0)}건</span>
              <span className="rent-floor-track" aria-hidden="true"><span style={{ height: `${Math.log1p(count) / Math.log1p(largestFloor) * 100}%` }} /></span>
              <span className="rent-floor-label">{label}</span>
            </button>)}
          </div>}
      </div>
    </div>
    <div className="table-scroll"><table className="rent-table"><thead><tr><th scope="col">상권</th><th scope="col">예상 월 임대료 <small>동일 {areaPyeong}평 기준</small></th><th scope="col">월 환산 매출 대비 비율</th></tr></thead>
      <tbody>{items.map((item, index) => { const e = estimates[index]; return <tr key={item.area.code}>
        <th scope="row">
          {item.area.name}
          <div className="rent-area-meta">
            <small>매물 {e.count}건</small>
            <AreaDetailButton areaName={item.area.name} onClick={() => open(item.area.code)} />
          </div>
        </th>
        <td><div className="metric-bar" aria-hidden="true"><span style={{ width: `${(e.monthlyRent || 0) / maximum * 100}%` }} /></div><strong className="rent-estimate">{e.monthlyRent == null ? '자료 없음' : `${num(e.monthlyRent / 10000)}만 원/월`}</strong></td>
        <td><strong className="rent-estimate">{e.salesRatio == null ? '계산 불가' : `${num(e.salesRatio)}%`}</strong><small>점포당 분기 평균 매출 ÷ 3 기준</small></td>
      </tr>; })}</tbody></table></div>
    <details className="rent-note"><summary>임대료 계산 기준</summary><p>예상 월 임대료 = 조건에 맞는 매물의 월세 합계 ÷ 면적 합계 × 설정 면적입니다. 매출 대비 비율 = 예상 월 임대료 ÷ (점포당 분기 평균 매출 ÷ 3) × 100입니다. 보증금과 관리비는 포함하지 않습니다.</p></details>
    <p className="notice info">{demo ? '개발용 가상 매물로 계산한 참고값입니다.' : '수집 시점의 공개 임대 광고로 계산한 참고값입니다.'} 실제 시세나 설정 면적의 실제 매물 가격을 의미하지 않으며, 상권 평균 매출은 해당 면적 점포의 예상 매출과 다를 수 있습니다.</p>
  </section>;
}
