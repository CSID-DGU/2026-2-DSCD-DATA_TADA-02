"""Import audited detailed commentary into the configured application database."""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.exc import IntegrityError

from backend.app.config import Settings
from backend.app.db import Database, ExplanationRow
from backend.app.detail_explanations import PERMANENT_EXPIRY, SECTIONS, detail_evidence, detail_key, load_detail_prompt
from backend.app.explanations import validate_content
from backend.app.schemas import ExplanationContent


def read_jsonl(path):
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def verified_entries(directory: Path) -> tuple[dict[str, dict], int]:
    inputs = {row["area_code"]: row for row in read_jsonl(directory / "inputs.jsonl")}
    prompts = {tab: load_detail_prompt(tab) for tab in SECTIONS}
    insufficient_data = 0
    entries = {}
    for row in read_jsonl(directory / "results.jsonl"):
        tab = row["tab"]
        source = inputs[row["area_code"]]
        if (row["section"] != SECTIONS[tab] or
                any(row[field] != source[field] for field in ("quarter", "industry_code", "data_version", "prompt_version"))):
            raise ValueError("Result identity differs from input")
        if row["status"] == "insufficient_data":
            insufficient_data += 1
            continue
        if row["status"] != "verified":
            raise ValueError("Expected a verified result")
        evidence = detail_evidence(area_code=row["area_code"], quarter=row["quarter"],
                                   industry_code=row["industry_code"], data_mode=source["data_mode"],
                                   data_version=row["data_version"], tab=tab, source=source["facts"])
        content = ExplanationContent.model_validate(row["content"])
        aliases = {f"{tab}_distribution": "distribution",
                   f"{'floating_population' if tab == 'transactions' else 'transactions'}_distribution": "comparison_distribution"}
        for block in content.blocks:
            block.evidence_ids = [aliases.get(item, item) for item in block.evidence_ids]
        validate_content(content, evidence)
        key = detail_key(evidence, prompts[tab], row["model"])
        if key in entries:
            raise ValueError("Duplicate detail result")
        entries[key] = content.model_dump()
    return entries, insufficient_data


def import_verified(db, entries: dict[str, dict]) -> dict[str, int]:
    report = {"inserted": 0, "existing": 0}
    ExplanationRow.__table__.create(db.engine, checkfirst=True)
    with db.session.begin() as session:
        for key, payload in entries.items():
            if session.get(ExplanationRow, key) is not None:
                report["existing"] += 1
                continue
            try:
                with session.begin_nested():
                    session.add(ExplanationRow(key=key, status="completed", owner=str(uuid.uuid4()),
                                               lease_until=0, expires_at=PERMANENT_EXPIRY, payload=payload))
                report["inserted"] += 1
            except IntegrityError:
                if session.get(ExplanationRow, key) is None:
                    raise
                report["existing"] += 1
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    entries, insufficient_data = verified_entries(args.directory)
    db = Database(Settings())
    try:
        report = import_verified(db, entries)
    finally:
        db.dispose()
    print(json.dumps({**report, "insufficient_data": insufficient_data}))
