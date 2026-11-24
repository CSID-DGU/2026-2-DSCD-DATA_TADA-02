export const PYEONG_M2 = 3.305785;

export function isRentEstimateSample(rental) {
  return rental.area_m2 > 0 && rental.monthly_rent_krw != null;
}

export function estimateRent(rentals, areaM2, quarterlySales, floor = '') {
  const eligible = rentals.filter(r => (!floor || r.floor === floor) && isRentEstimateSample(r));
  const totalArea = eligible.reduce((sum, r) => sum + r.area_m2, 0);
  const unitRent = totalArea > 0 ? eligible.reduce((sum, r) => sum + r.monthly_rent_krw, 0) / totalArea : null;
  const monthlyRent = unitRent == null || !(areaM2 > 0) ? null : unitRent * areaM2;
  return { count: eligible.length, unitRent, monthlyRent,
    salesRatio: monthlyRent != null && quarterlySales > 0 ? monthlyRent / (quarterlySales / 3) * 100 : null };
}

export function averageOutlook(salesRate, storeRate, transactionRate) {
  if (salesRate == null || storeRate == null || transactionRate == null) return '전년 동분기 비교 자료 부족';
  const sales = salesRate > storeRate ? '증가' : salesRate < storeRate ? '감소' : '유지';
  const transactions = transactionRate > storeRate ? '증가' : transactionRate < storeRate ? '감소' : '유지';
  return `점포당 평균 매출 ${sales}, 평균 거래 ${transactions}`;
}

export function overviewSituation(salesRate, storeRate, transactionRate) {
  if (salesRate == null || storeRate == null || transactionRate == null) {
    return { label: '비교 자료 부족', tone: 'neutral' };
  }
  if (salesRate < 0 && storeRate < 0 && transactionRate < 0) {
    return { label: '상권 위축 흐름', tone: 'negative' };
  }
  if (salesRate > 0 && transactionRate > 0) {
    if (salesRate > storeRate && transactionRate > storeRate) {
      return { label: '평균 여건 개선', tone: 'positive' };
    }
    if (salesRate < storeRate && transactionRate < storeRate) {
      return { label: '점포당 평균 감소', tone: 'pressure' };
    }
  }
  return { label: '지표별 변화', tone: 'neutral' };
}

export function overviewBarMaxima(items, quarter, previousQuarter) {
  const maxima = { total_sales_krw: 0, store_count: 0, transaction_count: 0 };
  for (const { observations } of items) {
    for (const row of observations) {
      if (row.quarter !== quarter && row.quarter !== previousQuarter) continue;
      for (const key of Object.keys(maxima)) {
        maxima[key] = Math.max(maxima[key], row[key] ?? 0);
      }
    }
  }
  return maxima;
}

export function overviewBarRatio(value, maximum) {
  return value > 0 && maximum > 0 ? value / maximum : 0;
}
