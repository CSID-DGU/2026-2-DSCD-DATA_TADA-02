import { useState } from 'react';
import type { ComparisonItem } from './types';
import './rent-comparison.css';

const number = (value: number) => value.toLocaleString('ko-KR', { maximumFractionDigits: 1 });

function valuesOf<T>(items: T[], read: (item: T) => number | null) {
  return items.map(read).filter((value): value is number => value != null);
}

function range(values: number[], divisor: number, unit: string) {
  if (!values.length) return '자료 없음';
  const min = Math.min(...values) / divisor;
  const max = Math.max(...values) / divisor;
  return min === max ? number(min) + unit : number(min) + '~' + number(max) + unit;
}

export default function RentComparison({ items, open }: { items: ComparisonItem[]; open: (code: string) => void }) {
  const [floor, setFloor] = useState('');
  const rentals = items.flatMap(item => item.rentals);
  const floors = [...new Set(rentals.map(rental => rental.floor).filter((value): value is string => !!value))]
    .sort((a, b) => a.localeCompare(b, 'ko', { numeric: true }));
  const activeFloor = floors.includes(floor) ? floor : '';
  const maxRent = Math.max(0, ...valuesOf(rentals, rental => rental.monthly_rent_krw));
  const step = Math.max(10000, 10 ** Math.floor(Math.log10(maxRent / 4 || 10000)));
  const tick = Math.max(step, Math.ceil(maxRent / (4 * step)) * step);
  const limit = tick * 4;

  return <section className="panel rent-overview" aria-label="발표용 임대 매물 비교">
    <div className="rent-toolbar">
      <p>점 하나는 매물 한 건의 월세입니다. 면적과 보증금도 함께 확인하세요.</p>
      <label>층 조건 <select value={activeFloor} onChange={event => setFloor(event.target.value)}>
        <option value="">전체 층</option>
        {floors.map(value => <option key={value}>{value}</option>)}
      </select></label>
    </div>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="후보별 임대 매물 비교표">
      <table className="rent-table">
        <thead><tr>
          <th scope="col">상권</th>
          <th scope="col" className="rent-scale-col">매물 월세 <small>(만 원/월)</small>
            <div className="rent-axis" aria-hidden="true">{[0, 1, 2, 3, 4].map(i => <span key={i}>{number(i * tick / 10000)}</span>)}</div>
          </th>
          <th scope="col">보증금 범위</th>
          <th scope="col">면적 범위</th>
          <th scope="col">매물</th>
        </tr></thead>
        <tbody>{items.map(({ area, rentals: areaRentals }) => {
          const filtered = areaRentals.filter(rental => !activeFloor || rental.floor === activeFloor);
          const monthly = valuesOf(filtered, rental => rental.monthly_rent_krw);
          return <tr key={area.code}>
            <th scope="row">{area.name}</th>
            <td>
              {monthly.length > 0 && <div className="rent-track" aria-hidden="true">
                {monthly.map((value, index) => <span key={index} style={{ left: (value / limit * 100) + '%' }}
                  title={number(value / 10000) + '만 원/월'} />)}
              </div>}
              <strong>{range(monthly, 10000, '만 원')}</strong>
            </td>
            <td>{range(valuesOf(filtered, rental => rental.deposit_krw), 10000, '만 원')}</td>
            <td>{range(valuesOf(filtered, rental => rental.area_m2), 1, '㎡')}</td>
            <td>{filtered.length > 0 ? <>{filtered.length}건<br /><button className="text-link rent-detail-link"
              onClick={() => open(area.code)} aria-label={area.name + ' 임대 매물 상세 보기'}>상세 →</button></> : '자료 없음'}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    <p className="rent-note">발표용 매물의 표시값을 비교합니다. 상권 전체의 평균이나 시세를 추정한 값은 아닙니다.</p>
  </section>;
}
