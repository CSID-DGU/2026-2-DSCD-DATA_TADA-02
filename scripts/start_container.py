import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
uvicorn.run("backend.app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), workers=1)
