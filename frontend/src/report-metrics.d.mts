import type { ComparisonItem, Rental } from './types';
export const PYEONG_M2: number;
export function isRentEstimateSample(rental: Rental): boolean;
export function estimateRent(rentals: Rental[], areaM2: number, quarterlySales: number | null | undefined, floor?: string): {
  count: number; unitRent: number | null; monthlyRent: number | null; salesRatio: number | null;
};
export function averageOutlook(salesRate: number | null | undefined, storeRate: number | null | undefined, transactionRate: number | null | undefined): string;
export function overviewSituation(salesRate: number | null | undefined, storeRate: number | null | undefined, transactionRate: number | null | undefined): {
  label: string; tone: 'neutral' | 'negative' | 'positive' | 'pressure';
};
export function overviewBarMaxima(items: Pick<ComparisonItem, 'observations'>[], quarter: string, previousQuarter: string): {
  total_sales_krw: number; store_count: number; transaction_count: number;
};
export function overviewBarRatio(value: number | null, maximum: number): number;
