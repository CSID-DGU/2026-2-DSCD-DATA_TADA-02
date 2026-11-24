import { useEffect, useRef, useState } from 'react';
import type { PointerEvent, ReactNode } from 'react';
import { cardScrollTarget } from './selection.mjs';
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
  const [edges, setEdges] = useState({ previous: false, next: false });

  function updateEdges(viewport: HTMLDivElement) {
    const { max } = scrollGeometry(viewport);
    const previous = viewport.scrollLeft > 1;
    const next = viewport.scrollLeft < max - 1;
    setEdges(old => old.previous === previous && old.next === next ? old : { previous, next });
  }

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const observer = new ResizeObserver(() => updateEdges(viewport));
    observer.observe(viewport);
    updateEdges(viewport);
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
    <div ref={viewportRef} className="comparison-cards" data-scrollable={edges.previous || edges.next}
      onScroll={event => updateEdges(event.currentTarget)}
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
      aria-disabled={!edges.previous} tabIndex={edges.previous ? 0 : -1}
      onClick={() => { if (edges.previous) move(-1); }}>
      <span aria-hidden="true">‹</span>
    </button>
    <button type="button" className="comparison-arrow comparison-arrow-next" aria-label="다음 후보 카드"
      aria-disabled={!edges.next} tabIndex={edges.next ? 0 : -1}
      onClick={() => { if (edges.next) move(1); }}>
      <span aria-hidden="true">›</span>
    </button>
  </div>;
}
