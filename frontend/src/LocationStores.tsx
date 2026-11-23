import { useEffect, useState } from 'react';
import { api } from './api';
import type { BrandMenuItem, MenuItem, Store } from './types';
import './location-stores.css';

function MenuList({ items, priceLabel }: { items: MenuItem[]; priceLabel?: string }) {
  return <ul className="store-menu">{items.map((item, index) =>
    <li key={index}>
      {item.source_url
        ? <a href={item.source_url} target="_blank" rel="noopener noreferrer">{item.name}</a>
        : <span>{item.name}</span>}
      <strong>{item.price_krw == null ? '가격 미확보' : `${item.price_krw.toLocaleString('ko-KR')}원`}</strong>
      {(item.source_date || priceLabel) && <small>{[priceLabel, item.source_date?.slice(0, 10)].filter(Boolean).join(' / ')}</small>}
    </li>
  )}</ul>;
}

function BrandMenu({ storeId, brand }: { storeId: string; brand: string }) {
  const [items, setItems] = useState<BrandMenuItem[] | null>(null);
  const [error, setError] = useState('');
  const [opened, setOpened] = useState(false);

  useEffect(() => {
    if (!opened || items) return;
    const controller = new AbortController();
    setError('');
    api<BrandMenuItem[]>(`/cafes/${encodeURIComponent(storeId)}/brand-menu`, { signal: controller.signal })
      .then(values => { if (!controller.signal.aborted) setItems(values); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [opened, items, storeId]);

  const official = items?.filter(item => item.channel === 'official_menu') ?? [];
  const gifts = items?.filter(item => item.channel === 'gift_catalog') ?? [];
  return <details className="store-menu-details" onToggle={event => setOpened(event.currentTarget.open)}>
    <summary>{brand} 본사 메뉴와 상품</summary>
    {opened && <>
      <small>본사 참고 자료입니다. 이 매장의 판매 여부와 가격은 매장에 확인하세요.</small>
      {error ? <small role="alert">{error}</small> : !items ? <small role="status">본사 자료를 불러오는 중입니다.</small> :
        items.length === 0 && <small>표시할 본사 자료가 없습니다.</small>}
      {official.length > 0 && <MenuList items={official} />}
      {gifts.length > 0 && <MenuList items={gifts} priceLabel="기프트 상품" />}
    </>}
  </details>;
}

export function StoreCard({ store }: { store: Store }) {
  return <article className="store-row">
    <h3>{store.name}</h3>
    {store.address && <small>{store.address}</small>}
    <small>{store.distance_m != null && `${store.distance_m.toLocaleString('ko-KR')}m / `}점포 자료 {store.observed_at.slice(0, 10)}</small>
    {store.menu.length ? <details className="store-menu-details">
      <summary>매장별 메뉴 {store.menu.length}건</summary>
      <MenuList items={store.menu} />
    </details> : <small>매장별 메뉴 미확보</small>}
    {store.brand && <BrandMenu storeId={store.id} brand={store.brand} />}
  </article>;
}
