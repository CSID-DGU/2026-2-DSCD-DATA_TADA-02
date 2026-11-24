import { useEffect, useState } from 'react';
import { api } from './api';
import type { Area, Detail } from './types';
import './presentation-picker.css';

const LIVE_CODES = ['3120052', '3120003', '3110565'] as const;
const DEMO_CODES = ['3120052', '3120053', '3110565'] as const;
const format = new Intl.NumberFormat('ko-KR');

export function presentationCodes(dataMode: string): readonly string[] {
  return dataMode === 'demo' ? DEMO_CODES : LIVE_CODES;
}

type Props = {
  codes: readonly string[];
  areas: Area[];
  selected: string[];
  onToggle: (code: string) => void;
  onDetail: (code: string) => void;
  onCompare: (codes: string[]) => void;
};

function PreviewValues({ detail }: { detail: Detail }) {
  const sales = detail.current?.average_sales_krw;
  const transactions = detail.current?.transaction_count;
  const menuCount = detail.stores.filter(store => store.menu.length > 0).length;
  const figures = [
    ['점포당 분기 평균 매출', sales == null ? '자료 없음' : format.format(Math.round(sales / 10000)) + '만 원'],
    ['분기 거래 건수', transactions == null ? '자료 없음' : format.format(transactions) + '건'],
    ['임대 매물', detail.rentals.length ? format.format(detail.rentals.length) + '건' : '자료 없음'],
    ['상권 내 카페', detail.stores.length ? format.format(detail.stores.length) + '곳' : '자료 없음'],
    ['메뉴가 있는 카페', menuCount ? format.format(menuCount) + '곳' : '자료 없음'],
  ];

  return <dl className="presentation-figures">
    {figures.map(([label, value]) => <div key={label}>
      <dt>{label}</dt>
      <dd className={value === '자료 없음' ? 'presentation-missing' : undefined}>{value}</dd>
    </div>)}
  </dl>;
}

export default function PresentationPicker({ codes, areas, selected, onToggle, onDetail, onCompare }: Props) {
  const [previews, setPreviews] = useState<Partial<Record<string, Detail | 'failed'>>>({});

  useEffect(() => {
    const controller = new AbortController();
    for (const code of codes) {
      api<Detail>('/areas/' + encodeURIComponent(code) + '/analysis', { signal: controller.signal })
        .then(detail => {
          if (!controller.signal.aborted) setPreviews(previous => ({ ...previous, [code]: detail }));
        })
        .catch(() => {
          if (!controller.signal.aborted) setPreviews(previous => ({ ...previous, [code]: 'failed' }));
        });
    }
    return () => controller.abort();
  }, [codes]);

  const options = codes.map(code => areas.find(area => area.code === code)).filter(area => area !== undefined);
  const selectedOptions = options.filter(area => selected.includes(area.code)).map(area => area.code);

  if (!options.length) return <p className="panel">표시할 발표용 상권이 없습니다. 상권 탐색에서 직접 선택하세요.</p>;

  return <section className="presentation-picker" aria-label="발표용 후보 상권">
    <ul className="presentation-options">
      {options.map(area => {
        const preview = previews[area.code];
        const checked = selected.includes(area.code);
        return <li key={area.code} className={'presentation-option' + (checked ? ' selected' : '')}>
          <label className="presentation-choice">
            <input type="checkbox" checked={checked} onChange={() => onToggle(area.code)} />
            <span><strong>{area.name}</strong><small>{area.district}</small></span>
          </label>
          {preview === undefined ? <p className="presentation-status" role="status">자료를 불러오는 중입니다.</p>
            : preview === 'failed' ? <p className="presentation-status" role="status">자료를 불러오지 못했습니다.</p>
            : <PreviewValues detail={preview} />}
          <button className="presentation-detail" aria-label={area.name + ' 상세 보기'} onClick={() => onDetail(area.code)}>상세 보기</button>
        </li>;
      })}
    </ul>
    <div className="presentation-actions">
      <span aria-live="polite">선택 {selectedOptions.length} / {options.length}곳</span>
      <button className="primary" onClick={() => onCompare(selectedOptions.length ? selectedOptions : options.map(area => area.code))}>
        {selectedOptions.length ? '선택한 ' + selectedOptions.length + '곳 비교하기' : '발표 후보 모두 비교하기'}
      </button>
    </div>
  </section>;
}
