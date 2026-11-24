"""Build the data contract for the four on-demand comparison prompts."""

from pathlib import Path
from statistics import mean, quantiles

from .analysis import AnalysisService
from .schemas import ComparisonItem, ExplanationRequest, Observation, Rental, Section
from .supabase_data import quarter_start

PROMPTS = Path(__file__).with_name("prompts")
COMPARISON_FILES = {
    Section.competition: "overview.md",
    Section.profitability: "sales.md",
    Section.demand: "demand.md",
    Section.rent: "rent.md",
}
COMPARISON_VERSION = "comparison-markdown-v1"
RENT_MIN_IQR_SAMPLE = 5


def load_comparison_prompt(section: Section) -> str:
    files = [PROMPTS / "common.md", PROMPTS / "comparison" / "common.md",
             PROMPTS / "comparison" / COMPARISON_FILES[section]]
    return "\n\n".join(path.read_text(encoding="utf-8").strip() for path in files)


def raw_metrics(row: Observation | None, fields: tuple[str, ...]) -> dict | None:
    if row is None:
        return None
    return {field: getattr(row, field) for field in fields}


def rent_summary(listings: list[Rental], field: str) -> dict:
    known = [getattr(listing, field) for listing in listings if getattr(listing, field) is not None]
    valid = sorted(amount for amount in known if amount >= 0 and (field == "deposit_krw" or amount > 0))
    used = valid
    if len(valid) >= RENT_MIN_IQR_SAMPLE:
        lower, _, upper = quantiles(valid, n=4, method="inclusive")
        spread = upper - lower
        if spread > 0:
            used = [amount for amount in valid if lower - 1.5 * spread <= amount <= upper + 1.5 * spread]
    excluded = len(valid) - len(used)
    return {
        "mean_krw": mean(used) if used else None,
        "method": "iqr_filtered_mean" if excluded else "arithmetic_mean",
        "filter_status": "applied" if excluded else "not_applied",
        "available_count": len(valid),
        "used_count": len(used),
        "missing_count": len(listings) - len(known),
        "invalid_count": len(known) - len(valid),
        "iqr_excluded_count": excluded,
        "small_sample": 0 < len(used) < RENT_MIN_IQR_SAMPLE,
    }


def rent_input(item: ComparisonItem, req: ExplanationRequest, mode: str) -> tuple[dict, dict]:
    listings = [listing for listing in item.rentals if not req.rental_floor or listing.floor == req.rental_floor]
    dates = sorted(listing.observed_at[:10] for listing in listings if listing.observed_at)
    rollup = {field: rent_summary(listings, field) for field in ("monthly_rent_krw", "deposit_krw")}
    rental_data = {
        "listing_count": len(listings),
        "checked_at_range": {"start": dates[0], "end": dates[-1]} if dates else None,
        "rent_summary": rollup,
    }
    with_area = [r for r in listings if r.area_m2 is not None and r.area_m2 > 0 and r.monthly_rent_krw is not None]
    total_area = sum(r.area_m2 for r in with_area)
    estimate = sum(r.monthly_rent_krw for r in with_area) / total_area * req.rental_area_m2 if total_area else None
    average_sales = item.metrics.average_sales_krw if item.metrics else None
    monthly_sales = average_sales / 3 if average_sales is not None else None
    source = "개발용 가상 매물" if mode == "demo" else "수집 시점의 공개 임대 광고"
    facts = {
        "average_sales_krw": average_sales,
        "rent_summary": rollup,
        "rental_estimate": {
            "area_m2": req.rental_area_m2,
            "floor": req.rental_floor or "전체 층",
            "sample_count": len(with_area),
            "monthly_rent_krw": estimate,
            "monthly_sales_krw": monthly_sales,
            "sales_ratio_pct": estimate / monthly_sales * 100 if estimate is not None and monthly_sales and monthly_sales > 0 else None,
            "method": f"월세 합계 / 면적 합계 * 설정 면적. 관리비와 보증금 제외. {source} 기준.",
        },
    }
    return rental_data, facts


def build_comparison_evidence(analysis: AnalysisService, req: ExplanationRequest) -> dict:
    comparison = analysis.compare(req.model_copy(update={"area_codes": sorted(req.area_codes)}))
    mode = analysis.db.data_mode
    prior = f"{int(req.quarter[:4]) - 1}{req.quarter[4:]}"
    rent = req.section == Section.rent
    overview = req.section == Section.competition
    two_periods = req.section in (Section.competition, Section.profitability)
    fields = ("total_sales_krw", "store_count") if two_periods else ("total_sales_krw", "transaction_count")
    if overview:
        fields += ("transaction_count",)

    facts = {}
    area_data = []
    for item in comparison.items:
        code = item.area.code
        prefix = f"{code}."
        facts[prefix + "name"] = item.area.name
        data = {"area_code": code, "area_name": item.area.name, "evidence_ids": []}
        if rent:
            rental_data, rental_facts = rent_input(item, req, mode)
            data.update(rental_data)
            facts.update({prefix + field: value for field, value in rental_facts.items()})
            data["evidence_ids"].append(prefix + "rent_summary")
        else:
            rows = {r.quarter: r for r in item.observations}
            data["current"] = raw_metrics(rows.get(req.quarter), fields)
            facts[prefix + "current"] = data["current"]
            data["evidence_ids"].append(prefix + "current")
            if two_periods:
                data["comparison"] = raw_metrics(rows.get(prior), fields)
                facts[prefix + "comparison"] = data["comparison"]
                data["evidence_ids"].append(prefix + "comparison")
                facts[prefix + "observations"] = [
                    row.model_dump() for quarter in (prior, req.quarter) if (row := rows.get(quarter))
                ]
            if item.metrics is not None:
                facts.update({prefix + field: value for field, value in item.metrics.model_dump().items()})
            else:
                facts[prefix + "missing"] = item.missing_reason or "기준 분기 지표 미확보"
        area_data.append(data)

    evidence = {
        "scope": req.scope, "section": req.section, "data_mode": mode,
        "data_version": comparison.meta.data_version, "quarter": req.quarter,
        "industry_code": req.industry_code, "industry_name": "카페",
        "current_quarter_start": quarter_start(req.quarter).isoformat(),
        "area_data": area_data, "facts": facts,
    }
    if two_periods:
        evidence["comparison_quarter_start"] = quarter_start(prior).isoformat()
    if rent:
        evidence["aggregation_policy"] = {
            "selected_floor": req.rental_floor or "전체 층",
            "iqr_min_count": RENT_MIN_IQR_SAMPLE,
            "iqr_multiplier": 1.5,
        }
    return evidence
