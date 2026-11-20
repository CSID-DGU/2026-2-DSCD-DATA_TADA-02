"""Upload collected rentals and cafes into the project's private Supabase schema."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import time

from dotenv import dotenv_values
import httpx


ROOT = Path(__file__).resolve().parents[1]
SQL = Path(__file__).with_name("sql")
PROJECT = "zpqctvthksrowalefmhi"
ENDPOINT = f"https://api.supabase.com/v1/projects/{PROJECT}/database/query"
CHUNK_BYTES = 360_000
DATASETS = {
    "rentals": ("rental", "rentals.csv"),
    "complete_rentals": ("rental", "complete_rentals.csv"),
    "rental_memberships": ("rental", "area_memberships.csv"),
    "rental_coverage": ("rental", "area_coverage.csv"),
    "rental_changes": ("rental", "changes.csv"),
    "cafes": ("cafe", "cafe_stores.csv"),
    "cafe_menus": ("cafe", "cafe_menus.csv"),
    "cafe_memberships": ("cafe", "area_memberships.csv"),
    "cafe_coverage": ("cafe", "area_coverage.csv"),
    "cafe_brand_menus": ("cafe", "brand_menus.csv"),
    "cafe_store_brands": ("cafe", "store_brands.csv"),
    "cafe_menu_candidates": ("cafe", "unmatched_menu_candidates.csv"),
}


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def literal(value):
    tag = "$location_value$"
    while tag in value:
        tag = tag[:-1] + "_$"
    return tag + value + tag


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"Inconsistent CSV columns in {path}")
    return rows


def digest(rows):
    checksums = []
    for row in rows:
        fields = "".join(f"{len(key)}:{key}{len(value)}:{value}" for key, value in sorted(row.items()))
        checksums.append(hashlib.md5(fields.encode("utf-8"), usedforsecurity=False).hexdigest())
    return hashlib.md5("".join(checksums).encode("ascii"), usedforsecurity=False).hexdigest()


def prepare(args):
    folders = {"rental": args.rental, "cafe": args.cafe}
    files = {key: folders[folder] / file for key, (folder, file) in DATASETS.items()}
    files["rental_public_notices"] = args.notices
    records = {name: csv_rows(file) for name, file in files.items()}
    manifest = {key: json.loads((folder / "summary.json").read_text(encoding="utf-8-sig"))
                for key, folder in folders.items()}
    manifest["inputs"] = {key: {"file": file.name, "rows": len(records[key]), "digest": digest(records[key])}
                          for key, file in files.items()}
    snapshot_id = hashlib.sha256(dump(manifest).encode("utf-8")).hexdigest()

    rentals = records["rentals"]
    cafes = records["cafes"]
    rental_ids = {row["listing_id"] for row in rentals}
    cafe_ids = {row["store_id"] for row in cafes}
    if not rental_ids or len(rental_ids) != len(rentals) or len({r["source_url"] for r in rentals}) != len(rentals):
        raise ValueError("Missing or repeated rental identity")
    if not cafe_ids or len(cafe_ids) != len(cafes):
        raise ValueError("Missing or repeated cafe identity")
    for dataset, field, ids in (
        ("rental_memberships", "listing_id", rental_ids),
        ("cafe_memberships", "store_id", cafe_ids),
        ("cafe_menus", "store_id", cafe_ids),
        ("cafe_store_brands", "store_id", cafe_ids),
    ):
        if {row[field] for row in records[dataset]} - ids:
            raise ValueError(f"Orphan rows in {dataset}")
    for dataset, field, kind in (("rental_memberships", "listing_id", "rental"), ("cafe_memberships", "store_id", "cafe")):
        rows = records[dataset]
        pairs = {(r["area_code"], r[field]) for r in rows}
        areas = {r["area_code"] for r in records[f"{kind}_coverage"]}
        if len(pairs) != len(rows) or {code for code, _ in pairs} - areas:
            raise ValueError(f"Invalid area membership in {dataset}")
    return snapshot_id, records, manifest


def execute(client, query, label, read_only=False):
    for attempt in range(4):
        try:
            response = client.post(ENDPOINT, json={"query": query, "read_only": read_only})
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 3:
                raise RuntimeError(f"{label}: DB request could not be confirmed") from None
        else:
            if response.is_success:
                return response.json() if response.content else []
            if response.status_code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                message = response.text.splitlines()[0][:400] if response.text else ""
                raise RuntimeError(f"{label}: HTTP {response.status_code} {message}")
        time.sleep(2 ** attempt)


def chunks(rows):
    batch, size = [], 2
    for number, row in enumerate(rows, start=1):
        item = dump([number, row])
        length = len(item.encode("utf-8")) + 1
        if batch and size + length > CHUNK_BYTES:
            yield "[" + ",".join(batch) + "]"
            batch, size = [], 2
        batch.append(item)
        size += length
    if batch:
        yield "[" + ",".join(batch) + "]"


def upload_datasets(client, snapshot, records):
    for dataset, rows in records.items():
        values = chunks(rows)

        def insert(item):
            index, batch = item
            query = f"""
            insert into data_tada.location_collection_rows (snapshot_id, dataset, row_number, payload)
            select {snapshot}, {literal(dataset)}, (r->>0)::integer, r->1
            from jsonb_array_elements({literal(batch)}::jsonb) as elements(r)
            on conflict do nothing
            """
            execute(client, query, f"{dataset} batch {index}")

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(insert, enumerate(values, start=1)))
        print(f"{dataset}: {len(rows)} rows staged", flush=True)


def verify_original(client, snapshot, manifest):
    actual = execute(client, f"""
        select dataset, count(*) as rows,
            md5(string_agg(md5((select string_agg(
                length(key)::text || ':' || key || length(value)::text || ':' || value,
                '' order by key collate "C") from jsonb_each_text(payload)
            )), '' order by row_number)) as digest
        from data_tada.location_collection_rows
        where snapshot_id = {snapshot}
        group by dataset
    """, "staged row digests", read_only=True)
    expected = {name: (info["rows"], info["digest"]) for name, info in manifest["inputs"].items() if info["rows"]}
    received = {row["dataset"]: (int(row["rows"]), row["digest"]) for row in actual}
    if received != expected:
        differences = sorted(name for name in (expected.keys() | received.keys()) if expected.get(name) != received.get(name))
        raise ValueError(f"Source row digest or count mismatch: {differences}")


def verify_published(client, snapshot, records):
    summary, = execute(client, f"""
        with source as (
            select dataset, payload from data_tada.location_collection_rows where snapshot_id = {snapshot}
        )
        select (select uploaded_at from data_tada.location_collection_runs where snapshot_id = {snapshot}),
            (select count(*) from source s join data_tada.rental_listings r
                on r.listing_id = s.payload->>'listing_id' and r.collection_payload = s.payload
                where s.dataset = 'rentals') as rentals,
            (select count(*) from source s join data_tada.cafe_stores c
                on c.store_id = s.payload->>'store_id' and c.collection_payload = s.payload
                where s.dataset = 'cafes') as cafes,
            (select count(*) from source s join data_tada.cafe_menus m
                on m.store_id = s.payload->>'store_id' and m.collection_payload = s.payload
                where s.dataset = 'cafe_menus') as cafe_menus,
            (select count(*) from source s join data_tada.rental_area_memberships r
                on r.area_code = s.payload->>'area_code' and r.listing_id = s.payload->>'listing_id'
                where s.dataset = 'rental_memberships') as rental_memberships,
            (select count(*) from source s join data_tada.cafe_area_memberships c
                on c.area_code = s.payload->>'area_code' and c.store_id = s.payload->>'store_id'
                where s.dataset = 'cafe_memberships') as cafe_memberships,
            (select count(*) from source s left join data_tada.areas a on a.area_code = s.payload->>'area_code'
                where s.dataset = 'rental_memberships' and a.area_code is null) as rental_unregistered_area_links,
            (select count(*) from source s left join data_tada.areas a on a.area_code = s.payload->>'area_code'
                where s.dataset = 'cafe_memberships' and a.area_code is null) as cafe_unregistered_area_links,
            (select count(*) from data_tada_demo.location_examples where is_demo) as demo_areas
    """, "published row verification", read_only=True)
    if not summary["uploaded_at"]:
        raise ValueError("Run did not commit")
    for name in ("rentals", "cafes", "cafe_menus"):
        if int(summary[name]) != len(records[name]):
            raise ValueError(f"Published row count mismatch: {name}")
    for source in ("rental", "cafe"):
        name = f"{source}_memberships"
        if int(summary[name]) + int(summary[f"{source}_unregistered_area_links"]) != len(records[name]):
            raise ValueError(f"Published row count mismatch: {name}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("rental", "cafe", "notices"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    snapshot_id, records, manifest = prepare(args)
    snapshot = literal(snapshot_id)
    report = {"snapshot_id": snapshot_id, "source_rows": {k: len(v) for k, v in records.items()}}
    print(dump(report), flush=True)
    if not args.apply:
        return

    token = os.environ.get("SUPABASE_ACCESS_TOKEN") or dotenv_values(ROOT / ".env").get("SUPABASE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN is not configured")
    with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=90) as client:
        execute(client, (SQL / "location_collection_schema.sql").read_text(encoding="utf-8"), "location collection schema")
        execute(client, f"""
            insert into data_tada.location_collection_runs (snapshot_id, manifest)
            values ({snapshot}, {literal(dump(manifest))}::jsonb)
            on conflict do nothing
        """, "register collection snapshot")
        run, = execute(client, f"""
            select uploaded_at from data_tada.location_collection_runs where snapshot_id = {snapshot}
        """, "collection snapshot status", read_only=True)
        if not run["uploaded_at"]:
            upload_datasets(client, snapshot, records)
        verify_original(client, snapshot, manifest)
        if not run["uploaded_at"]:
            publish = (SQL / "location_collection_publish.sql").read_text(encoding="utf-8")
            publish = publish.replace("__SNAPSHOT_ID__", snapshot).replace(
                "__CAFE_CHECKED_AT__", literal(manifest["cafe"]["collected_at"])
            )
            execute(client, publish, "publish location collection")
        report["database"] = verify_published(client, snapshot, records)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(dump(report), flush=True)


if __name__ == "__main__":
    main()
