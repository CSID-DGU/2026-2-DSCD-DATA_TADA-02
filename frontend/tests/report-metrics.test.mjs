import test from 'node:test';
import assert from 'node:assert/strict';
import { averageOutlook, estimateRent, overviewBarMaxima, overviewBarRatio, overviewSituation } from '../src/report-metrics.mjs';

test('rent uses area-weighted unit rent and monthly, not quarterly, sales', () => {
  const rentals = [
    { floor: '1층', area_m2: 20, monthly_rent_krw: 1000000 },
    { floor: '1층', area_m2: 80, monthly_rent_krw: 2000000 },
    { floor: '2층', area_m2: 50, monthly_rent_krw: 500000 },
    { floor: '1층', area_m2: 0, monthly_rent_krw: 9999999 },
    { floor: '1층', area_m2: 20, monthly_rent_krw: null },
  ];
  assert.deepEqual(estimateRent(rentals, 50, 18000000, '1층'), {
    count: 2, unitRent: 30000, monthlyRent: 1500000, salesRatio: 25,
  });
  assert.equal(estimateRent(rentals, 100, 18000000, '1층').monthlyRent, 3000000);
  assert.equal(estimateRent(rentals, 50, 0, '1층').salesRatio, null);
  assert.equal(estimateRent(rentals, 50, null, '1층').salesRatio, null);
  assert.equal(estimateRent(rentals, 50, 18000000, '3층').monthlyRent, null);
  assert.equal(estimateRent([{ area_m2: 50, monthly_rent_krw: 0 }], 50, 300, '').salesRatio, 0);
});

test('same growth directions can imply different per-store conditions', () => {
  assert.match(averageOutlook(20, 10, 15), /매출 증가, 평균 거래 증가/);
  assert.match(averageOutlook(10, 20, 15), /매출 감소, 평균 거래 감소/);
  assert.match(averageOutlook(-5, -20, -10), /매출 증가, 평균 거래 증가/);
  assert.match(averageOutlook(10, 10, 10), /매출 유지, 평균 거래 유지/);
  assert.match(averageOutlook(null, 10, 10), /자료 부족/);
});

test('overview badges distinguish observed growth, pressure, contraction and missing comparisons', () => {
  assert.equal(overviewSituation(20, 10, 15).tone, 'positive');
  assert.equal(overviewSituation(10, 20, 15).tone, 'pressure');
  assert.equal(overviewSituation(-12, -4, -10).tone, 'negative');
  assert.equal(overviewSituation(10, -2, -5).tone, 'neutral');
  assert.equal(overviewSituation(null, 10, 10).label, '비교 자료 부족');
});

test('overview uses shared maxima across candidates and both comparison quarters', () => {
  const entries = [
    { observations: [
      { quarter: '2025Q2', total_sales_krw: 500, store_count: 8, transaction_count: 1_000 },
      { quarter: '2026Q2', total_sales_krw: null, store_count: 6, transaction_count: null },
      { quarter: '2026Q1', total_sales_krw: 9_999, store_count: 120, transaction_count: 1_000_000 },
    ] },
    { observations: [{ quarter: '2026Q2', total_sales_krw: 400, store_count: 10, transaction_count: 25_000 }] },
    { observations: [{ quarter: '2026Q2', total_sales_krw: 480, store_count: 9, transaction_count: 100_000 }] },
  ];
  const maxima = overviewBarMaxima(entries, '2026Q2', '2025Q2');
  assert.deepEqual(maxima, { total_sales_krw: 500, store_count: 10, transaction_count: 100_000 });
  for (const [value, ratio] of [[100_000, 1], [25_000, .5], [1_000, .1], [0, 0], [null, 0]]) {
    assert.equal(overviewBarRatio(value, maxima.transaction_count), ratio);
  }
  assert.equal(overviewBarRatio(null, 0), 0);
});
