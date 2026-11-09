import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import Settings
from backend.app.main import create_app

target = ROOT / "docs/api/openapi.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(create_app(Settings(_env_file=None)).openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Exported {target.name}")
