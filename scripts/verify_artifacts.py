"""Check source/spec consistency, local links, copied map data and running service."""
import hashlib
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import Settings
from backend.app.main import create_app


def main():
    spec = json.loads((ROOT / "docs/api/openapi.json").read_text(encoding="utf-8"))
    assert spec == create_app(Settings(llm_enabled=False, _env_file=None)).openapi(), "OpenAPI drift"
    authored = [ROOT / "README.md"]
    authored += list((ROOT / "docs").rglob("*.md"))
    authored += list((ROOT / "backend").rglob("*.py"))
    authored += list((ROOT / "scripts").rglob("*.py"))
    authored += list((ROOT / "frontend/src").rglob("*"))
    for path in authored:
        if path.is_file():
            assert "\u00b7" not in path.read_text(encoding="utf-8"), f"Forbidden punctuation: {path.name}"
    for path in [ROOT / "README.md", *list((ROOT / "docs").rglob("*.md"))]:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if not target.startswith(("http", "#")):
                assert (path.parent / target).exists(), f"Broken local link {path.name}: {target}"
    original = Path("D:/대회/2026 금융 AI Challenge/data/processed_re/re_stage8/commercial_area_points.json")
    copied = ROOT / "data/catalog/commercial_areas.json"
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()
    assert digest == "84b86a4ef8002b6baa60b8cc735912a8dbe8905a04c7fbb8a1076d638a2e5ac7"
    original_matches = hashlib.sha256(original.read_bytes()).hexdigest() == digest if original.is_file() else None
    assert original_matches is not False
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as client:
        for endpoint in ("/health/live", "/health/ready", "/api/v1/config", "/openapi.json", "/"):
            response = client.get(endpoint)
            assert response.status_code == 200, endpoint
            assert response.headers["x-request-id"] and response.headers["server-timing"]
        assert client.get("/openapi.json").json() == spec
        index = client.get("/").text
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', index):
            assert client.get(asset).status_code == 200, asset
        metric_text = client.get("/metrics").text
        assert "process_uptime_seconds" in metric_text and "http_request_duration_seconds_bucket" in metric_text
    result = {"openapi_matches_source_and_server": True, "local_links_valid": True,
              "authored_punctuation_valid": True, "catalog_sha256": digest,
              "catalog_original_matches": original_matches, "health_and_assets": "passed"}
    (ROOT / "tmp/artifact-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
