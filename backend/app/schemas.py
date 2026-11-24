from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_CANDIDATES = 5


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Section(StrEnum):
    profitability = "profitability"
    competition = "competition"
    demand = "demand"
    rent = "rent"
    location = "location"


class QueryContext(StrictModel):
    area_codes: list[str] = Field(min_length=1, max_length=MAX_CANDIDATES)
    industry_code: Literal["CS100010"] = "CS100010"
    quarter: str = Field(default="2026Q2", pattern=r"^20\d{2}Q[1-4]$")

    @model_validator(mode="after")
    def unique_areas(self):
        if len(set(self.area_codes)) != len(self.area_codes):
            raise ValueError("상권 코드는 중복될 수 없습니다.")
        return self


class ExplanationRequest(QueryContext):
    scope: Literal["comparison", "detail"]
    section: Section
    demand_metric: Literal["transactions", "floating_population"] = "transactions"
    location_view: Literal["rentals", "stores"] = "rentals"
    listing_id: str | None = Field(default=None, max_length=80)
    radius_m: Literal[100, 300, 500] = 300
    rental_area_m2: float = Field(default=66.1157, gt=0, le=3305.785)
    rental_floor: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def valid_scope(self):
        if self.scope == "detail" and len(self.area_codes) != 1:
            raise ValueError("상세 해설에는 상권 하나만 지정합니다.")
        if self.scope == "comparison" and self.section == Section.location:
            raise ValueError("비교 화면은 rent를 사용합니다.")
        if self.scope == "detail" and self.section == Section.rent:
            raise ValueError("상세 화면은 location을 사용합니다.")
        if self.listing_id and not (self.scope == "detail" and self.section == Section.location):
            raise ValueError("기준 매물은 입지 상세 해설에서만 사용합니다.")
        if self.section == Section.location and self.location_view == "stores" and not self.listing_id:
            raise ValueError("주변 점포 해설은 기준 매물을 선택해야 합니다.")
        return self


class Area(BaseModel):
    code: str
    name: str
    category: str
    district: str
    administrative_dong: str
    latitude: float
    longitude: float
    area_m2: float
    radius_m: float


class Metadata(BaseModel):
    data_mode: Literal["demo", "supabase"] = "demo"
    data_version: str
    metric_version: str = "metrics-v1"
    industry_code: str = "CS100010"
    quarter: str
    warning: str = "분석 수치, 예측, 매물과 메뉴는 개발용 가상 자료입니다. 실제 상권 위치 목록과 구분합니다."


class CurrentMetrics(BaseModel):
    total_sales_krw: float | None
    store_count: int
    transaction_count: int | None
    average_sales_krw: float | None
    transactions_per_store: float | None
    average_payment_krw: float | None
    sales_yoy_pct: float | None
    stores_yoy_pct: float | None
    average_sales_yoy_pct: float | None
    transactions_yoy_pct: float | None = None
    competition_type: str


class Rental(BaseModel):
    id: str
    area_code: str
    title: str
    latitude: float
    longitude: float
    monthly_rent_krw: int | None
    deposit_krw: int | None
    area_m2: float | None
    floor: str | None
    maintenance_fee_krw: int | None
    observed_at: str
    source_url: str | None = None
    source_name: str | None = None
    is_transfer: bool = False
    is_demo: bool = True


class MenuItem(BaseModel):
    name: str
    price_krw: int | None
    source_url: str | None = None
    source_date: str | None = None


class BrandMenuItem(MenuItem):
    channel: Literal["official_menu", "gift_catalog"]


class Store(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    menu: list[MenuItem]
    observed_at: str
    source_url: str | None = None
    address: str | None = None
    brand: str | None = None
    distance_m: float | None = None
    is_demo: bool = True


class ComparisonItem(BaseModel):
    area: Area
    metrics: CurrentMetrics | None
    rentals: list[Rental]
    missing_reason: str | None = None
    observations: list["Observation"] = Field(default_factory=list)


class ComparisonResponse(BaseModel):
    meta: Metadata
    items: list[ComparisonItem]


class Observation(BaseModel):
    quarter: str
    total_sales_krw: float | None
    store_count: int
    transaction_count: int | None
    average_sales_krw: float | None
    sales_yoy_pct: float | None
    stores_yoy_pct: float | None


class ForecastPoint(BaseModel):
    quarter: str
    total_sales_krw: float | None = None
    average_sales_krw: float | None
    sales_yoy_pct: float | None
    stores_yoy_pct: float | None
    lower80_krw: float | None = None
    upper80_krw: float | None = None
    lower90_krw: float | None = None
    upper90_krw: float | None = None


class Forecast(BaseModel):
    model_version: str
    interval_method: str
    coverage_validated: bool = False
    points: list[ForecastPoint]


class DistributionBin(BaseModel):
    label: str
    value: float | None
    share_pct: float | None


class Distribution(BaseModel):
    unit: str
    age_basis: str
    weekday_basis: str
    time_basis: str
    age: list[DistributionBin]
    weekday: list[DistributionBin]
    time: list[DistributionBin]


class DetailResponse(BaseModel):
    meta: Metadata
    area: Area
    current: CurrentMetrics | None
    observations: list[Observation]
    forecast: Forecast | None
    demand: dict[str, Distribution]
    rentals: list[Rental]
    stores: list[Store]
    boundary: dict | None = None
    missing_reason: str | None = None


class CatalogResponse(BaseModel):
    items: list[Area]
    total: int
    crs: str = "EPSG:4326"
    marker_meaning: str = "원은 탐색용 면적 환산 표시이며 실제 상권 경계가 아닙니다."


class Industry(BaseModel):
    code: str
    name: str


class ConfigResponse(BaseModel):
    data_mode: str
    llm_enabled: bool
    llm_auth_required: bool
    max_candidates: int
    industries: list[Industry]
    quarters: list[str]
    demo_area_codes: list[str]


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(HealthResponse):
    data_mode: str


class ExplanationBlock(StrictModel):
    title: str
    text: str
    evidence_ids: list[str]


class ExplanationContent(StrictModel):
    summary: str
    blocks: list[ExplanationBlock]
    caveats: list[str]


class ExplanationResponse(BaseModel):
    status: Literal["completed", "running", "disabled", "unavailable", "failed"]
    cache_key: str
    cache_hit: bool = False
    content: ExplanationContent | None = None
    message: str | None = None
    retry_after_seconds: int | None = None
    prompt_version: str
    model: str | None = None
    evidence: dict = Field(default_factory=dict)


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody
