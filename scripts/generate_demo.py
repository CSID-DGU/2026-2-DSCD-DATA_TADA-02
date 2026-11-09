"""Generate visibly labeled synthetic fixtures. Never load production statistics here."""
import calendar
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Fictional presentation examples, arranged around the real area centroids.
PRESENTATION_LOCATIONS = {
    "3120052": (
        [("성수 공방길 1층 코너", 66.1, "1층", 5000, 390, 25),
         ("성수 창고길 테이크아웃형", 29.8, "1층", 3000, 220, 12),
         ("성수 작업실길 2층 채광형", 79.2, "2층", 3500, 260, 18)],
        [("주철빛 커피실", 4800, "솔트크림 라테", 6800, "피칸 휘낭시에", 3600),
         ("잔결 로스터리", 5100, "싱글오리진 필터", 7200, "버터 사블레", 3100),
         ("작업실 오후", 4500, "흑당 오트라테", 6200, "바닐라 파운드", 4900),
         ("모서리 다섯", 4300, "더블 에스프레소", 4600, "레몬 마들렌", 3300),
         ("붉은벽 커피선반", 4900, "자몽 에스프레소 토닉", 6500, "얼그레이 스콘", 4200)],
    ),
    "3120104": (
        [("연남 산책길 작은 1층", 36.4, "1층", 3500, 240, 10),
         ("연남 골목 모퉁이 테라스형", 59.5, "1층", 4500, 320, 17),
         ("연남 주택길 2층 좌석형", 72.7, "2층", 3000, 210, 15)],
        [("연두 산책점", 4700, "바질 레몬 에이드", 6500, "딸기 크럼블", 6200),
         ("구름결 찻장", 4500, "말차 크림라테", 6600, "우유 푸딩", 5300),
         ("연남 종이컵집", 3900, "시나몬 플랫화이트", 5500, "오렌지 쿠키", 3200),
         ("정원 뒤 한 잔", 4900, "청포도 아이스티", 6300, "당근 케이크", 6500),
         ("오후 우편함", 4600, "연유 라테", 5900, "무화과 스콘", 4500)],
    ),
    "3120100": (
        [("망원 생활길 테이크아웃형", 26.4, "1층", 1800, 125, 8),
         ("망원 시장길 1층 좌석형", 49.6, "1층", 2800, 185, 11),
         ("망원 주택길 2층 작업형", 62.8, "2층", 2200, 145, 10)],
        [("모눈잔 커피", 3500, "흑임자 라테", 5300, "인절미 쿠키", 3000),
         ("망원 두칸 찻집", 3800, "보리 밀크티", 5100, "쑥 마들렌", 3200),
         ("골목의 여섯시", 4000, "꿀 오트라테", 5600, "사과 타르트", 5100),
         ("유리문 안쪽", 4200, "콜드브루 라테", 5500, "버터 프레첼", 3900),
         ("작은 원두방", 3700, "고소한 필터커피", 5000, "초코 브라우니", 4100)],
    ),
    "3120050": (
        [("서울숲 산책길 창가형", 56.2, "1층", 4500, 340, 22),
         ("서울숲 오솔길 소형 1층", 33.1, "1층", 3000, 215, 13),
         ("서울숲 나무길 2층 테라스형", 92.6, "2층", 4200, 275, 20)],
        [("그늘자리 커피", 5000, "메이플 오트라테", 6800, "호두 바나나 브레드", 5500),
         ("잎맥 다방", 4600, "유자 얼그레이", 6500, "말차 테린느", 6400),
         ("나무결 브루잉", 5200, "아이스 드립", 6900, "크림 스콘", 4700),
         ("솔바람 찻잔", 4800, "라벤더 밀크티", 6700, "라임 치즈케이크", 6900),
         ("숲길 한 모금", 4400, "토마토 바질 에이드", 6200, "아몬드 비스코티", 3500)],
    ),
    "3120053": (
        [("건대입구 학원길 소형 1층", 36.4, "1층", 2500, 175, 10),
         ("건대입구 먹자골목 코너형", 59.5, "1층", 3800, 285, 16),
         ("건대입구 대학가 2층 좌석형", 82.6, "2층", 2800, 190, 14)],
        [("캠퍼스 빈칸 커피", 3300, "초코 바나나 프라페", 5400, "플레인 크로플", 3900),
         ("페이지사이 카페", 3600, "쿠키크림 라테", 5200, "블루베리 베이글", 4200),
         ("건대 모퉁이 잔", 3800, "복숭아 아이스티", 4500, "시나몬 롤", 4300),
         ("늦은 종소리", 4000, "카라멜 플랫화이트", 5500, "초코칩 쿠키", 3300),
         ("한칸 공부방 커피", 3400, "바닐라 콜드브루", 4900, "햄치즈 토스트", 5100)],
    ),
}


def distribution(total, unit, daily=False):
    age_weights = [.04, .25, .32, .20, .12, .07]
    day_weights = [.11, .12, .12, .13, .15, .20, .17]
    time_weights = [.01, .14, .25, .30, .25, .05]
    # Count the actual calendar occurrences; do not assume every quarter has 13 of each weekday.
    weekdays = [0] * 7
    for month in (4, 5, 6):
        for day in range(1, calendar.monthrange(2026, month)[1] + 1):
            weekdays[date(2026, month, day).weekday()] += 1

    def bins(labels, weights, denominators=None):
        return [{"label": label, "value": round(total * weight / (denominators[i] if denominators else 1), 2),
                 "share_pct": round(weight * 100, 2)} for i, (label, weight) in enumerate(zip(labels, weights))]

    return {"unit": unit, "age_basis": "분기 합계", "weekday_basis": "해당 요일의 실제 일수로 나눈 일평균",
            "time_basis": "분기 합계", "age": bins(["10대", "20대", "30대", "40대", "50대", "60대 이상"], age_weights),
            "weekday": bins(list("월화수목금토일"), day_weights, weekdays),
            "time": bins(["00~06시", "06~11시", "11~14시", "14~17시", "17~21시", "21~24시"], time_weights)}


def main():
    catalog = json.loads((ROOT / "data/catalog/commercial_areas.json").read_text(encoding="utf-8"))
    by_code = {a["code"]: a for a in catalog["items"]}
    codes = ["3120052", "3120104", "3120100", "3120050", "3120053"]
    items = []
    for index, code in enumerate(codes):
        area = by_code[code]
        average = [78000000, 62500000, 54000000, 71000000, 48000000][index]
        stores = [80, 64, 50, 45, 92][index]
        payment = [10000, 12500, 9000, 11000, 8500][index]
        observations = []
        for year in range(2023, 2027):
            for quarter in range(1, 5):
                if year == 2026 and quarter > 2:
                    break
                t = (year - 2023) * 4 + quarter - 1
                factor = .76 + .018 * t + [.01, 0, .035, -.025][quarter - 1]
                count = max(1, round(stores * (.88 + .0092 * t)))
                sales = round(average * factor * count)
                if year == 2026 and quarter == 2:
                    count, sales = stores, average * stores
                observations.append({"quarter": f"{year}Q{quarter}", "total_sales_krw": sales,
                                     "store_count": count, "transaction_count": round(sales / payment)})
        current = observations[-1]
        forecasts = []
        for horizon, multiplier in [(1, 1.04), (2, .98)]:
            sales_per_store = round(average * multiplier)
            future_stores = stores * (1 + .018 * horizon)
            future_sales = sales_per_store * future_stores
            prior = next(r for r in observations if r["quarter"] == f"2025Q{2 + horizon}")
            forecasts.append({"quarter": f"2026Q{2 + horizon}", "average_sales_krw": sales_per_store,
                              "sales_yoy_pct": (future_sales / prior["total_sales_krw"] - 1) * 100,
                              "stores_yoy_pct": (future_stores / prior["store_count"] - 1) * 100,
                              "lower80_krw": round(sales_per_store * (.90 - .025 * horizon)),
                              "upper80_krw": round(sales_per_store * (1.10 + .025 * horizon)),
                              "lower90_krw": round(sales_per_store * (.85 - .035 * horizon)),
                              "upper90_krw": round(sales_per_store * (1.15 + .035 * horizon))})
        rental_examples, cafe_examples = PRESENTATION_LOCATIONS[code]
        rentals, nearby_stores = [], []
        for j, (title, size, floor, deposit, rent, maintenance) in enumerate(rental_examples):
            rentals.append({"id": f"demo-{code}-rent-{j}", "area_code": code, "title": f"[가상] {title}",
                            "latitude": area["latitude"] + (j - 1) * .0007,
                            "longitude": area["longitude"] + j * .0004,
                            "monthly_rent_krw": rent * 10000, "deposit_krw": deposit * 10000, "area_m2": size,
                            "floor": floor, "maintenance_fee_krw": maintenance * 10000,
                            "observed_at": "2026-11-06", "source_url": None, "is_demo": True})
        for j, (name, coffee, signature, signature_price, food, food_price) in enumerate(cafe_examples):
            nearby_stores.append({"id": f"demo-{code}-store-{j}", "name": f"[가상] {name}",
                                  "latitude": area["latitude"] + (j - 2) * .0007,
                                  "longitude": area["longitude"] + (j % 2) * .0011,
                                  "menu": [{"name": "아메리카노", "price_krw": coffee},
                                           {"name": signature, "price_krw": signature_price},
                                           {"name": food, "price_krw": food_price}],
                                  "observed_at": "2026-11-06", "source_url": None, "is_demo": True})
        items.append({"area_code": code, "data_version": "synthetic-demo-20261106-v2",
                      "observations": observations,
                      "forecast": {"model_version": "illustration-only-no-trained-model", "coverage_validated": False,
                                   "interval_method": "개발용 가상 폭, 통계적 보장과 실제 모델 평가 없음", "points": forecasts},
                      "demand": {"transactions": distribution(current["transaction_count"], "건"),
                                 "floating_population": distribution(2400000 + index * 180000, "명 (추정)")},
                      "rentals": rentals, "stores": nearby_stores})
    target = ROOT / "data/demo/snapshots.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"is_demo": True, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(items)} synthetic area fixtures")


if __name__ == "__main__":
    main()
