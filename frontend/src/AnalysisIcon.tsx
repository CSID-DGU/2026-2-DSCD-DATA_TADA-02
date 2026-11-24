import type { ReactNode } from 'react';

const paths: Record<'pin' | 'coins' | 'store' | 'sparkle' | 'info', ReactNode> = {
  pin: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  coins: <><ellipse cx="15" cy="5.5" rx="6" ry="2.5" /><path d="M9 5.5v5m12-5v10c0 1.4-2.7 2.5-6 2.5m0-5c3.3 0 6-1.1 6-2.5" /><ellipse cx="8" cy="13" rx="6" ry="2.5" /><path d="M2 13v6c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-6M2 16c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5" /></>,
  store: <><path d="M4 10v11h16V10M10 21v-6h4v6M3 4h18l2 6a3 3 0 0 1-5 2 3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-5-2l2-6Zm4 0-1 6m6-6v6m5-6 1 6" /></>,
  sparkle: <path fill="currentColor" stroke="none" d="M12 1.5c.6 0 1 .4 1.2 1l1.2 4.2a4.4 4.4 0 0 0 2.9 2.9l4.2 1.2a1.2 1.2 0 0 1 0 2.4l-4.2 1.2a4.4 4.4 0 0 0-2.9 2.9l-1.2 4.2a1.2 1.2 0 0 1-2.4 0l-1.2-4.2a4.4 4.4 0 0 0-2.9-2.9l-4.2-1.2a1.2 1.2 0 0 1 0-2.4l4.2-1.2a4.4 4.4 0 0 0 2.9-2.9l1.2-4.2c.2-.6.6-1 1.2-1Z" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5m0-8v.1" /></>,
};

export default function AnalysisIcon({ name }: { name: keyof typeof paths }) {
  return <svg className="analysis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
