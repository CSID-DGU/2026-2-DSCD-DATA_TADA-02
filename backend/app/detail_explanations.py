"""Shared request and storage contract for the four detailed commentary views."""

import calendar
import hashlib
import json
from pathlib import Path

from .analysis import AnalysisService
from .schemas import DetailResponse, ExplanationRequest

PROMPTS = Path(__file__).with_name("prompts") / "detail"
FILES = {"sales": "sales.md", "transactions": "demand.md",
         "floating_population": "demand.md", "rentals": "rentals.md"}
SECTIONS = {"sales": "profitability", "transactions": "demand",
            "floating_population": "demand", "rentals": "location"}
RENT_FIELDS = ("monthly_rent_krw", "deposit_krw", "area_m2", "floor")


def detail_tab(req: ExplanationRequest) -> str | None:
    if req.section == "location":
        return "rentals" if req.location_view == "rentals" else None
    if req.section == "demand":
        return req.demand_metric
    return "sales" if req.section == "profitability" else None


def load_detail_prompt(tab: str) -> str:
    return "\n\n".join((PROMPTS / name).read_text(encoding="utf-8").strip()
                       for name in ("common.md", "detail-common.md", FILES[tab]))


def prompt_version(prompt: str) -> str:
    return "detail-" + hashlib.sha256(prompt.encode()).hexdigest()[:16]


def rent_stats(rentals: list[dict], field: str) -> dict:
    values = [r[field] for r in rentals if r[field] is not None]
    return {"known_count": len(values), "min_krw": min(values, default=None), "max_krw": max(values, default=None)}


def detail_facts(detail: DetailResponse, tab: str) -> dict:
    facts = {"area_name": detail.area.name, "current": detail.current.model_dump() if detail.current else None}
    if tab == "sales":
        facts["observations"] = [row.model_dump() for row in detail.observations]
        facts["forecast"] = detail.forecast.model_dump() if detail.forecast else None
    elif tab == "rentals":
        rentals = [rental.model_dump(include=set(RENT_FIELDS)) for rental in detail.rentals]
        facts["rental_count"] = len(rentals)
        facts["monthly_rent_stats"] = rent_stats(rentals, "monthly_rent_krw")
        facts["deposit_stats"] = rent_stats(rentals, "deposit_krw")
        facts["rental_examples"] = [
            r for r in rentals if (r["area_m2"] is not None or r["floor"]) and
            (r["monthly_rent_krw"] is not None or r["deposit_krw"] is not None)
        ][:2]
    else:
        for metric in ("transactions", "floating_population"):
            distribution = detail.demand.get(metric)
            facts[f"{metric}_distribution"] = distribution.model_dump() if distribution else None
        year, quarter = int(detail.meta.quarter[:4]), int(detail.meta.quarter[-1])
        month = (quarter - 1) * 3 + 1
        facts["quarter_day_count"] = sum(calendar.monthrange(year, x)[1] for x in range(month, month + 3))
    return facts


def detail_evidence(*, area_code: str, quarter: str, industry_code: str, data_mode: str,
                    data_version: str, tab: str, source: dict) -> dict:
    section = SECTIONS[tab]
    page = {"scope": "detail", "section": section}
    facts = {"area_name": source["area_name"]}
    if section == "demand":
        page["demand_metric"] = tab
        other = "floating_population" if tab == "transactions" else "transactions"
        facts["distribution"] = source[f"{tab}_distribution"]
        facts["comparison_distribution"] = source[f"{other}_distribution"]
        if tab == "transactions":
            current = source["current"] or {}
            facts.update(transaction_count=current.get("transaction_count"),
                         transactions_per_store=current.get("transactions_per_store"),
                         quarter_day_count=source["quarter_day_count"])
    elif section == "location":
        page["location_view"] = tab
        facts.update({name: source[name] for name in (
            "rental_count", "monthly_rent_stats", "deposit_stats", "rental_examples",
        )})
    else:
        facts.update({name: source[name] for name in ("current", "observations", "forecast")})
    return {"page": page, "area_code": area_code, "quarter": quarter, "industry_code": industry_code,
            "data_mode": data_mode, "data_version": data_version, "facts": facts}


def build_detail_evidence(analysis: AnalysisService, req: ExplanationRequest, tab: str) -> dict:
    area_code = req.area_codes[0]
    detail = analysis.detail(area_code, req.quarter)
    return detail_evidence(area_code=area_code, quarter=req.quarter, industry_code=req.industry_code,
                           data_mode=analysis.db.data_mode, data_version=detail.meta.data_version,
                           tab=tab, source=detail_facts(detail, tab))


def detail_key(evidence: dict, prompt: str, model: str) -> str:
    data = {"evidence": evidence, "prompt": prompt, "model": model, "provider": "openai-responses"}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def has_detail_data(tab: str, facts: dict) -> bool:
    if tab == "rentals":
        return True
    if tab == "transactions":
        return facts["distribution"] is not None or facts["transaction_count"] is not None
    if tab == "floating_population":
        return facts["distribution"] is not None
    return ((facts["current"] or {}).get("average_sales_krw") is not None
            or any(row["average_sales_krw"] is not None for row in facts["observations"])
            or any(row["average_sales_krw"] is not None for row in (facts["forecast"] or {}).get("points", [])[:2]))
