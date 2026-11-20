"""Refresh public Sangga114 shop rental listings and join them to Seoul areas."""

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from zipfile import ZipFile

from pyproj import CRS, Transformer
import shapefile
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import transform
from shapely.strtree import STRtree


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "jsw/지수수식검증/데이터/raw/OA-15560_current_seq5.zip"
OCTOBER_BASELINE = ROOT / (
    "jsw/10.25 회의/임대료_크롤링_가능성검증/all_areas_20261025/asking_ads.csv"
)
ORIGIN = "https://www.sangga114.co.kr"
LIST_PATH = "/sales/jumpo/get_kakao_map"
DETAIL_PATH = "/sales/jumpo_detail"
FRONTEND_PATH = "/common/js/map_sales.js"
USER_AGENT = "DATATADA-RentCollector/1.0"
WEST, SOUTH, EAST, NORTH = 126.75, 37.4, 127.2, 37.75
KST = timezone(timedelta(hours=9))
RECENT_DAYS = 90
FIELDS = (
    "listing_id", "source_url", "address", "building_address", "deposit_krw",
    "monthly_rent_krw", "floor_raw", "area_pyeong_raw", "published_at",
    "latitude", "longitude", "checked_at",
)
CHANGE_FIELDS = (
    "address", "deposit_krw", "monthly_rent_krw", "floor_raw", "area_pyeong_raw",
    "latitude", "longitude", "published_at",
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


class PublicSource:
    def __init__(self):
        self.opener = build_opener(NoRedirect())
        self.last_request = 0.0
        self.request_count = 0
        self.rules = RobotFileParser()
        robots = self.read("/robots.txt")
        if not re.search(r"(?im)^user-agent\s*:", robots):
            raise ValueError("Unexpected robots.txt format")
        self.rules.parse(robots.splitlines())
        if LIST_PATH not in self.read(FRONTEND_PATH):
            raise ValueError("Public map frontend no longer references the listing route")

    def read(self, route):
        url = ORIGIN + route
        if route != "/robots.txt" and not self.rules.can_fetch(USER_AGENT, url):
            raise ValueError(f"robots.txt disallows {route.split('?')[0]}")
        request = Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(2):
            time.sleep(max(0, self.last_request + 0.75 - time.monotonic()))
            self.last_request = time.monotonic()
            self.request_count += 1
            try:
                with self.opener.open(request, timeout=20) as response:
                    return response.read().decode("utf-8-sig")
            except HTTPError as error:
                if error.code not in (500, 502, 503, 504) or attempt:
                    raise
            except (URLError, TimeoutError):
                if attempt:
                    raise
            time.sleep(3)


def load_boundaries(path):
    keys, names, geometries = [], [], []
    with ZipFile(path) as archive:
        files = {Path(name).suffix.lower(): name for name in archive.namelist()}
        encoding = archive.read(files[".cpg"]).decode("ascii").strip().upper()
        crs = CRS.from_wkt(archive.read(files[".prj"]).decode("utf-8-sig"))
        convert = Transformer.from_crs(crs, 4326, always_xy=True).transform
        with shapefile.Reader(
            shp=BytesIO(archive.read(files[".shp"])),
            shx=BytesIO(archive.read(files[".shx"])),
            dbf=BytesIO(archive.read(files[".dbf"])),
            encoding="cp949" if encoding in ("949", "CP949", "EUC-KR") else "utf-8",
        ) as reader:
            for feature in reader.iterShapeRecords():
                attrs = feature.record.as_dict()
                geometry = transform(convert, make_valid(shape(feature.shape.__geo_interface__)))
                x1, y1, x2, y2 = geometry.bounds
                if not (WEST <= x1 < x2 <= EAST and SOUTH <= y1 < y2 <= NORTH):
                    raise ValueError(f"Listing search does not cover area {attrs['TRDAR_CD']}")
                keys.append(str(attrs["TRDAR_CD"]))
                names.append(attrs["TRDAR_CD_N"])
                geometries.append(geometry)
    if not keys or len(keys) != len(set(keys)):
        raise ValueError("Empty or duplicate area codes in boundary file")
    return keys, names, STRtree(geometries)


def text(value):
    return " ".join(str(value if value is not None else "").split())


def building_address(address):
    address = re.sub(r"^(서울시|서울)\s+", "서울특별시 ", address)
    match = re.match(
        r"^(서울특별시 \S+구 (?:\S+ )*?\S+(?:동|가|리|로|길|대로) \d+(?:-\d+)?)(?=번지|\s|\(|/|$)",
        address,
    )
    return match[1] if match and not re.search(r"비공개|문의|\*|○|번지미상", address) else None


def won(value):
    value = text(value).replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d{1,4})?", value):
        return None
    return int(Decimal(value) * 10_000)


def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def crawl(source):
    rows, raw_ids = [], set()
    exclusions = defaultdict(int)
    checked_at = datetime.now(KST).isoformat(timespec="seconds")
    page, pages, expected_rows = 1, 1, None
    while page <= max(1, pages):
        params = urlencode({
            "maxLat": NORTH, "maxLng": EAST, "minLat": SOUTH, "minLng": WEST,
            "mapLevel": 6, "pageNo": page, "keyword": "", "a03": "3", "c05": "",
            "c01Min": "", "c01Max": "", "a06Min": "", "a06Max": "", "a02": "",
        })
        payload = json.loads(source.read(f"{LIST_PATH}?{params}"))
        pagination, listings = payload["pagination"], payload["searchList"]
        total, page_size = pagination["totalRecord"], pagination["pageSize"]
        reported_pages = pagination["totalPage"]
        if (
            not isinstance(listings, list) or not isinstance(total, int) or total < 0
            or not isinstance(page_size, int) or page_size < 1
            or pagination["pageNum"] != page or reported_pages != (total + page_size - 1) // page_size
            or reported_pages > 500 or len(listings) != min(page_size, max(0, total - (page - 1) * page_size))
        ):
            raise ValueError(f"Unexpected pagination or row count on page {page}")
        if expected_rows is not None and (reported_pages != pages or total != expected_rows):
            raise ValueError("Listing changes during pagination. Start a new collection.")
        pages, expected_rows = reported_pages, total
        for item in listings:
            listing_id = str(item["num"])
            if not listing_id.isascii() or not listing_id.isdecimal() or listing_id in raw_ids:
                raise ValueError(f"Invalid or repeated listing ID on page {page}")
            raw_ids.add(listing_id)
            if str(item["a03"]) != "3" or str(item["state"]) != "1":
                exclusions["not_listed_as_available_monthly_offer"] += 1
                continue
            address = text(item["address1"])
            key = building_address(address)
            rent = won(item["c04"])
            lat, lon = number(item["lat"]), number(item["lng"])
            if key is None:
                exclusions["no_exact_public_seoul_address"] += 1
            elif not rent:
                exclusions["no_positive_monthly_rent"] += 1
            else:
                if lat is None or lon is None or not (SOUTH <= lat <= NORTH and WEST <= lon <= EAST):
                    lat, lon = None, None
                rows.append({
                    "listing_id": listing_id, "source_url": f"{ORIGIN}{DETAIL_PATH}?num={listing_id}",
                    "address": address, "building_address": key, "deposit_krw": won(item["c03"]),
                    "monthly_rent_krw": rent, "floor_raw": text(item.get("a05")),
                    "area_pyeong_raw": text(item.get("a06")), "published_at": text(item.get("regDate")),
                    "latitude": lat, "longitude": lon, "checked_at": checked_at,
                })
        if page == 1 or page % 20 == 0 or page == pages:
            print(f"Pages {page}/{pages}, offers with exact address and rent {len(rows)}", flush=True)
        page += 1
    if len(raw_ids) != expected_rows:
        raise ValueError("Distinct listing IDs do not match the source total")
    return rows, {"pages": pages, "source_rows": expected_rows, "excluded": dict(exclusions)}


def load_baseline(output):
    previous = sorted(path for path in output.glob("[0-9]*/rentals.csv")
                      if (path.parent / "summary.json").is_file())
    if previous:
        path = previous[-1]
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return path.parent.name, {row["listing_id"]: row for row in csv.DictReader(stream)}
    if not OCTOBER_BASELINE.is_file():
        return None, {}
    with OCTOBER_BASELINE.open(encoding="utf-8-sig", newline="") as stream:
        candidates = (row for row in csv.DictReader(stream) if row["source"] == "sangga114")
        return "2026-10-25 asking_ads.csv", {
            row["source_url"].rsplit("=", 1)[-1]: {
                "monthly_rent_krw": won(row["monthly_rent_manwon"]),
                "deposit_krw": won(row["deposit_manwon"]),
            }
            for row in candidates
        }


def changes(rows, baseline):
    current = {row["listing_id"]: row for row in rows}
    report = []
    for listing_id, row in current.items():
        old = baseline.get(listing_id)
        fields = [key for key in CHANGE_FIELDS if old is not None and key in old
                  and str(old[key] if old[key] is not None else "")
                  != str(row[key] if row[key] is not None else "")]
        if old is None or fields:
            report.append({"listing_id": listing_id, "source_url": row["source_url"],
                           "status": "added" if old is None else "changed",
                           "fields": "|".join(fields)})
    for listing_id in sorted(baseline.keys() - current.keys()):
        report.append({"listing_id": listing_id, "source_url": f"{ORIGIN}{DETAIL_PATH}?num={listing_id}",
                       "status": "not_observed", "fields": ""})
    return report


def publication_date(row):
    try:
        return date.fromisoformat(row["published_at"][:10])
    except ValueError:
        return None


def join_areas(rows, recent_ids, boundaries):
    keys, names, tree = boundaries
    groups = defaultdict(list)
    memberships = []
    for row in rows:
        if row["latitude"] is None:
            continue
        point = Point(row["longitude"], row["latitude"])
        for index in sorted(tree.query(point, predicate="covered_by")):
            groups[index].append(row)
            memberships.append({"area_code": keys[index], "listing_id": row["listing_id"]})
    coverage = []
    for index, code in enumerate(keys):
        listings = groups[index]
        addresses = {row["building_address"] for row in listings}
        recent = [row for row in listings if row["listing_id"] in recent_ids]
        coverage.append({"area_code": code, "area_name": names[index], "listings": len(listings),
                         "distinct_addresses": len(addresses), "shortfall_to_five": max(0, 5 - len(addresses)),
                         "recent_listings": len(recent),
                         "recent_distinct_addresses": len({row["building_address"] for row in recent})})
    return memberships, coverage


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=BOUNDARY)
    parser.add_argument("--output", type=Path, default=ROOT / "data/rental_collection")
    args = parser.parse_args()
    started = datetime.now(KST)
    boundaries = load_boundaries(args.boundary)
    source = PublicSource()
    rows, summary = crawl(source)
    baseline_name, baseline = load_baseline(args.output)
    delta = changes(rows, baseline)
    today = started.date()
    recent_from = today - timedelta(days=RECENT_DAYS - 1)
    dated_rows = {row["listing_id"]: publication_date(row) for row in rows}
    recent_ids = {key for key, published in dated_rows.items() if published and recent_from <= published <= today}
    memberships, coverage = join_areas(rows, recent_ids, boundaries)
    summary.update({
        "source": "sangga114", "source_scope": "Seoul map search, active shop monthly rental filter",
        "started_at": started.isoformat(timespec="seconds"), "requests": source.request_count,
        "listings": len(rows), "with_coordinates": sum(r["latitude"] is not None for r in rows),
        "linked_listings": len({r["listing_id"] for r in memberships}), "memberships": len(memberships),
        "areas": len(coverage), "areas_with_listings": sum(r["listings"] > 0 for r in coverage),
        "areas_with_five_addresses": sum(r["shortfall_to_five"] == 0 for r in coverage),
        "areas_without_listings": sum(r["listings"] == 0 for r in coverage),
        "recent_from": recent_from.isoformat(), "recent_through": today.isoformat(),
        "recent_listings": len(recent_ids),
        "recent_linked_listings": len({r["listing_id"] for r in memberships if r["listing_id"] in recent_ids}),
        "areas_with_recent_listings": sum(r["recent_listings"] > 0 for r in coverage),
        "areas_with_five_recent_addresses": sum(r["recent_distinct_addresses"] >= 5 for r in coverage),
        "listings_without_publication_date": sum(value is None for value in dated_rows.values()),
        "baseline": baseline_name, "baseline_listings": len(baseline),
        "added": sum(r["status"] == "added" for r in delta),
        "changed": sum(r["status"] == "changed" for r in delta),
        "not_observed": sum(r["status"] == "not_observed" for r in delta),
        "boundary_sha256": hashlib.sha256(args.boundary.read_bytes()).hexdigest(),
    })
    run = args.output / started.strftime("%Y%m%d-%H%M%S-%f")
    args.output.mkdir(parents=True, exist_ok=True)
    # Publish the full snapshot together so an interrupted run is never a baseline.
    with TemporaryDirectory(prefix=".pending-", dir=args.output) as temp:
        stage = Path(temp)
        write_csv(stage / "rentals.csv", rows, FIELDS)
        write_csv(stage / "area_memberships.csv", memberships, ("area_code", "listing_id"))
        write_csv(stage / "area_coverage.csv", coverage, tuple(coverage[0]))
        write_csv(stage / "changes.csv", delta, ("listing_id", "source_url", "status", "fields"))
        (stage / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stage.rename(run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Snapshot directory: {run}", flush=True)


if __name__ == "__main__":
    main()
