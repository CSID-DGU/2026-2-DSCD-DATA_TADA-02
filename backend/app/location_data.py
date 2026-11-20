"""Read locations and menu evidence from already-collected Supabase tables."""

from collections import defaultdict
from math import cos, radians
import re
from urllib.parse import urlsplit

from sqlalchemy import text


RENTAL_FIELDS = """
    select r.listing_id as id, m.area_code, r.address, r.latitude, r.longitude,
           r.monthly_rent_krw, r.deposit_krw, r.floor_raw, r.source_url, r.checked_at,
           r.collection_payload->>'source' as source,
           r.collection_payload->>'listing_status' as listing_status,
           r.collection_payload->>'area_pyeong_raw' as area_pyeong_raw,
           r.collection_payload->>'area_raw' as area_raw
    from data_tada.rental_area_memberships m
    join data_tada.rental_listings r using (listing_id)
    where r.latitude is not null and r.longitude is not null
"""
RENTALS = text(RENTAL_FIELDS + """
    and m.area_code = any(cast(:codes as text[]))
    order by m.area_code, (r.deposit_krw is not null and r.monthly_rent_krw > 0
        and r.address_precision = 'building') desc nulls last, r.checked_at desc, r.listing_id
""")
RENTAL_POINT = text(RENTAL_FIELDS + " and m.area_code = :code and r.listing_id = :listing")

CAFE_FIELDS = """
    select c.store_id as id, c.name, c.collection_payload->>'branch' as branch, c.address,
           c.latitude, c.longitude, c.source_url,
           coalesce(c.collection_payload->>'source_date', c.collection_as_of::date::text) as observed_at,
           b.brand, coalesce(menu.items, '[]'::jsonb) as menu
    from data_tada.cafe_stores c
    left join data_tada.service_cafe_store_brands b on b.store_id = c.store_id
    left join lateral (
        select jsonb_agg(jsonb_build_object(
            'name', m.name, 'price_krw', m.price_krw,
            'source_url', m.collection_payload->>'source_url',
            'source_date', nullif(m.collection_payload->>'source_date', '')
        ) order by (m.price_krw is not null) desc, m.menu_index) as items
        from data_tada.cafe_menus m
        where m.store_id = c.store_id
    ) menu on true
    where c.latitude is not null and c.longitude is not null
"""
AREA_CAFES = text(CAFE_FIELDS + """
    and exists (select 1 from data_tada.cafe_area_memberships m where m.area_code = :code and m.store_id = c.store_id)
    order by (menu.items is not null) desc, c.name, c.store_id
""")
NEARBY_CAFES = text(CAFE_FIELDS + """
    and c.latitude between :south and :north and c.longitude between :west and :east
""")
BRAND_MENU = text("""
    select m.name, m.channel, m.price_krw, m.source_url, m.source_date
    from data_tada.service_cafe_store_brands b
    join data_tada.service_cafe_brand_menus m using (brand)
    where b.store_id = :store_id
    order by m.channel, m.name, m.price_krw nulls last
""")
SOURCES = {"sangga114": "상가114", "sangga114_line": "상가114 권리금", "ddak": "딱자리", "heybd": "헤이빌딩"}


def public_url(value):
    parsed = urlsplit(value or "")
    return value if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username else None


def floor_label(value):
    floor = (value or "").split("/", 1)[0].strip()
    numbered = re.fullmatch(r"(B|지하|[-+])?\s*(\d+)\s*(?:층)?", floor, flags=re.I)
    if numbered:
        prefix = "지하 " if (numbered[1] or "").upper() in ("B", "지하", "-") else ""
        return f"{prefix}{int(numbered[2])}층"
    return floor or None


def area_m2(area, pyeong):
    metric = re.fullmatch(r"([\d,.]+)\s*㎡\s*(?:\([^)]*\))?", area or "")
    number = (metric[1] if metric else (pyeong or "")).replace(",", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", number):
        value = float(number)
        return round(value if metric else value * 400 / 121, 2) if value > 0 else None
    return None


def store_payload(row):
    store = dict(row)
    branch = store.pop("branch")
    if branch and not store["name"].replace(" ", "").endswith(branch.replace(" ", "")):
        store["name"] = f"{store['name']} {branch}"
    store["source_url"] = public_url(store["source_url"])
    for item in store["menu"]:
        item["source_url"] = public_url(item["source_url"])
    return {**store, "is_demo": False}


def rentals_by_area(conn, codes):
    grouped = defaultdict(list)
    for row in conn.execute(RENTALS, {"codes": codes}).mappings():
        source = SOURCES.get(row["source"])
        grouped[row["area_code"]].append({
            "id": row["id"], "area_code": row["area_code"], "title": row["address"] or "주소 미공개 매물",
            "latitude": row["latitude"], "longitude": row["longitude"],
            "monthly_rent_krw": row["monthly_rent_krw"], "deposit_krw": row["deposit_krw"],
            "area_m2": area_m2(row["area_raw"], row["area_pyeong_raw"]),
            "floor": floor_label(row["floor_raw"]), "maintenance_fee_krw": None,
            "observed_at": row["checked_at"].isoformat(), "source_url": public_url(row["source_url"]),
            "source_name": source, "is_transfer": row["listing_status"] == "listed_for_business_transfer",
            "is_demo": False,
        })
    return grouped


def area_stores(conn, code):
    return [store_payload(row) for row in conn.execute(AREA_CAFES, {"code": code}).mappings()]


def nearby_candidates(conn, code, listing_id, radius):
    rental = conn.execute(RENTAL_POINT, {"code": code, "listing": listing_id}).mappings().first()
    if rental is None:
        return None
    lat, lon = rental["latitude"], rental["longitude"]
    # Slightly expand the query box; the service then filters by great-circle distance.
    lat_pad = radius / 110000
    lon_pad = lat_pad / cos(radians(abs(lat) + lat_pad))
    params = {"south": lat - lat_pad, "north": lat + lat_pad, "west": lon - lon_pad, "east": lon + lon_pad}
    return lat, lon, [store_payload(row) for row in conn.execute(NEARBY_CAFES, params).mappings()]


def brand_menu(conn, store_id):
    return [{**row, "source_url": public_url(row["source_url"])}
            for row in conn.execute(BRAND_MENU, {"store_id": store_id}).mappings()]
