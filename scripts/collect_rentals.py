"""Refresh public shop rental listings and join them to Seoul areas."""

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from html import unescape
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode
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
ORIGIN = "https://www.sangga114.co.kr"
LIST_PATH = "/sales/jumpo/get_kakao_map"
DETAIL_PATH = "/sales/jumpo_detail"
TRANSFER_PATH = "/jumpo_line/get_kakao_map"
TRANSFER_DETAIL_PATH = "/sangga/sangga_detail"
FRONTEND_PATH = "/common/js/map_sales.js"
USER_AGENT = "DATATADA-RentCollector/1.0"
WEST, SOUTH, EAST, NORTH = 126.75, 37.4, 127.2, 37.75
KST = timezone(timedelta(hours=9))
FIELDS = (
    "listing_id", "source", "source_listing_id", "source_url", "listing_status",
    "address", "building_address", "deposit_krw", "monthly_rent_krw", "floor_raw",
    "area_pyeong_raw", "area_raw", "published_at", "latitude", "longitude",
    "detail_status", "missing_required_fields", "checked_at",
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
        frontend = self.read(FRONTEND_PATH)
        if any(route not in frontend for route in (LIST_PATH, TRANSFER_PATH)):
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
    prefix = re.match(r"^서울(?:특별시|시)?\s+(\S+구)\s+(.+)$", address)
    if not prefix or re.search(r"비공개|문의|\*|○|번지미상", address):
        return None
    district, rest = prefix.groups()
    road = re.search(r"(?:^|\s)([^\s,]+(?:로|길))\s*(지하\s*)?(\d+(?:-\d+)?)(?![\d-])", rest)
    if road:
        return f"서울특별시 {district} {road[1]} {'지하 ' if road[2] else ''}{road[3]}"
    parcel = re.match(
        r"(?P<dong>\S+(?:동|가|리))\s+"
        r"(?:(?:(?P=dong)|[가-힣]*\d+(?:\.\d+)?동)\s*)?"
        r"(?P<lot>\d+-\d+(?=호)|\d+(?:-\d+)?(?=번지|외|[가-힣]+(?:빌딩|건물|상가)|[^\w-]|$))",
        rest,
    )
    if parcel:
        return f"서울특별시 {district} {parcel['dong']} {parcel['lot']}"
    named_parcel = re.match(r"(\S+(?:동|가|리))\s+\S+\s+(\d+(?:-\d+)?)번지", rest)
    if named_parcel:
        return f"서울특별시 {district} {named_parcel[1]} {named_parcel[2]}"
    return None


def in_seoul(value):
    return bool(re.match(r"^서울(?:특별시|시)?(?:\s|/|$)", value))


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


def html_text(raw):
    return text(unescape(re.sub(r"<[^>]+>", " ", raw)))


def table_fields(raw):
    tables = re.findall(r"<th\b[^>]*>(.*?)</th>\s*<td\b[^>]*>(.*?)</td>", raw, re.S | re.I)
    fields = {}
    for key, value in tables:
        fields.setdefault(html_text(key).replace(" ", ""), html_text(value))
    return fields


def get_detail(source, route):
    try:
        return source.read(route)
    except HTTPError as error:
        if error.code in (404, 410):
            return ""
        raise


def apply_public_coordinates(row, latitude, longitude):
    lat, lon = number(latitude), number(longitude)
    if row["building_address"] and lat is not None and lon is not None and (
        SOUTH <= lat <= NORTH and WEST <= lon <= EAST
    ):
        row.update(latitude=lat, longitude=lon)


def quality(row):
    fields = {"address": row["building_address"], "monthly_rent_krw": row["monthly_rent_krw"],
              "deposit_krw": row["deposit_krw"]}
    row["missing_required_fields"] = "|".join(
        field for field, value in fields.items() if value is None or value == ""
    )
    return row


def make_row(source, listing_id, url, status, address, checked_at):
    return dict.fromkeys(FIELDS, "") | {
        "listing_id": listing_id if source == "sangga114" else f"{source}:{listing_id}",
        "source": source, "source_listing_id": listing_id, "source_url": url,
        "listing_status": status, "address": address, "building_address": building_address(address),
        "monthly_rent_krw": None, "deposit_krw": None, "latitude": None, "longitude": None,
        "checked_at": checked_at,
    }


def fetch_pages(source, route, filters):
    raw_ids = set()
    page, pages, expected_rows = 1, 1, None
    while page <= max(1, pages):
        params = urlencode({
            "maxLat": NORTH, "maxLng": EAST, "minLat": SOUTH, "minLng": WEST,
            "mapLevel": 6, "pageNo": page, "keyword": "", **filters,
        })
        payload = json.loads(source.read(f"{route}?{params}"))
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
        if page == 1 or page % 20 == 0 or page == pages:
            print(f"{route}: pages {page}/{pages}, listings received {len(raw_ids)}", flush=True)
        yield listings
        page += 1
    if len(raw_ids) != expected_rows:
        raise ValueError("Distinct listing IDs do not match the source total")


def crawl_general(source):
    rows, exclusions = [], defaultdict(int)
    pending = []
    checked_at = datetime.now(KST).isoformat(timespec="seconds")
    filters = {"a03": "3", "c05": "", "c01Min": "", "c01Max": "", "a06Min": "", "a06Max": "", "a02": ""}
    pages = total = 0
    for items in fetch_pages(source, LIST_PATH, filters):
        pages += 1
        total += len(items)
        for item in items:
            if str(item["a03"]) != "3" or str(item["state"]) != "1":
                exclusions["other_state_or_type"] += 1
                continue
            address = text(item["address1"])
            region = text(item.get("area")).replace("/", " ")
            if not (in_seoul(address) or in_seoul(region)):
                exclusions["outside_or_unknown_seoul"] += 1
                continue
            listing_id = str(item["num"])
            route = f"{DETAIL_PATH}?num={listing_id}"
            row = make_row("sangga114", listing_id, ORIGIN + route, "listed_for_monthly_rent",
                           address if in_seoul(address) else region, checked_at)
            row.update(monthly_rent_krw=won(item["c04"]) or None, deposit_krw=won(item["c03"]),
                       floor_raw=text(item.get("a05")), area_pyeong_raw=text(item.get("a06")),
                       published_at=text(item.get("regDate")), detail_status="list_only")
            apply_public_coordinates(row, item["lat"], item["lng"])
            if quality(row)["missing_required_fields"]:
                pending.append((row, item["lat"], item["lng"], route))
            rows.append(row)
    for count, (row, lat, lon, route) in enumerate(pending, start=1):
        fields = table_fields(get_detail(source, route))
        row["detail_status"] = "public_detail_checked" if fields.get("주소") else "detail_unverified"
        if not row["building_address"] and building_address(fields.get("주소", "")):
            row["address"] = fields["주소"]
            row["building_address"] = building_address(row["address"])
            apply_public_coordinates(row, lat, lon)
        for field, label in (("monthly_rent_krw", "월세(만원)"), ("deposit_krw", "보증금(만원)")):
            if row[field] is None:
                price = won(fields.get(label))
                row[field] = price if field == "deposit_krw" or price else None
        quality(row)
        if count % 25 == 0 or count == len(pending):
            print(f"Sangga114 missing-field details: {count}/{len(pending)}", flush=True)
    return rows, {"pages": pages, "source_rows": total, "detail_requests": len(pending), "excluded": dict(exclusions)}


def explicit_amount(description, label):
    # Transfer pages can have a bundled monthly expense. Read explicitly labelled rent only.
    pattern = rf"(?<![가-힣])(?:{label})\s*[:：]?\s*((?:[\d,.]+\s*(?:억|천만?|만)\s*)+원?|[\d,]+\s*원)"
    amounts = set()
    for raw in re.findall(pattern, description):
        units = {"억": 100_000_000, "천만": 10_000_000, "천": 10_000_000, "만": 10_000}
        parts = re.findall(r"(\d+(?:\.\d+)?)\s*(억|천만?|만)", raw.replace(",", ""))
        if parts:
            amounts.add(sum(int(Decimal(value) * units[unit]) for value, unit in parts))
        else:
            amounts.add(int(re.sub(r"\D", "", raw)))
    return amounts.pop() if len(amounts) == 1 else None


def crawl_transfer(source):
    rows, pending = [], []
    checked_at = datetime.now(KST).isoformat(timespec="seconds")
    pages = total = outside = 0
    for items in fetch_pages(source, TRANSFER_PATH, {}):
        pages += 1
        total += len(items)
        for item in items:
            region = text(item.get("area")).replace("/", " ")
            region = region if in_seoul(region) else text(item.get("address"))
            if not in_seoul(region):
                outside += 1
                continue
            address_open = str(item.get("addressVisibleYn")).upper() in {"Y", "1", "TRUE"} and (
                str(item.get("addressHideYn")).upper() not in {"Y", "1", "TRUE"}
            )
            address = text(item.get("streetAddress") or item.get("numberAddress") or item.get("address"))
            encoded = unquote(text(item.get("encNum")))
            if not re.fullmatch(r"[a-zA-Z0-9+/_=-]+", encoded):
                raise ValueError("Invalid public transfer link identifier")
            route = f"{TRANSFER_DETAIL_PATH}?encNum={quote(encoded, safe='')}"
            row = make_row("sangga114_line", str(item["num"]), ORIGIN + route, "listed_for_business_transfer",
                           address if address_open and building_address(address) else region, checked_at)
            if not address_open:
                row["building_address"] = None
                # The public region is coarse. Do not retain any more specific list address.
                row["address"] = " ".join(region.split()[:3])
            row.update(floor_raw=text(item.get("floor")), area_raw=text(item.get("floorArea")),
                       published_at=text(item.get("publishTime") or item.get("registrationTime")))
            pending.append((row, address_open, route))
            rows.append(row)
    for count, (row, address_open, route) in enumerate(pending, start=1):
        html = get_detail(source, route)
        fields = table_fields(html)
        comment = re.search(r'<div[^>]*class="edit_box"[^>]*>(.*?)<div[^>]*id="detail_map"', html, re.S)
        row["detail_status"] = "public_detail_checked" if fields or comment else "detail_unverified"
        if comment:
            description = html_text(comment[1])
            row["monthly_rent_krw"] = explicit_amount(description, r"월세|월\s*임대료") or None
            row["deposit_krw"] = explicit_amount(description, "보증금")
        if address_open:
            address = fields.get("도로명주소") or fields.get("지번주소") or ""
            if building_address(address):
                row.update(address=address, building_address=building_address(address))
            lat = re.search(r'var lat\s*=\s*"([\d.]+)"', html)
            lon = re.search(r'var lng\s*=\s*"([\d.]+)"', html)
            if lat and lon:
                apply_public_coordinates(row, lat[1], lon[1])
        quality(row)
        if count % 25 == 0 or count == len(pending):
            print(f"Sangga114 transfer details: {count}/{len(pending)}", flush=True)
    return rows, {"pages": pages, "source_rows": total, "detail_requests": len(pending),
                  "excluded": {"outside_or_unknown_seoul": outside}}


def load_market(checkpoint, name):
    summary = json.loads((checkpoint / f"{name}_summary.json").read_text(encoding="utf-8"))
    if not summary["complete"]:
        raise ValueError(f"{name} checkpoint is incomplete")
    collected = {}
    index = checkpoint / f"{name}_index.json"
    current = set(json.loads(index.read_text(encoding="utf-8"))) if index.is_file() else None
    with (checkpoint / f"{name}_records.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            if current is None or item["source_url"] in current:
                collected[item["source_url"]] = item
    rows = []
    status = "listed_on_public_sitemap" if name == "ddak" else "listed_on_public_shop_index"
    for item in collected.values():
        if item["status"] != "seoul_listing":
            continue
        row = make_row(name, item["source_listing_id"], item["source_url"], status,
                       item["address"], item["checked_at"])
        for field in ("deposit_krw", "monthly_rent_krw", "floor_raw", "area_raw"):
            row[field] = item[field]
        row["detail_status"] = "public_detail_checked"
        apply_public_coordinates(row, item.get("latitude"), item.get("longitude"))
        rows.append(quality(row))
    if len(rows) != summary["counts"].get("seoul_listing", 0):
        raise ValueError(f"{name} records differ from checkpoint summary")
    return rows, summary


def read_run(path):
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    with (path / "rentals.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = []
        for row in csv.DictReader(stream):
            for key in ("latitude", "longitude"):
                row[key] = number(row[key])
            for key in ("monthly_rent_krw", "deposit_krw"):
                row[key] = int(row[key]) if row[key] else None
            rows.append(row)
    return rows, summary


def load_baseline(output, sources):
    for path in sorted(output.glob("[0-9]*/summary.json"), reverse=True):
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary.get("sources", {}).keys() != sources.keys():
            continue
        rows, _ = read_run(path.parent)
        return path.parent.name, {row["listing_id"]: row for row in rows}
    return None, {}


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
        report.append({"listing_id": listing_id, "source_url": baseline[listing_id]["source_url"],
                       "status": "not_observed", "fields": ""})
    return report


def join_areas(rows, boundaries):
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
        complete = [row for row in listings if not row["missing_required_fields"]]
        coverage.append({"area_code": code, "area_name": names[index], "listings": len(listings),
                         "distinct_addresses": len(addresses), "shortfall_to_five": max(0, 5 - len(addresses)),
                         "complete_listings": len(complete),
                         "complete_distinct_addresses": len({row["building_address"] for row in complete})})
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
    parser.add_argument("--sangga-snapshot", type=Path, help="Use an existing expanded Sangga114 run")
    parser.add_argument("--market-checkpoint", action="append", nargs=2, default=[], metavar=("NAME", "PATH"),
                        help="Include the completed public checkpoint for ddak or heybd")
    args = parser.parse_args()
    started = datetime.now(KST)
    boundaries = load_boundaries(args.boundary)
    if args.sangga_snapshot:
        rows, previous = read_run(args.sangga_snapshot)
        sources = previous["sources"]
        if set(sources) != {"sangga114", "sangga114_line"}:
            raise ValueError("Expected a standalone expanded Sangga114 snapshot")
        sangga_requests = previous["sangga_requests"]
    else:
        source = PublicSource()
        general, general_stats = crawl_general(source)
        transfer, transfer_stats = crawl_transfer(source)
        rows = general + transfer
        sources = {"sangga114": general_stats, "sangga114_line": transfer_stats}
        sangga_requests = source.request_count
    for name, checkpoint in args.market_checkpoint:
        if name not in {"ddak", "heybd"} or name in sources:
            parser.error(f"Unsupported or repeated market source: {name}")
        market_rows, market_stats = load_market(Path(checkpoint), name)
        rows.extend(market_rows)
        sources[name] = market_stats
    if len(rows) != len({row["listing_id"] for row in rows}) or len(rows) != len({row["source_url"] for row in rows}):
        raise ValueError("Duplicate source listing IDs or links")
    baseline_name, baseline = load_baseline(args.output, sources)
    delta = changes(rows, baseline) if baseline_name else []
    memberships, coverage = join_areas(rows, boundaries)
    complete_rows = [r for r in rows if not r["missing_required_fields"]]
    for name, stats in sources.items():
        group = [row for row in rows if row["source"] == name]
        stats.update({"seoul_rows_saved": len(group),
                      "complete_rows": sum(not row["missing_required_fields"] for row in group),
                      "mapped_rows": sum(row["latitude"] is not None for row in group)})
    summary = {
        "sources": sources, "started_at": started.isoformat(timespec="seconds"),
        "sangga_requests": sangga_requests,
        "listings": len(rows), "with_coordinates": sum(r["latitude"] is not None for r in rows),
        "complete_listings": len(complete_rows),
        "linked_listings": len({r["listing_id"] for r in memberships}), "memberships": len(memberships),
        "areas": len(coverage), "areas_with_listings": sum(r["listings"] > 0 for r in coverage),
        "areas_with_five_addresses": sum(r["shortfall_to_five"] == 0 for r in coverage),
        "areas_without_listings": sum(r["listings"] == 0 for r in coverage),
        "areas_with_complete_listings": sum(r["complete_listings"] > 0 for r in coverage),
        "areas_with_five_complete_addresses": sum(r["complete_distinct_addresses"] >= 5 for r in coverage),
        "baseline": baseline_name, "baseline_listings": len(baseline),
        "added": sum(r["status"] == "added" for r in delta),
        "changed": sum(r["status"] == "changed" for r in delta),
        "not_observed": sum(r["status"] == "not_observed" for r in delta),
        "boundary_sha256": hashlib.sha256(args.boundary.read_bytes()).hexdigest(),
    }
    run = args.output / started.strftime("%Y%m%d-%H%M%S-%f")
    args.output.mkdir(parents=True, exist_ok=True)
    # Publish the full snapshot together so an interrupted run is never a baseline.
    with TemporaryDirectory(prefix=".pending-", dir=args.output) as temp:
        stage = Path(temp)
        write_csv(stage / "rentals.csv", rows, FIELDS)
        write_csv(stage / "complete_rentals.csv", complete_rows, FIELDS)
        write_csv(stage / "area_memberships.csv", memberships, ("area_code", "listing_id"))
        write_csv(stage / "area_coverage.csv", coverage, tuple(coverage[0]))
        write_csv(stage / "changes.csv", delta, ("listing_id", "source_url", "status", "fields"))
        (stage / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stage.rename(run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Snapshot directory: {run}", flush=True)


if __name__ == "__main__":
    main()
