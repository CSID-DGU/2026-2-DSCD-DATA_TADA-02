import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from enum import IntEnum
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .analysis import AnalysisService
from .config import ROOT, Settings
from .db import Database
from .explanations import ExplanationService
from .schemas import (
    CatalogResponse, ComparisonResponse, ConfigResponse, DetailResponse, ErrorResponse, HealthResponse, ReadyResponse,
    ExplanationRequest, ExplanationResponse, QueryContext, Store,
)
from .telemetry import Metrics, event, request_id_var, span

logging.basicConfig(level=logging.INFO, format="%(message)s")
Quarter = Annotated[str, Query(pattern=r"^20\d{2}Q[1-4]$")]


class Radius(IntEnum):
    small = 100
    medium = 300
    large = 500


def create_app(settings: Settings | None = None, provider=None) -> FastAPI:
    settings = settings or Settings()
    db = Database(settings)
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(app):
        db.initialize(settings.seed_on_start)
        app.state.analysis = AnalysisService(db)
        app.state.explanations = ExplanationService(settings, db, app.state.analysis, provider)
        yield
        await app.state.explanations.close()
        db.dispose()

    app = FastAPI(title="DATA TADA 상권 분석 API", version="0.1.0", lifespan=lifespan,
                  description="카페 상권 최대 5개를 비교합니다. Supabase 모드는 서울시 통계와 발표용 입지 예시를 구분합니다.",
                  responses={422: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                             500: {"model": ErrorResponse}})
    app.state.db = db
    app.state.metrics = metrics

    def error_response(request, code, message, status):
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "request_id": getattr(request.state, "request_id", ""),
        }})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return error_response(request, f"HTTP_{exc.status_code}", str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo arbitrary input values or auth data into responses/logs.
        errors = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return error_response(request, "VALIDATION_ERROR", errors, 422)

    @app.middleware("http")
    async def timing(request: Request, call_next):
        started = time.perf_counter()
        request.state.request_id = str(uuid.uuid4())
        token = request_id_var.set(request.state.request_id)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                event("http.error", error_type=type(exc).__name__)
                response = error_response(request, "INTERNAL_ERROR", "서버 처리 중 오류가 발생했습니다.", 500)
            duration = time.perf_counter() - started
            route = getattr(request.scope.get("route"), "path", "unmatched")
            # SPA paths and unknown URLs must not create unbounded metric labels.
            if route.startswith("/{"):
                route = "frontend"
            metrics.record(request.method, route, response.status_code, duration)
            response.headers["X-Request-ID"] = request.state.request_id
            response.headers["Server-Timing"] = f"app;dur={duration * 1000:.3f}"
            event("http.request", method=request.method, route=route, status=response.status_code,
                  elapsed_ms=round(duration * 1000, 3))
            return response
        finally:
            request_id_var.reset(token)

    def analysis(request: Request):
        return request.app.state.analysis

    def authorize(authorization: Annotated[str | None, Header()] = None):
        if settings.service_access_token:
            expected = f"Bearer {settings.service_access_token}"
            if not authorization or not secrets.compare_digest(authorization, expected):
                raise HTTPException(401, "이 기능에는 서비스 접근 인증이 필요합니다.")

    @app.get("/health/live", response_model=HealthResponse, tags=["operations"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", response_model=ReadyResponse, responses={503: {"model": ErrorResponse}}, tags=["operations"])
    def ready():
        try:
            db.check_ready()
        except Exception:
            raise HTTPException(503, "데이터베이스 준비 상태를 확인할 수 없습니다.")
        return {"status": "ready", "data_mode": settings.data_mode}

    @app.get("/metrics", dependencies=[Depends(authorize)], tags=["operations"], response_class=PlainTextResponse)
    def metric_endpoint():
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.get("/api/v1/config", response_model=ConfigResponse, tags=["catalog"])
    def config():
        return {"data_mode": settings.data_mode, "llm_enabled": settings.llm_enabled,
                "llm_auth_required": bool(settings.service_access_token), "max_candidates": 5,
                "industries": [{"code": "CS100010", "name": "카페"}], "quarters": ["2026Q2"],
                "demo_area_codes": ["3120052", "3120104", "3120100", "3120050", "3120053"]}

    @app.get("/api/v1/areas", response_model=CatalogResponse, tags=["catalog"])
    def areas(service=Depends(analysis), q: str = Query(default="", max_length=80),
              district: str = Query(default="", max_length=40), dong: str = Query(default="", max_length=40),
              offset: int = Query(default=0, ge=0), limit: int = Query(default=2000, ge=1, le=2000)):
        values = [a for a in service.catalog.values()
                  if (not district or a["district"] == district)
                  and (not dong or a["administrative_dong"] == dong)
                  and (not q or q.casefold() in f"{a['name']} {a['district']} {a['administrative_dong']}".casefold())]
        return CatalogResponse(items=values[offset:offset + limit], total=len(values))

    @app.post("/api/v1/comparisons", response_model=ComparisonResponse, tags=["analysis"])
    def comparisons(query: QueryContext, service=Depends(analysis)):
        with span("analysis.compare"):
            return service.compare(query)

    @app.get("/api/v1/areas/{area_code}/analysis", response_model=DetailResponse, tags=["analysis"])
    def detail(area_code: str, quarter: Quarter = "2026Q2", service=Depends(analysis)):
        with span("analysis.detail"):
            return service.detail(area_code, quarter)

    @app.get("/api/v1/areas/{area_code}/nearby-stores", response_model=list[Store], tags=["analysis"])
    def nearby(area_code: str, listing_id: str = Query(min_length=1, max_length=80),
               radius_m: Radius = Radius.medium, quarter: Quarter = "2026Q2", service=Depends(analysis)):
        return service.nearby(area_code, quarter, listing_id, radius_m)

    @app.post("/api/v1/explanations", response_model=ExplanationResponse,
              responses={202: {"model": ExplanationResponse}, 502: {"model": ExplanationResponse}, 401: {"model": ErrorResponse}},
              dependencies=[Depends(authorize)], tags=["explanations"])
    async def explanations(query: ExplanationRequest, request: Request):
        result = await request.app.state.explanations.explain(query)
        status = 202 if result.status == "running" else 502 if result.status == "failed" else 200
        return JSONResponse(result.model_dump(mode="json"), status_code=status,
                            headers={"Retry-After": "2"} if status == 202 else {})

    dist = ROOT / "frontend/dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith(("api/", "health/")) or "." in path:
            raise HTTPException(404, "경로를 찾을 수 없습니다.")
        if not (dist / "index.html").is_file():
            raise HTTPException(503, "프론트엔드를 먼저 빌드하거나 Vite 개발 서버를 사용하세요.")
        return FileResponse(dist / "index.html")

    return app


app = create_app()
