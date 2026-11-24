import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, PointerEvent, ReactNode } from 'react';
import { cardScrollTarget, cardWindow } from './selection.mjs';
import './comparison-carousel.css';

type Drag = { id: number; x: number; y: number; start: number; active: boolean };

function scrollGeometry(viewport: HTMLDivElement) {
  const [first, second] = viewport.children;
  const step = second && first ? second.getBoundingClientRect().left - first.getBoundingClientRect().left : 0;
  return { step, max: Math.max(0, viewport.scrollWidth - viewport.clientWidth) };
}

export default function ComparisonCarousel({ children }: { children: ReactNode }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const gesture = useRef<Drag | null>(null);
  const ignoreClick = useRef(false);
  const [position, setPosition] = useState({ start: 0, lastStart: 0, total: 0 });
  const { start: firstCard, lastStart, total } = position;
  const firstVisible = firstCard + 1;
  const lastVisible = firstCard + total - lastStart;
  const rangeText = firstVisible === lastVisible ? `${firstVisible}번째` : `${firstVisible}~${lastVisible}번째`;
  const previous = firstCard > 0;
  const next = firstCard < lastStart;

  function updatePosition(viewport: HTMLDivElement) {
    const { step, max } = scrollGeometry(viewport);
    const current = cardWindow(viewport.scrollLeft, step, max, viewport.children.length);
    setPosition(old => old.start === current.start && old.lastStart === current.lastStart && old.total === current.total ? old : current);
  }

  function slideTo(index: number) {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const { step, max } = scrollGeometry(viewport);
    // Keep the bar and cards in sync while the thumb is being dragged.
    viewport.scrollTo({ left: cardScrollTarget(0, step, max, index), behavior: 'instant' });
    updatePosition(viewport);
  }

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const observer = new ResizeObserver(() => updatePosition(viewport));
    observer.observe(viewport);
    updatePosition(viewport);
    return () => observer.disconnect();
  }, []);

  function move(direction: -1 | 1) {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const { step, max } = scrollGeometry(viewport);
    viewport.scrollTo({ left: cardScrollTarget(viewport.scrollLeft, step, max, direction) });
  }

  function start(event: PointerEvent<HTMLDivElement>) {
    ignoreClick.current = false;
    if (event.pointerType !== 'mouse' || event.button !== 0) return;
    if (event.target instanceof Element && event.target.closest('button, a, input, select, textarea')) return;
    const viewport = event.currentTarget;
    if (scrollGeometry(viewport).max <= 1) return;
    gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, start: viewport.scrollLeft, active: false };
  }

  function drag(event: PointerEvent<HTMLDivElement>) {
    const state = gesture.current;
    if (!state || state.id !== event.pointerId) return;
    const viewport = event.currentTarget;
    const dx = event.clientX - state.x;
    if (!state.active) {
      if (Math.abs(dx) < 6 || Math.abs(dx) <= Math.abs(event.clientY - state.y)) return;
      state.active = true;
      ignoreClick.current = true;
      viewport.classList.add('is-dragging');
      viewport.setPointerCapture(event.pointerId);
    }
    event.preventDefault();
    viewport.scrollLeft = state.start - dx;
  }

  function finish(event: PointerEvent<HTMLDivElement>, cancelled = false) {
    const state = gesture.current;
    if (!state || state.id !== event.pointerId) return;
    gesture.current = null;
    if (!state.active) return;
    const viewport = event.currentTarget;
    const { step, max } = scrollGeometry(viewport);
    const distance = viewport.scrollLeft - state.start;
    const startTarget = cardScrollTarget(state.start, step, max);
    let target = startTarget;
    if (!cancelled && Math.abs(distance) >= Math.min(48, step * .2)) {
      target = cardScrollTarget(viewport.scrollLeft, step, max);
      if (target === startTarget) target = cardScrollTarget(state.start, step, max, distance > 0 ? 1 : -1);
    }
    viewport.classList.remove('is-dragging');
    viewport.scrollTo({ left: target });
  }

  return <div className="comparison-carousel">
    <div className="comparison-carousel-body">
      <div ref={viewportRef} className="comparison-cards" data-scrollable={lastStart > 0}
        onScroll={event => updatePosition(event.currentTarget)}
        onPointerDown={start}
        onPointerMove={drag}
        onPointerUp={event => finish(event)}
        onPointerCancel={event => finish(event, true)}
        onLostPointerCapture={event => finish(event, true)}
        onPointerLeave={event => { if (!gesture.current?.active) finish(event, true); }}
        onClickCapture={event => {
          if (!ignoreClick.current || event.detail === 0) return;
          ignoreClick.current = false;
          event.preventDefault();
          event.stopPropagation();
        }}>
        {children}
      </div>
      <button type="button" className="comparison-arrow comparison-arrow-previous" aria-label="이전 후보 카드"
        aria-disabled={!previous} tabIndex={previous ? 0 : -1}
        onClick={() => { if (previous) move(-1); }}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5.5-6 6.5 6 6.5" /></svg>
      </button>
      <button type="button" className="comparison-arrow comparison-arrow-next" aria-label="다음 후보 카드"
        aria-disabled={!next} tabIndex={next ? 0 : -1}
        onClick={() => { if (next) move(1); }}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5.5 6 6.5-6 6.5" /></svg>
      </button>
    </div>
    {total > 0 && <div className="comparison-carousel-position">
      <input type="range" className="comparison-range" aria-label="비교 카드 위치"
        aria-valuetext={`${rangeText} / 전체 ${total}개`}
        min={0} max={lastStart} value={firstCard} disabled={lastStart === 0}
        style={{ '--comparison-thumb-width': `${(total - lastStart) / total * 100}%` } as CSSProperties}
        onChange={event => slideTo(event.currentTarget.valueAsNumber)} />
      <span aria-hidden="true">{rangeText} / 전체 {total}개</span>
    </div>}
  </div>;
}
