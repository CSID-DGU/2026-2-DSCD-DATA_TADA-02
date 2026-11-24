import json
from pathlib import Path

from sqlalchemy import JSON, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import ROOT, Settings
from .supabase_data import SupabaseData


class Base(DeclarativeBase):
    pass


class AreaRow(Base):
    __tablename__ = "areas"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class SnapshotRow(Base):
    __tablename__ = "analysis_snapshots"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ExplanationRow(Base):
    __tablename__ = "explanations"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    owner: Mapped[str] = mapped_column(String(36))
    lease_until: Mapped[float]
    expires_at: Mapped[float]
    payload: Mapped[dict] = mapped_column(JSON)


class Database:
    def __init__(self, settings: Settings):
        self.remote = SupabaseData(settings) if settings.data_mode == "supabase" else None
        url = settings.database_url
        if url.startswith("sqlite:///") and not url.endswith(":memory:"):
            Path(url.removeprefix("sqlite:///")).resolve().parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url, pool_pre_ping=True,
            **({"connect_args": {"check_same_thread": False, "timeout": 10}} if url.startswith("sqlite") else {}),
        )
        self.session = sessionmaker(self.engine, expire_on_commit=False)
        self.comparison_session = self.session
        self.detail_session = self.session
        self.llm_enabled = settings.llm_enabled
        if self.remote:
            detail_engine = self.remote.engine.execution_options(schema_translate_map={None: "analysis_cache"})
            self.detail_session = sessionmaker(detail_engine, expire_on_commit=False)
            if settings.app_env == "production" and url.startswith("sqlite"):
                self.comparison_session = self.detail_session

    def initialize(self, seed: bool):
        # Production schema creation/import is an explicit operator command.
        if seed:
            Base.metadata.create_all(self.engine)
            if self.remote is None:
                self.import_demo()

    @property
    def data_mode(self):
        return "supabase" if self.remote else "demo"

    def check_ready(self):
        if self.remote:
            self.remote.check_ready()
        else:
            with self.session() as session:
                session.scalars(select(AreaRow.code).limit(1)).one()
        if self.llm_enabled:
            for sessions in dict.fromkeys((self.comparison_session, self.detail_session)):
                with sessions() as session:
                    session.scalars(select(ExplanationRow.key).limit(1)).first()

    def dispose(self):
        self.engine.dispose()
        if self.remote:
            self.remote.engine.dispose()

    def import_demo(self):
        catalog = json.loads((ROOT / "data/catalog/commercial_areas.json").read_text(encoding="utf-8"))
        demo = json.loads((ROOT / "data/demo/snapshots.json").read_text(encoding="utf-8"))
        with self.session.begin() as session:
            existing_areas = set(session.scalars(select(AreaRow.code)))
            for area in catalog["items"]:
                if area["code"] not in existing_areas:
                    session.add(AreaRow(code=area["code"], payload=area))
            for payload in demo["items"]:
                key = f"demo:{payload['area_code']}:CS100010:2026Q2"
                row = session.get(SnapshotRow, key)
                if row is None:
                    session.add(SnapshotRow(key=key, payload=payload))
                elif row.payload.get("data_version") != payload["data_version"]:
                    row.payload = payload

    def areas(self) -> list[dict]:
        if self.remote:
            return self.remote.areas()
        with self.session() as session:
            return [r.payload for r in session.scalars(select(AreaRow).order_by(AreaRow.code))]

    def snapshots(self, codes: list[str], quarter: str) -> dict:
        if self.remote:
            return self.remote.snapshots(codes, quarter)
        keys = [f"demo:{code}:CS100010:{quarter}" for code in codes]
        with self.session() as session:
            rows = session.scalars(select(SnapshotRow).where(SnapshotRow.key.in_(keys)))
            return {row.payload["area_code"]: row.payload for row in rows}

    def snapshot(self, code: str, quarter: str) -> dict | None:
        if self.remote:
            return self.remote.snapshots([code], quarter, include_stores=True).get(code)
        return self.snapshots([code], quarter).get(code)
