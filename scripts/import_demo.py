"""Explicit schema creation and demo import, including for a provisioned MySQL DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.db import Base, Database

if __name__ == "__main__":
    settings = Settings()
    database = Database(settings)
    Base.metadata.create_all(database.engine)
    database.import_demo()
    print("Imported catalog and explicitly labeled synthetic fixtures")
    database.engine.dispose()
