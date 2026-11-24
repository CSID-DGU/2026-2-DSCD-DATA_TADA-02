import type { ReactNode } from 'react';
import type { MenuItem, Store } from './types';
import './location-stores.css';

function MenuList({ items }: { items: MenuItem[] }) {
  return <ul className="store-menu">{items.map((item, index) =>
    <li key={index}>
      {item.source_url
        ? <a href={item.source_url} target="_blank" rel="noopener noreferrer">{item.name}</a>
        : <span>{item.name}</span>}
      <strong>{item.price_krw == null ? '가격 미확보' : `${item.price_krw.toLocaleString('ko-KR')}원`}</strong>
      {item.source_date && <small>{item.source_date.slice(0, 10)}</small>}
    </li>
  )}</ul>;
}

type CardInteraction = { selected: boolean; onSelect: () => void; onHover: (hovered: boolean) => void };

export function LocationCard({ className, id, title, selected, onSelect, onHover, children }: CardInteraction & {
  className: string; id: string; title: string; children: ReactNode;
}) {
  return <article className={`${className} location-card${selected ? ' selected' : ''}`}
    data-location-id={id}
    onMouseEnter={() => onHover(true)} onMouseLeave={() => onHover(false)}
    onClick={event => {
      if (event.target instanceof Element && !event.target.closest('a, button, summary')) onSelect();
    }}>
    <h3><button type="button" className="rental-name" aria-pressed={selected} onClick={onSelect}>{title}</button></h3>
    {children}
  </article>;
}

export function StoreCard({ store, ...interaction }: CardInteraction & { store: Store }) {
  return <LocationCard className="store-row" id={store.id} title={store.name} {...interaction}>
    {store.address && <small>{store.address}</small>}
    <small>{store.distance_m != null && `${store.distance_m.toLocaleString('ko-KR')}m / `}점포 자료 {store.observed_at.slice(0, 10)}</small>
    {store.menu.length ? <details className="store-menu-details">
      <summary>매장별 메뉴 {store.menu.length}건</summary>
      <MenuList items={store.menu} />
    </details> : <small>매장별 메뉴 미확보</small>}
  </LocationCard>;
}
