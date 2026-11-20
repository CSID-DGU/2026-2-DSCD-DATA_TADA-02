import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Area, Rental, Store } from './types';

const escape = (text: string) => text.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

// Adapted from the requested financial challenge v5 map: area-weighted district/dong centers,
// three zoom levels, always-visible labels and OSM tiles. Selection is now explicit and multiple.
function aggregate(items: Area[], key: 'district' | 'administrative_dong') {
  const groups = new Map<string, Area[]>();
  for (const item of items) {
    const id = key === 'district' ? item.district : `${item.district}::${item.administrative_dong}`;
    groups.set(id, [...(groups.get(id) || []), item]);
  }
  return [...groups.values()].map(group => {
    const weight = group.reduce((sum, a) => sum + Math.max(1, a.area_m2), 0);
    return { name: group[0][key], district: group[0].district, count: group.length,
      latitude: group.reduce((sum, a) => sum + a.latitude * Math.max(1, a.area_m2), 0) / weight,
      longitude: group.reduce((sum, a) => sum + a.longitude * Math.max(1, a.area_m2), 0) / weight };
  });
}

function baseMap(element: HTMLDivElement, center: L.LatLngExpression, zoom: number) {
  const map = L.map(element, { preferCanvas: true }).setView(center, zoom);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
  }).addTo(map);
  L.control.scale({ imperial: false }).addTo(map);
  return map;
}

function label(layer: L.LayerGroup, latitude: number, longitude: number, text: string, small = '') {
  L.marker([latitude, longitude], { interactive: false, keyboard: false, icon: L.divIcon({
    className: 'map-label', html: `<strong>${escape(text)}</strong>${small ? `<small>${escape(small)}</small>` : ''}`,
    iconSize: [105, 40], iconAnchor: [52, 20],
  }) }).addTo(layer);
}

export default function MapPicker({ areas, selected, onToggle }: { areas: Area[]; selected: string[]; onToggle: (code: string) => void }) {
  const target = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const [district, setDistrict] = useState('');
  const [dong, setDong] = useState('');
  const [query, setQuery] = useState('');
  const [tileError, setTileError] = useState(false);
  const [viewport, setViewport] = useState(0);
  const districts = [...new Set(areas.map(a => a.district))].sort();
  const dongs = [...new Set(areas.filter(a => a.district === district).map(a => a.administrative_dong))].sort();
  const filtered = areas.filter(a => (!district || a.district === district) && (!dong || a.administrative_dong === dong)
    && (!query || `${a.name} ${a.district} ${a.administrative_dong}`.includes(query)));

  useEffect(() => {
    if (!target.current) return;
    const map = baseMap(target.current, [37.5665, 126.978], 11);
    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);
    map.eachLayer(layer => { if (layer instanceof L.TileLayer) layer.on('tileerror', () => setTileError(true)); });
    const refreshViewport = () => setViewport(v => v + 1);
    map.on('zoomend', () => {
      // Browsing scope follows zoom level; selected comparison candidates stay untouched.
      const zoom = map.getZoom();
      if (zoom <= 14) setDong('');
      if (zoom <= 12) setDistrict('');
      refreshViewport();
    });
    map.on('moveend', refreshViewport);
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(target.current);
    return () => { resize.disconnect(); map.remove(); mapRef.current = null; layerRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current, layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    const zoom = map.getZoom();
    // Explicit text search keeps its results; zooming out restores the parent browsing level.
    let values = filtered;
    if (!query && !district && zoom > 12) {
      const center = map.getCenter();
      const nearest = areas.reduce<Area | null>((best, a) => !best || center.distanceTo([a.latitude, a.longitude]) < center.distanceTo([best.latitude, best.longitude]) ? a : best, null);
      if (nearest) values = areas.filter(a => a.district === nearest.district);
    }
    if (!query && zoom <= 12) {
      for (const group of aggregate(areas, 'district')) {
        L.circleMarker([group.latitude, group.longitude], { radius: 26 + Math.min(10, Math.sqrt(group.count)), color: '#087c87', fillColor: '#009da5', fillOpacity: .7, weight: 2 })
          .on('click', () => { setDistrict(group.name); setDong(''); map.setView([group.latitude, group.longitude], 13); }).addTo(layer);
        label(layer, group.latitude, group.longitude, group.name, `상권 ${group.count}개`);
      }
    } else if (!query && zoom <= 14) {
      for (const group of aggregate(values, 'administrative_dong')) {
        L.circleMarker([group.latitude, group.longitude], { radius: 27, color: '#078e98', fillColor: '#28aeb5', fillOpacity: .7, dashArray: '5 3' })
          .on('click', () => { setDistrict(group.district); setDong(group.name); map.setView([group.latitude, group.longitude], 15); }).addTo(layer);
        label(layer, group.latitude, group.longitude, group.name, `${group.count}개 상권`);
      }
    } else {
      for (const area of values) {
        const active = selected.includes(area.code);
        L.circle([area.latitude, area.longitude], { radius: Math.max(70, area.radius_m), color: active ? '#092347' : '#009da5', weight: active ? 4 : 2, fillColor: '#009da5', fillOpacity: active ? .55 : .2 })
          .bindTooltip(`${escape(area.name)}: ${active ? '선택 해제' : '후보 추가'}`)
          .on('click', () => onToggle(area.code)).addTo(layer);
        label(layer, area.latitude, area.longitude, area.name, active ? '선택됨' : '');
      }
    }
  }, [areas, selected, district, dong, query, viewport, onToggle, filtered]);

  function focusDistrict(value: string) {
    setDistrict(value); setDong(''); setQuery('');
    const values = areas.filter(a => !value || a.district === value);
    if (values.length) mapRef.current?.fitBounds(values.map(a => [a.latitude, a.longitude] as [number, number]), { padding: [40, 40], maxZoom: value ? 13 : 11 });
  }

  return <div className="map-selection">
    <aside className="panel location-controls">
      <h2>관심 상권 찾기</h2>
      <label>상권 이름 검색<input value={query} placeholder="성수역, 연남동 등" onChange={e => { setQuery(e.target.value); setDistrict(''); setDong(''); }} /></label>
      <label>자치구<select value={district} onChange={e => focusDistrict(e.target.value)}><option value="">서울 전체</option>{districts.map(d => <option key={d}>{d}</option>)}</select></label>
      <label>행정동<select value={dong} disabled={!district} onChange={e => { const value = e.target.value; setDong(value); const values = areas.filter(a => a.district === district && (!value || a.administrative_dong === value)); if (values.length) mapRef.current?.fitBounds(values.map(a => [a.latitude, a.longitude] as [number, number]), { maxZoom: 15 }); }}><option value="">전체 행정동</option>{dongs.map(d => <option key={d}>{d}</option>)}</select></label>
      <p className="muted">{filtered.length.toLocaleString()}개 상권 / 선택 {selected.length}개</p>
      <div className="area-results" aria-label="상권 검색 결과">{(query || district ? filtered : areas.filter(a => selected.includes(a.code))).map(a => <button className={selected.includes(a.code) ? 'area-result selected' : 'area-result'} key={a.code} onClick={() => onToggle(a.code)} aria-pressed={selected.includes(a.code)}><strong>{a.name}</strong><small>{a.district} / {a.administrative_dong}</small><span>{selected.includes(a.code) ? '선택 해제' : '+ 후보 추가'}</span></button>)}{!query && !district && <p className="muted">지도에서 자치구를 선택하거나 이름을 검색하세요.</p>}</div>
    </aside>
    <div className="map-shell"><div className="map-breadcrumb"><button onClick={() => focusDistrict('')}>서울 전체</button><span>› {district || '자치구'} › {dong || '행정동'} › 상권</span></div><div ref={target} className="map-canvas" role="region" aria-label="서울시 후보 상권 선택 지도" /><p className="map-caption">원은 탐색용 표시이며 실제 상권 경계가 아닙니다. 확대와 이동만으로 후보가 선택되지는 않습니다.</p>{tileError && <p role="status">배경지도를 불러오지 못했습니다. 목록과 검색으로 선택할 수 있습니다.</p>}</div>
  </div>;
}

export function LocationMap({ area, rentals, stores, selectedId, radius, onSelect, demo }: { area: Area; rentals: Rental[]; stores: Store[]; selectedId: string; radius?: number; onSelect: (id: string) => void; demo: boolean }) {
  const element = useRef<HTMLDivElement>(null);
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    if (!element.current) return;
    const map = baseMap(element.current, [area.latitude, area.longitude], 16);
    const layer = L.layerGroup().addTo(map);
    map.eachLayer(item => { if (item instanceof L.TileLayer) item.on('tileerror', () => setTileError(true)); });
    const listing = rentals.find(r => r.id === selectedId);
    const ring = radius && listing ? L.circle([listing.latitude, listing.longitude], { radius, color: '#009da5', dashArray: '7 6', fillOpacity: .07 }).addTo(layer) : null;
    for (const rental of rentals) {
      const selected = rental.id === selectedId;
      L.circleMarker([rental.latitude, rental.longitude], { radius: selected ? 13 : 9, color: '#fff', weight: 3, fillColor: selected ? '#071d43' : '#009da5', fillOpacity: 1 })
        .bindTooltip(escape(rental.title)).on('click', () => onSelect(rental.id)).addTo(layer);
    }
    for (const store of stores) {
      L.circleMarker([store.latitude, store.longitude], { radius: stores.length > 15 ? 6 : 9, color: '#fff', weight: 2, fillColor: '#009da5', fillOpacity: 1 }).bindTooltip(escape(store.name)).addTo(layer);
      if (stores.length <= 12) label(layer, store.latitude, store.longitude, store.name);
    }
    if (ring) map.fitBounds(ring.getBounds(), { padding: [22, 22], maxZoom: 17 });
    else if (rentals.length + stores.length > 0) {
      map.fitBounds(L.latLngBounds([...rentals, ...stores].map(item => [item.latitude, item.longitude])), { padding: [24, 24], maxZoom: 17 });
    }
    const observer = new ResizeObserver(() => map.invalidateSize()); observer.observe(element.current);
    return () => { observer.disconnect(); map.remove(); };
  }, [area, rentals, stores, selectedId, radius, onSelect]);
  return <div className="map-shell"><div ref={element} className="map-canvas detail-map" role="region" aria-label="임대 매물과 카페 지도" /><p className="map-caption">{demo ? '개발용 예시 위치입니다.' : '공개 자료에서 확보한 위치입니다.'}</p>{tileError && <p role="status">배경지도를 불러오지 못했습니다. 왼쪽 목록에서 위치와 조건을 볼 수 있습니다.</p>}</div>;
}
