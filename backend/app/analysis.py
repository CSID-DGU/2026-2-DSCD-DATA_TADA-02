import math

from fastapi import HTTPException

from .db import Database
from .schemas import (
    Area, ComparisonItem, ComparisonResponse, CurrentMetrics, DetailResponse,
    Metadata, Observation, QueryContext, Store,
)


def divide(value: float | None, denominator: float | None) -> float | None:
    return value / denominator if value is not None and denominator is not None and denominator > 0 else None


def yoy(value: float | None, old: float | None) -> float | None:
    return (value / old - 1) * 100 if value is not None and old is not None and old > 0 else None


def competition_type(sales: float | None, stores: float | None) -> str:
    if sales is None or stores is None:
        return "자료 부족"
    if sales == 0 or stores == 0:
        return "변화 없음 / 경계"
    return {
        (True, True): "시장확장형", (True, False): "매출개선형",
        (False, False): "시장축소형", (False, True): "경쟁압박형",
    }[sales > 0, stores > 0]


def distance_m(lat1, lon1, lat2, lon2):
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = a2 - a1, math.radians(lon2 - lon1)
    hav = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(hav)))


class AnalysisService:
    def __init__(self, db: Database):
        self.db = db
        self.catalog = {a["code"]: a for a in db.areas()}

    def area(self, code: str) -> Area:
        if code not in self.catalog:
            raise HTTPException(404, "상권 코드를 찾을 수 없습니다.")
        return Area.model_validate(self.catalog[code])

    def observations(self, snapshot: dict) -> list[Observation]:
        rows = snapshot["observations"]
        by_quarter = {r["quarter"]: r for r in rows}
        result = []
        for row in rows:
            previous = by_quarter.get(f"{int(row['quarter'][:4]) - 1}{row['quarter'][4:]}")
            result.append(Observation(
                **row, average_sales_krw=divide(row["total_sales_krw"], row["store_count"]),
                sales_yoy_pct=yoy(row["total_sales_krw"], previous["total_sales_krw"] if previous else None),
                stores_yoy_pct=yoy(row["store_count"], previous["store_count"] if previous else None),
            ))
        return result

    def current(self, rows: list[Observation], quarter: str) -> CurrentMetrics | None:
        row = next((r for r in rows if r.quarter == quarter), None)
        if row is None:
            return None
        prior_quarter = f"{int(quarter[:4]) - 1}{quarter[4:]}"
        previous = next((r for r in rows if r.quarter == prior_quarter), None)
        return CurrentMetrics(
            **{k: getattr(row, k) for k in ["total_sales_krw", "store_count", "transaction_count", "average_sales_krw", "sales_yoy_pct", "stores_yoy_pct"]},
            transactions_per_store=divide(row.transaction_count, row.store_count),
            average_payment_krw=divide(row.total_sales_krw, row.transaction_count),
            average_sales_yoy_pct=yoy(row.average_sales_krw, previous.average_sales_krw if previous else None),
            competition_type=competition_type(row.sales_yoy_pct, row.stores_yoy_pct),
        )

    def detail(self, code: str, quarter: str) -> DetailResponse:
        area = self.area(code)
        return self._detail(area, quarter, self.db.snapshot(code, quarter))

    def _detail(self, area: Area, quarter: str, snapshot: dict | None) -> DetailResponse:
        if snapshot is None:
            return DetailResponse(
                meta=Metadata(data_version="demo-v1", quarter=quarter), area=area, current=None,
                observations=[], forecast=None, demand={}, rentals=[], stores=[],
                missing_reason="이 상권과 분기의 분석 자료는 아직 연결되지 않았습니다.",
            )
        observations = self.observations(snapshot)
        current = self.current(observations, quarter)
        meta = Metadata(data_version=snapshot["data_version"], quarter=quarter, data_mode=self.db.data_mode)
        if self.db.data_mode == "supabase":
            meta.warning = "매출, 거래, 점포와 유동인구는 서울시 상권 통계입니다. 예측은 Ridge 기준 모델 결과입니다. 임대 광고와 카페 메뉴는 수집 시점의 공개 자료입니다."
        return DetailResponse(
            meta=meta, area=area, current=current, observations=observations,
            forecast=snapshot["forecast"], demand=snapshot["demand"],
            rentals=snapshot["rentals"], stores=snapshot["stores"], boundary=None,
            missing_reason=None if current is not None else "선택한 분기의 카페 통계가 없습니다.",
        )

    def compare(self, query: QueryContext) -> ComparisonResponse:
        areas = [self.area(code) for code in query.area_codes]
        snapshots = self.db.snapshots(query.area_codes, query.quarter)
        details = [self._detail(area, query.quarter, snapshots.get(area.code)) for area in areas]
        return ComparisonResponse(meta=details[0].meta, items=[
            ComparisonItem(area=d.area, metrics=d.current, rentals=d.rentals, missing_reason=d.missing_reason)
            for d in details
        ])

    def nearby(self, code: str, quarter: str, listing_id: str, radius_m: int):
        if self.db.remote:
            self.area(code)
            result = self.db.remote.nearby_candidates(code, listing_id, radius_m)
            if result is None:
                raise HTTPException(404, "이 상권의 기준 매물을 찾을 수 없습니다.")
            latitude, longitude, candidates = result
            stores = [Store.model_validate(item) for item in candidates]
        else:
            detail = self.detail(code, quarter)
            listing = next((r for r in detail.rentals if r.id == listing_id), None)
            if listing is None:
                raise HTTPException(404, "이 상권의 기준 매물을 찾을 수 없습니다.")
            latitude, longitude, stores = listing.latitude, listing.longitude, detail.stores
        results = []
        for store in stores:
            distance = distance_m(latitude, longitude, store.latitude, store.longitude)
            if distance <= radius_m:
                results.append(store.model_copy(update={"distance_m": round(distance, 1)}))
        return sorted(results, key=lambda s: (s.distance_m, s.id))

    def brand_menu(self, store_id: str):
        return self.db.remote.brand_menu(store_id) if self.db.remote else []
