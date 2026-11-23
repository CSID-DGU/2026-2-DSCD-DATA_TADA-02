"""Read the published statistical snapshot and collected locations."""
from calendar import monthrange
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text

from .config import ROOT, Settings
from .location_data import CAFE_FIELDS, RENTAL_FIELDS, area_stores, brand_menu, nearby_candidates, rentals_by_area

CATALOG = text("""
    select area_code as code, name, category, coalesce(district, '') as district,
           coalesce(administrative_dong, '') as administrative_dong,
           latitude, longitude, area_m2, radius_m
    from data_tada.areas
    where map_selectable
    order by area_code
""")

SNAPSHOTS = text("""
    select a.code, history.observations, m.sales_shares, m.transaction_count,
           p.floating_population_count, p.floating_population_shares,
           run.model_version, forecasts.points
    from unnest(cast(:codes as text[])) as a(code)
    left join lateral (
        select jsonb_agg(jsonb_build_object(
            'quarter', to_char(q.quarter_start, 'YYYY"Q"Q'),
            'total_sales_krw', q.total_sales_krw,
            'transaction_count', q.transaction_count,
            'store_count', q.store_count
        ) order by q.quarter_start) as observations
        from data_tada.quarterly_metrics q
        where q.area_code = a.code and q.industry_code = 'CS100010' and q.quarter_start <= :quarter
    ) history on true
    left join data_tada.quarterly_metrics m
        on m.area_code = a.code and m.industry_code = 'CS100010' and m.quarter_start = :quarter
    left join data_tada.quarterly_population p on p.area_code = a.code and p.quarter_start = :quarter
    left join lateral (
        select model_version from data_tada.forecast_runs
        where industry_code = 'CS100010' and origin_quarter_start = :quarter
        order by generated_at desc, model_version desc limit 1
    ) run on true
    left join lateral (
        select jsonb_agg(jsonb_build_object(
            'quarter', to_char(f.target_quarter_start, 'YYYY"Q"Q'),
            'sales', f.predicted_sales_krw, 'stores', f.predicted_store_count
        ) order by f.target_quarter_start) as points
        from data_tada.quarterly_forecasts f
        where f.area_code = a.code and f.industry_code = 'CS100010'
          and f.origin_quarter_start = :quarter and f.model_version = run.model_version
    ) forecasts on true
""")

DATA_VERSION = "seoul-cafe-20261106-locations-20261120"


def quarter_start(quarter: str) -> date:
    return date(int(quarter[:4]), 3 * (int(quarter[-1]) - 1) + 1, 1)


def percent_change(value, prior):
    return (value / prior - 1) * 100 if value is not None and prior is not None and prior > 0 else None


def distribution(total, shares, start: date, *, population: bool):
    if total is None or not shares:
        return None
    weekday_counts = [0] * 7
    for month in range(start.month, start.month + 3):
        for day in range(1, monthrange(start.year, month)[1] + 1):
            weekday_counts[date(start.year, month, day).weekday()] += 1
    prefix = "pop_share_" if population else "sale_share_"

    def bins(labels, first, denominators=None):
        output = []
        for offset, label in enumerate(labels):
            share = shares.get(f"{prefix}{first + offset:02d}")
            value = round(total * share) if share is not None else None
            if value is not None and denominators:
                value = round(value / denominators[offset], 2)
            output.append({"label": label, "value": value,
                           "share_pct": round(share * 100, 2) if share is not None else None})
        return output

    # Offsets follow the verified source share_dictionary.json. Sales uses counts, not amounts.
    return {
        "unit": "명 (추정)" if population else "건",
        "age_basis": "분기 합계", "weekday_basis": "해당 요일의 실제 일수로 나눈 일평균",
        "time_basis": "분기 합계",
        "age": bins(["10대", "20대", "30대", "40대", "50대", "60대 이상"], 2 if population else 40),
        "weekday": bins(list("월화수목금토일"), 14 if population else 25, weekday_counts),
        "time": bins(["00~06시", "06~11시", "11~14시", "14~17시", "17~21시", "21~24시"], 8 if population else 32),
    }


class SupabaseData:
    def __init__(self, settings: Settings):
        # libpq on Windows can fail to open a UTF-8 absolute path containing Korean text.
        certificate = settings.supabase_sslrootcert
        if not certificate.is_absolute() and Path.cwd() != ROOT:
            certificate = ROOT / certificate
        self.engine = create_engine(
            settings.supabase_database_url.get_secret_value(),
            connect_args={
                "sslmode": "verify-full",
                "sslrootcert": str(certificate),
                "connect_timeout": 7,
            },
            pool_pre_ping=True, pool_size=3, max_overflow=2, pool_timeout=8,
            hide_parameters=True,
        )

    def check_ready(self):
        with self.engine.connect() as conn:
            conn.execute(text("select 1 from data_tada.quarterly_metrics limit 1")).scalar_one()
            conn.execute(text(RENTAL_FIELDS + " limit 0"))
            conn.execute(text(CAFE_FIELDS + " limit 0"))
            conn.execute(text("select 1 from data_tada.service_cafe_brand_menus limit 0"))

    def areas(self) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(CATALOG).mappings()]

    def snapshots(self, codes: list[str], quarter: str, *, include_stores: bool = False) -> dict:
        start = quarter_start(quarter)
        with self.engine.connect() as conn:
            rows = conn.execute(SNAPSHOTS, {"codes": codes, "quarter": start}).mappings().all()
            rentals = rentals_by_area(conn, codes)
            cafes = {code: area_stores(conn, code) for code in codes} if include_stores else {}
        result = {}
        for row in rows:
            observations = row["observations"] or []
            by_quarter = {item["quarter"]: item for item in observations}
            points = []
            for point in row["points"] or []:
                target = point["quarter"]
                prior = by_quarter.get(f"{int(target[:4]) - 1}{target[4:]}", {})
                sales, stores = point["sales"], point["stores"]
                points.append({
                    "quarter": target, "total_sales_krw": sales, "average_sales_krw": sales / stores if stores > 0 else None,
                    "sales_yoy_pct": percent_change(sales, prior.get("total_sales_krw")),
                    "stores_yoy_pct": percent_change(stores, prior.get("store_count")),
                })
            demand = {
                "transactions": distribution(row["transaction_count"], row["sales_shares"], start, population=False),
                "floating_population": distribution(row["floating_population_count"], row["floating_population_shares"],
                                                    start, population=True),
            }
            result[row["code"]] = {
                "data_version": DATA_VERSION,
                "observations": observations,
                "forecast": {
                    "model_version": row["model_version"],
                    "interval_method": "Ridge 기준 모델의 예측입니다. 점포당 평균 매출의 예측 구간은 제공하지 않습니다.",
                    "points": points,
                } if points else None,
                "demand": {key: value for key, value in demand.items() if value is not None},
                "rentals": rentals.get(row["code"], []),
                "stores": cafes.get(row["code"], []),
            }
        return result

    def nearby_candidates(self, code, listing_id, radius):
        with self.engine.connect() as conn:
            return nearby_candidates(conn, code, listing_id, radius)

    def brand_menu(self, store_id):
        with self.engine.connect() as conn:
            return brand_menu(conn, store_id)
