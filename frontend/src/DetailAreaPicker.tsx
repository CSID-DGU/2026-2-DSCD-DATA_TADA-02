import { useState } from 'react';
import type { Area } from './types';

export default function DetailAreaPicker({ areas, selectedCode, suggestedCodes, onSelect, compact = false }: {
  areas: Area[]; selectedCode: string; suggestedCodes: string[]; onSelect: (code: string) => void; compact?: boolean;
}) {
  const [query, setQuery] = useState('');
  const search = query.trim();
  const matches = areas.filter(area => !search || `${area.name} ${area.district} ${area.administrative_dong}`.includes(search));
  const current = areas.find(area => area.code === selectedCode);
  const options = current && !matches.some(area => area.code === selectedCode) ? [current, ...matches] : matches;
  const suggestions = search ? matches.slice(0, 8) : areas.filter(area => suggestedCodes.includes(area.code)).slice(0, 8);

  return <section className={`panel detail-area-picker ${compact ? 'compact' : ''}`} aria-label="상세분석할 상권 선택">
    {!compact && <><h2>어떤 상권을 자세히 살펴볼까요?</h2><p className="muted">상권 이름이나 지역을 검색해 바로 상세분석을 확인하세요.</p></>}
    <div className="detail-picker-controls">
      <label>상권 검색<input type="search" value={query} placeholder="상권 이름, 자치구, 행정동" onChange={event => setQuery(event.target.value)} /></label>
      <label>상세분석할 상권<select value={selectedCode} onChange={event => onSelect(event.target.value)}>
        <option value="" disabled>상권을 선택하세요</option>
        {options.map(area => <option key={area.code} value={area.code}>{area.name} · {area.district}</option>)}
      </select></label>
    </div>
    {!matches.length && <p className="muted" role="status">검색 결과가 없습니다. 다른 이름이나 지역으로 검색하세요.</p>}
    {!compact && suggestions.length > 0 && <div className="detail-area-results" aria-label={search ? '상권 검색 결과' : '바로 분석할 상권'}>
      {suggestions.map(area => <button key={area.code} onClick={() => onSelect(area.code)}><strong>{area.name}</strong><span>{area.district} / {area.administrative_dong}</span></button>)}
    </div>}
  </section>;
}
