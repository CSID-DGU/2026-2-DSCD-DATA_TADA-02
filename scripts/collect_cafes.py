"""Build a Seoul cafe catalog and attach publicly observed menu evidence."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from html import unescape
from io import TextIOWrapper
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from zipfile import ZipFile

from shapely.geometry import Point

from collect_rentals import BOUNDARY, EAST, KST, NORTH, ROOT, SOUTH, WEST, building_address, load_boundaries


OUTPUT = ROOT / "data/cafe_collection"
PORTAL = "https://www.data.go.kr"
STORES_URL = f"{PORTAL}/data/15083033/fileData.do"
GOOD_PRICE_URL = f"{PORTAL}/data/15172358/fileData.do"
TOURISM_URL = "https://data.seoul.go.kr/dataList/OA-21054/S/1/datasetView.do"
USER_AGENT = "DATATADA-CafeCollector/1.0"
PAIK = "https://paikdabang.com"
HOLLYS = "https://www.hollys.co.kr"
VENTI = "https://www.theventi.co.kr/new2022/menu/all.html"
MEGA = "https://www.mega-mgccoffee.com/menu/"
STARBUCKS = "https://www.starbucks.co.kr/menu/"
BRAND_ALIASES = {
    "메가MGC커피": ("메가mgc커피", "메가엠지씨커피", "메가커피", "메가mgc"),
    "스타벅스": ("스타벅스커피", "스타벅스"),
    "더벤티": ("더벤티",),
    "빽다방": ("빽다방",),
    "할리스": ("할리스커피", "할리스"),
}
BRAND_PAGES = [
    ("빽다방", f"{PAIK}/menu/menu_{category}/", "official_menu", "paik-" + category)
    for category in ("coffee", "drink", "dessert", "ccino")
] + [("할리스", f"{HOLLYS}/mall/product.do", "gift_catalog", "hollys-mall")]
MENU_FIELDS = [
    "store_id", "source", "source_record_id", "source_url", "source_date",
    "menu_name", "price_krw", "price_raw", "price_status",
]


def clean(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def identity(value):
    value = re.sub(r"\((?:주|유)\)|주식회사|㈜", "", clean(value))
    return re.sub(r"[^\w]|_", "", value.lower())


def read_url(url, headers=None, data=None):
    return urlopen(Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})}), timeout=90)


def portal_download(dataset, raw):
    url = f"{PORTAL}/data/{dataset}/fileData.do"
    with read_url(url) as response:
        page = response.read().decode("utf-8")
    detail = re.search(rf"fn_fileDataDown\('{dataset}',\s*'(uddi:[^']+)'", page)
    date = re.search(r'<meta name="title" property="og:title" content="[^"]*_(20\d{6})">', page)
    if not detail or not date:
        raise ValueError(f"Dataset {dataset}: download button or reference date missing")
    stamp = date[1]
    output = raw / f"{dataset}-{stamp}.download"
    if not output.exists():
        params = urlencode({
            "publicDataPk": dataset, "publicDataDetailPk": detail[1], "atchFileId": "",
            "fileDetailSn": 1, "publicDataTyCode": "PR0051",
        })
        headers = {"X-Requested-With": "XMLHttpRequest", "Referer": url}
        with read_url(f"{PORTAL}/tcs/dss/selectFileDataDownload.do", headers, params.encode()) as response:
            metadata = json.load(response)
        if metadata.get("status") is not True:
            raise ValueError(f"Dataset {dataset}: official download failed")
        query = urlencode({key: metadata[key] for key in ("atchFileId", "fileDetailSn")})
        partial = output.with_suffix(".partial")
        with read_url(f"{PORTAL}/cmm/cmm/fileDownload.do?{query}", {"Referer": url}) as response:
            with partial.open("wb") as stream:
                while block := response.read(1024 * 1024):
                    stream.write(block)
        partial.replace(output)
    return output, datetime.strptime(stamp, "%Y%m%d").date().isoformat()


def load_stores(path, source_date):
    stores = {}
    with ZipFile(path) as archive:
        member, = (name for name in archive.namelist() if re.search(r"_서울_\d+\.csv$", name))
        with TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row["상권업종소분류코드"] != "I21201":
                    continue
                store_id = row["상가업소번호"]
                if not store_id or store_id in stores:
                    raise ValueError(f"Missing or repeated cafe store ID {store_id!r}")
                stores[store_id] = {
                    "store_id": store_id, "name": clean(row["상호명"]), "branch": clean(row["지점명"]),
                    "district": row["시군구명"], "neighborhood": row["행정동명"],
                    "road_address": row["도로명주소"], "lot_address": row["지번주소"],
                    "floor": row["층정보"], "unit": row["호정보"],
                    "latitude": row["위도"], "longitude": row["경도"],
                    "category_code": row["상권업종소분류코드"], "standard_category_code": row["표준산업분류코드"],
                    "source_date": source_date, "source_url": STORES_URL,
                }
    if not stores:
        raise ValueError("No Seoul shops in the cafe classification")
    return stores


def address_key(address):
    address = clean(address)
    if re.match(r"^[가-힣]+구\s", address):
        address = "서울특별시 " + address
    return building_address(address)


def store_index(stores):
    index = defaultdict(set)
    for store in stores.values():
        names = {identity(store["name"]), identity(store["name"] + store["branch"])} - {""}
        for value in (store["road_address"], store["lot_address"]):
            address = address_key(value)
            if address:
                for name in names:
                    index[(name, address)].add(store["store_id"])
    return index


def match_store(index, name, *addresses):
    candidates = set()
    for address in addresses:
        candidates.update(index.get((identity(name), address_key(address)), ()))
    if len(candidates) == 1:
        return next(iter(candidates))
    return ""


def price_krw(raw):
    if re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)\s*원?", raw):
        number = int(raw.removesuffix("원").strip().replace(",", ""))
        return number if number > 0 else None
    return None


def menu(store_id, source, record, url, date, name, raw):
    raw = clean(raw)
    price = price_krw(raw)
    return dict(
        store_id=store_id, source=source, source_record_id=record, source_url=url, source_date=date,
        menu_name=clean(name), price_krw=price, price_raw=raw,
        price_status="observed" if price else ("non_numeric" if raw else "missing"),
    )


def good_price_menus(path, source_date, index):
    rows, unresolved = [], []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for line, row in enumerate(csv.DictReader(stream), start=2):
            if row["광역"] != "서울특별시":
                continue
            store_id = match_store(index, row["업소명"], row["주소"])
            items = [(clean(row[f"착한가격메뉴 품목{i}"]), row[f"착한가격메뉴 가격{i}"]) for i in range(1, 5)]
            if store_id:
                rows.extend(menu(store_id, "good_price", f"{line}:{i}", GOOD_PRICE_URL, source_date, name, raw)
                            for i, (name, raw) in enumerate(items, start=1) if name)
            elif re.search(r"카페|커피|coffee|cafe", row["업소명"], re.I) and any(
                re.search(r"아메리카노|라[떼테]|에스프레소|커피|콜드브루|카푸치노", name) for name, _ in items
            ):
                unresolved.extend(
                    dict(menu("", "good_price", f"{line}:{i}", GOOD_PRICE_URL, source_date, name, raw),
                         store_name=row["업소명"], address=row["주소"])
                    for i, (name, raw) in enumerate(items, start=1) if name
                )
    return rows, unresolved


def tourism_menus(path, index):
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["언어"] != "ko" or not clean(row["대표메뉴"]):
                continue
            store = match_store(index, row["상호명"], row["신주소"], row["주소"])
            if not store:
                continue
            # A comma between digits is part of a price, not a menu separator.
            for i, item in enumerate(re.split(r"[\n;]+|,(?!\d{3}(?:\D|$))", row["대표메뉴"]), start=1):
                item = clean(item)
                if not item:
                    continue
                priced = re.fullmatch(r"(.+?)\s*[:：-]?\s*\(?\s*(\d{1,3}(?:,\d{3})+|\d{3,})\s*원\)?", item)
                name, raw = priced.groups() if priced else (item, "")
                if name.strip():
                    rows.append(menu(store, "visit_seoul", f"{row['고유번호']}:{i}",
                                     clean(row["콘텐츠URL"]) or TOURISM_URL, "", name, raw))
    return rows


def pilot_menus(directory, index):
    with (directory / "cafe_stores.csv").open(encoding="utf-8-sig", newline="") as stream:
        matches = {row["store_id"]: (match_store(index, row["name"], row["address"]), row["source_url"])
                   for row in csv.DictReader(stream)}
    with (directory / "cafe_menus.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = []
        for row in csv.DictReader(stream):
            store, url = matches.get(row["store_id"], ("", ""))
            if store and url and clean(row["name"]):
                rows.append(menu(store, "seongsu_pilot", f"{row['store_id']}:{row['menu_index']}",
                                 url, row["checked_at"], row["name"], row["price_krw"]))
    return rows


def load_brand_page(raw, fetch, robots, url, cache, data=None, headers=None):
    path = raw / f"{cache}.html"
    if fetch:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in robots:
            rules = RobotFileParser(f"{origin}/robots.txt")
            with read_url(rules.url) as response:
                rules.parse(response.read().decode("utf-8").splitlines())
            robots[origin] = rules
        if not robots[origin].can_fetch(USER_AGENT, url):
            raise ValueError(f"robots.txt disallows {url}")
        with read_url(url, headers, data) as response:
            path.write_bytes(response.read())
    checked_at = datetime.fromtimestamp(path.stat().st_mtime, KST).isoformat()
    return path.read_text(encoding="utf-8"), checked_at


def brand_menu_rows(raw, fetch):
    products = []
    robots = {}

    def load(url, cache, data=None, headers=None):
        return load_brand_page(raw, fetch, robots, url, cache, data, headers)

    def append(brand, channel, items, url, checked_at):
        if not items:
            raise ValueError(f"No menu items in {url}")
        for name, price in items:
            name, price = clean(unescape(name)), clean(unescape(price))
            if name:
                products.append({"brand": brand, "channel": channel, "menu_name": name,
                                 "price_krw": price_krw(price), "price_raw": price,
                                 "source_url": url, "collected_at": checked_at})

    for brand, url, channel, cache in BRAND_PAGES:
        page, stamp = load(url, cache)
        if channel == "gift_catalog":
            items = re.findall(r'<span class="named">([^<]+)</span>\s*</a>\s*<span class="cost">([^<]+)</span>', page)
        else:
            items = [(name, "") for name in re.findall(r'<p class="menu_tit">([^<]+)</p>', page)]
        append(brand, channel, items, url, stamp)

    for mode in range(1, 9):
        url = f"{VENTI}?mode={mode}"
        page, stamp = load(url, f"venti-{mode}")
        items = [(name, "") for name in re.findall(r'<p class="tit">([^<]+)</p>', page)]
        append("더벤티", "official_menu", items, url, stamp)

    page, stamp = load(f"{MEGA}menu.php?page=1", "mega-1")
    last = re.search(r"board_page_last board_page_link' data-page='(\d+)'", page)
    if not last or not 1 <= int(last[1]) <= 100:
        raise ValueError("Unexpected Mega MGC menu pagination")
    for number in range(1, int(last[1]) + 1):
        if number != 1:
            page, stamp = load(f"{MEGA}menu.php?page={number}", f"mega-{number}")
        cards = re.findall(r'<a class="inner_modal_open">(.+?)</a>', page, flags=re.S)
        items = []
        for card in cards:
            heading = re.search(r"<b>(.*?)</b>", card, flags=re.S)
            if heading:
                name = re.sub(r"<[^>]+>", " ", heading[1])
                temperature = re.search(r'cont_gallery_list_label[^"]*">(ICE|HOT)</div>', card)
                if temperature and not re.search(r"\((?:HOT|ICE|ICED)\)", name, re.I):
                    name = f"{name} ({temperature[1]})"
                items.append((name, ""))
        append("메가MGC커피", "official_menu", items, MEGA, stamp)

    for category in ("drink", "food"):
        url = f"{STARBUCKS}{category}_list.do"
        page, _ = load(url, f"starbucks-{category}")
        codes = re.findall(r'else if\(tmp_cate == "product_\w+"\)\s*\{\s*result = "(W\d+)"', page)
        if not codes:
            raise ValueError(f"No Starbucks categories in {url}")
        for code in dict.fromkeys(codes):
            params = urlencode({"CATE_CD": code, "SOLD_OUT": "1"}).encode()
            payload, stamp = load(f"{STARBUCKS}productListAjax.do", f"starbucks-{code}", params,
                                  {"Referer": url, "X-Requested-With": "XMLHttpRequest"})
            items = [(row["product_NM"], "") for row in json.loads(payload)["list"] if row["product_NM"]]
            if items:
                append("스타벅스", "official_menu", items, url, stamp)
    return list({(r["brand"], r["menu_name"], r["price_krw"]): r for r in products}.values())


def match_brands(stores, products):
    brands = {row["brand"] for row in products}
    rows = []
    for store in stores.values():
        name = identity(store["name"])
        for brand in brands:
            if any(name.startswith(alias) and (name == alias or name.endswith("점"))
                   for alias in BRAND_ALIASES[brand]):
                rows.append({"store_id": store["store_id"], "brand": brand})
    return sorted(rows, key=lambda row: (row["store_id"], row["brand"]))


def coverage(stores, menus, brand_links, boundaries):
    codes, names, tree = boundaries
    by_store = defaultdict(list)
    for row in menus:
        by_store[row["store_id"]].append(row)
    with_price = {store for store, items in by_store.items() if any(row["price_krw"] for row in items)}
    with_recent_price = {row["store_id"] for row in menus if row["source"] == "good_price" and row["price_krw"]}
    with_brand = {row["store_id"] for row in brand_links}
    groups = defaultdict(list)
    memberships = []
    for store_id, store in stores.items():
        try:
            lon, lat = float(store["longitude"]), float(store["latitude"])
        except ValueError:
            store["area_status"] = "invalid_coordinates"
            continue
        if not (WEST <= lon <= EAST and SOUTH <= lat <= NORTH):
            store["area_status"] = "invalid_coordinates"
            continue
        areas = sorted(tree.query(Point(lon, lat), predicate="covered_by"))
        store["area_status"] = "linked" if areas else "outside_areas"
        for index in areas:
            groups[index].append(store_id)
            memberships.append({"area_code": codes[index], "store_id": store_id})
    counts = []
    for index, code in enumerate(codes):
        ids = groups[index]
        counts.append(dict(area_code=code, area_name=names[index], stores=len(ids),
                           stores_with_menu=sum(i in by_store for i in ids),
                           stores_with_price=sum(i in with_price for i in ids),
                           stores_with_good_price=sum(i in with_recent_price for i in ids),
                           stores_with_brand_menu=sum(i in with_brand for i in ids)))
    return memberships, counts


def write_csv(directory, filename, fields, rows):
    with (directory / filename).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=OUTPUT / "raw")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--boundary", type=Path, default=BOUNDARY)
    parser.add_argument("--stores", type=Path)
    parser.add_argument("--stores-date")
    parser.add_argument("--good-price", type=Path)
    parser.add_argument("--good-price-date")
    parser.add_argument("--tourism", type=Path)
    parser.add_argument("--pilot", type=Path)
    parser.add_argument("--brands", choices=("cached", "live"))
    args = parser.parse_args()
    for path, date in ((args.stores, args.stores_date), (args.good_price, args.good_price_date)):
        if bool(path) != bool(date):
            parser.error("Supply both the source path and its date, or omit both to download it")
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    checked_at = datetime.now(KST)
    stores_file, store_date = (args.stores, args.stores_date) if args.stores else portal_download("15083033", args.raw_dir)
    good_file, good_date = (args.good_price, args.good_price_date) if args.good_price else portal_download("15172358", args.raw_dir)
    stores = load_stores(stores_file, store_date)
    index = store_index(stores)
    menus, unresolved = good_price_menus(good_file, good_date, index)
    if args.tourism:
        menus.extend(tourism_menus(args.tourism, index))
    if args.pilot:
        menus.extend(pilot_menus(args.pilot, index))
    menus = list({(r["source"], r["store_id"], r["menu_name"], r["price_raw"]): r for r in reversed(menus)}.values())
    menus.sort(key=lambda r: (r["store_id"], r["source"], r["menu_name"], r["price_raw"]))
    products = brand_menu_rows(args.raw_dir, args.brands == "live") if args.brands else []
    brand_links = match_brands(stores, products)
    memberships, counts = coverage(stores, menus, brand_links, load_boundaries(args.boundary))
    counts_by_source = {}
    for source in sorted({row["source"] for row in menus}):
        items = [row for row in menus if row["source"] == source]
        counts_by_source[source] = dict(menus=len(items), priced_menus=sum(bool(row["price_krw"]) for row in items),
                                        stores=len({row["store_id"] for row in items}))
    out = args.output_dir / checked_at.strftime("%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True)
    write_csv(out, "cafe_stores.csv", next(iter(stores.values())).keys(), stores.values())
    write_csv(out, "cafe_menus.csv", MENU_FIELDS, menus)
    write_csv(out, "unmatched_menu_candidates.csv", MENU_FIELDS + ["store_name", "address"], unresolved)
    write_csv(out, "area_memberships.csv", ["area_code", "store_id"], memberships)
    write_csv(out, "area_coverage.csv", counts[0].keys(), counts)
    if args.brands:
        write_csv(out, "brand_menus.csv", products[0].keys(), products)
        write_csv(out, "store_brands.csv", ["store_id", "brand"], brand_links)
    summary = dict(
        collected_at=checked_at.isoformat(), store_source_date=store_date, good_price_source_date=good_date,
        stores=len(stores), store_area_status=dict(Counter(row["area_status"] for row in stores.values())),
        area_memberships=len(memberships), areas=len(counts),
        areas_with_stores=sum(row["stores"] > 0 for row in counts),
        areas_with_menu=sum(row["stores_with_menu"] > 0 for row in counts),
        areas_with_price=sum(row["stores_with_price"] > 0 for row in counts),
        areas_with_brand_menu=sum(row["stores_with_brand_menu"] > 0 for row in counts),
        menus=len(menus), menus_with_price=sum(bool(row["price_krw"]) for row in menus),
        stores_with_menu=len({row["store_id"] for row in menus}),
        stores_with_price=len({row["store_id"] for row in menus if row["price_krw"]}),
        sources=counts_by_source, unmatched_candidate_rows=len(unresolved),
        brand_items=dict(Counter(row["brand"] for row in products)),
        brand_items_with_catalog_prices=dict(Counter(row["brand"] for row in products if row["price_krw"])),
        brand_stores=dict(Counter(row["brand"] for row in brand_links)),
    )
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
