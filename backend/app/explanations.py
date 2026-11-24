import asyncio
import hashlib
import json
import re
import time
import uuid

from openai import AsyncOpenAI
from sqlalchemy import and_, or_, update
from sqlalchemy.exc import IntegrityError

from .analysis import AnalysisService
from .comparison_explanations import COMPARISON_VERSION, build_comparison_evidence, load_comparison_prompt
from .config import Settings
from .db import Database, ExplanationRow
from .detail_explanations import (
    PERMANENT_EXPIRY, build_detail_evidence, detail_key, detail_tab, has_detail_data,
    load_detail_prompt, prompt_version as detail_prompt_version,
)
from .schemas import ExplanationContent, ExplanationRequest, ExplanationResponse
from .telemetry import event, span

DETAIL_PROMPT_VERSION = "detail-pending"
DETAIL_DISCLAIMER = re.compile(
    r"추가\s*확인이\s*필요|(?:확인|검토|점검)할\s*필요가\s*있|"
    r"직접\s*비교(?:하여야|해야)|보장하지\s*않"
)


def build_evidence(analysis: AnalysisService, req: ExplanationRequest) -> dict:
    if req.scope == "comparison":
        return build_comparison_evidence(analysis, req)
    facts = {}
    versions = {}
    for code in sorted(req.area_codes):
        detail = analysis.detail(code, req.quarter)
        versions[code] = detail.meta.data_version
        if detail.current is None:
            facts[f"{code}.missing"] = detail.missing_reason
            continue
        prefix = f"{code}."
        facts[prefix + "name"] = detail.area.name
        current = detail.current.model_dump()
        keys = {
            "profitability": ["average_sales_krw", "average_sales_yoy_pct", "total_sales_krw", "store_count"],
            "competition": ["sales_yoy_pct", "stores_yoy_pct", "transactions_yoy_pct", "average_sales_krw", "average_sales_yoy_pct", "total_sales_krw", "store_count", "transaction_count", "transactions_per_store", "average_payment_krw"],
            "demand": ["transactions_per_store", "average_payment_krw", "transaction_count", "store_count"],
            "rent": ["average_sales_krw"], "location": [],
        }[req.section]
        for key in keys:
            facts[prefix + key] = current[key]
        if req.section == "competition":
            facts[prefix + "rentals"] = [r.model_dump() for r in detail.rentals]
        if req.section == "rent" or (req.section == "location" and req.location_view == "rentals"):
            facts[prefix + "rentals"] = [r.model_dump() for r in detail.rentals]
        if req.scope == "detail":
            if req.section in ("profitability", "competition"):
                facts[prefix + "observations"] = [r.model_dump() for r in detail.observations]
                facts[prefix + "forecast"] = detail.forecast.model_dump() if detail.forecast else None
            if req.section == "demand":
                distribution = detail.demand.get(req.demand_metric)
                facts[prefix + "distribution"] = distribution.model_dump() if distribution else None
                facts[prefix + "demand_distributions"] = {key: value.model_dump() for key, value in detail.demand.items()}
    return {"scope": req.scope, "section": req.section, "data_mode": analysis.db.data_mode,
            "data_versions": versions, "quarter": req.quarter, "industry_code": req.industry_code, "facts": facts}


def validate_content(content: ExplanationContent, evidence: dict):
    comparison = evidence.get("scope") == "comparison"
    overview = comparison and evidence.get("section") == "competition"
    if not content.summary.strip() or len(content.blocks) > 5:
        raise ValueError("Empty or oversized commentary")
    if not comparison and not content.blocks:
        raise ValueError("Empty commentary blocks")
    if evidence.get("page", {}).get("scope") == "detail":
        if content.area_summaries:
            raise ValueError("Unexpected area summaries")
        passages = [content.summary, *content.caveats, *(block.text for block in content.blocks)]
        if any(DETAIL_DISCLAIMER.search(text) for text in passages):
            raise ValueError("Generic disclaimer in detailed commentary")
    if comparison:
        if content.caveats or (not overview and (content.blocks or content.area_summaries)):
            raise ValueError("Unexpected comparison output fields")
        if overview:
            expected = {area["area_code"] for area in evidence["area_data"]}
            actual = [area.area_code for area in content.area_summaries if area.text.strip()]
            if set(actual) != expected or len(content.area_summaries) != len(expected):
                raise ValueError("Overview must summarize each selected area exactly once")
    valid_ids = set(evidence["facts"])
    for block in content.blocks:
        if not block.text.strip() or not block.evidence_ids or not set(block.evidence_ids) <= valid_ids:
            raise ValueError("Unknown or missing evidence references")
    if "\u00b7" in content.model_dump_json():
        raise ValueError("Forbidden punctuation")
    # Citation validity is checked here; semantic/numeric correctness requires the evaluation suite.


class ExplanationService:
    def __init__(self, settings: Settings, db: Database, analysis: AnalysisService, provider=None):
        self.settings, self.db, self.analysis = settings, db, analysis
        self.capacity = asyncio.Semaphore(settings.llm_max_concurrent)
        self.provider = provider
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds, max_retries=0,
        ) if settings.llm_enabled and provider is None else None

    async def close(self):
        if self.client:
            await self.client.close()

    async def generate(self, evidence: dict, prompt: str) -> tuple[ExplanationContent, dict]:
        if self.provider:
            return await self.provider(evidence)
        inputs = ({key: value for key, value in evidence.items() if key != "facts"}
                  if evidence.get("scope") == "comparison" else evidence)
        response = await self.client.responses.parse(
            model=self.settings.openai_model,
            input=[{"role": "system", "content": prompt},
                   {"role": "user", "content": json.dumps(inputs, ensure_ascii=False)}],
            text_format=ExplanationContent, max_output_tokens=3000, store=False,
        )
        if response.status != "completed" or response.output_parsed is None:
            raise ValueError("Refused or incomplete provider response")
        usage = response.usage
        return response.output_parsed, {
            "input_tokens": usage.input_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "provider_request_id": response._request_id,
        }

    def claim(self, key: str, owner: str, *, detail: bool = False) -> tuple[str, dict]:
        now = time.time()
        sessions = self.db.detail_session if detail else self.db.session
        with sessions.begin() as session:
            row = session.get(ExplanationRow, key)
            if row and row.status == "completed" and row.expires_at > now:
                return "cached", row.payload
            if row and row.status == "running" and row.lease_until > now:
                return "running", {}
            if row:
                updated = session.execute(update(ExplanationRow).where(
                    ExplanationRow.key == key,
                    or_(
                        and_(ExplanationRow.status == "running", ExplanationRow.lease_until <= now),
                        and_(ExplanationRow.status == "completed", ExplanationRow.expires_at <= now),
                        ExplanationRow.status == "failed",
                    ),
                ).values(status="running", owner=owner,
                         lease_until=now + self.settings.llm_timeout_seconds + 20,
                         expires_at=0, payload={}))
                return ("claimed" if updated.rowcount == 1 else "running"), {}
            session.add(ExplanationRow(key=key, owner=owner, status="running",
                                      lease_until=now + self.settings.llm_timeout_seconds + 20,
                                      expires_at=0, payload={}))
        return "claimed", {}

    def finish(self, key: str, owner: str, content: ExplanationContent | None, *, detail: bool = False):
        expires_at = PERMANENT_EXPIRY if detail else time.time() + self.settings.llm_cache_ttl_seconds
        sessions = self.db.detail_session if detail else self.db.session
        with sessions.begin() as session:
            changed = session.execute(update(ExplanationRow).where(
                ExplanationRow.key == key, ExplanationRow.owner == owner,
            ).values(status="completed" if content else "failed", payload=content.model_dump() if content else {},
                     lease_until=0, expires_at=expires_at if content else 0))
            if content and changed.rowcount != 1:
                raise RuntimeError("Lease ownership lost")

    async def explain(self, req: ExplanationRequest) -> ExplanationResponse:
        comparison = req.scope == "comparison"
        tab = detail_tab(req) if not comparison else None
        detail_enabled = bool(tab and self.settings.llm_enabled)
        with span("evidence.build", section=req.section, scope=req.scope):
            evidence = await (
                asyncio.to_thread(build_detail_evidence, self.analysis, req, tab)
                if detail_enabled else asyncio.to_thread(build_evidence, self.analysis, req)
            )
        if detail_enabled:
            prompt = load_detail_prompt(tab)
            prompt_version = detail_prompt_version(prompt)
            key = detail_key(evidence, prompt, self.settings.openai_model)
        else:
            prompt = load_comparison_prompt(req.section) if comparison else ""
            prompt_version = COMPARISON_VERSION if comparison else DETAIL_PROMPT_VERSION
            context = req.model_dump(mode="json")
            context["area_codes"] = sorted(req.area_codes)
            key = hashlib.sha256(json.dumps({
                "context": context, "evidence": evidence, "prompt": prompt,
                "prompt_version": prompt_version, "metric_version": "metrics-v1",
                "model": self.settings.openai_model, "provider": "openai-responses",
            }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        common = dict(cache_key=key, prompt_version=prompt_version,
                      model=self.settings.openai_model or None, evidence=evidence)
        if comparison and req.section != "rent" and not any(
            area["current"] is not None for area in evidence["area_data"]
        ):
            return ExplanationResponse(status="unavailable", message="선택한 후보의 기준 분기 지표가 없습니다.", **common)
        if not self.settings.llm_enabled or not (comparison or tab):
            message = "상권 비교 AI 해설을 준비 중입니다." if comparison else "상세 분석 해설을 준비 중입니다."
            return ExplanationResponse(status="disabled", message=message, **common)
        if tab and not has_detail_data(tab, evidence["facts"]):
            return ExplanationResponse(status="unavailable", message="이 화면의 해설에 사용할 자료가 없습니다.", **common)
        owner = str(uuid.uuid4())
        try:
            claimed, payload = await asyncio.to_thread(self.claim, key, owner, detail=detail_enabled)
        except IntegrityError:
            claimed, payload = "running", {}
        if claimed == "cached":
            event("llm.cache", hit=True, model=self.settings.openai_model)
            return ExplanationResponse(status="completed", content=ExplanationContent.model_validate(payload), cache_hit=True, **common)
        if claimed == "running":
            return ExplanationResponse(status="running", retry_after_seconds=2, message="같은 근거의 해설을 생성하고 있습니다.", **common)
        try:
            # Request remains alive through completion: no detached BackgroundTasks on Cloud Run.
            async with asyncio.timeout(self.settings.llm_timeout_seconds):
                async with self.capacity:
                    with span("llm.generate", model=self.settings.openai_model, prompt_version=prompt_version):
                        content, usage = await self.generate(evidence, prompt)
                    with span("llm.validate"):
                        validate_content(content, evidence)
            await asyncio.to_thread(self.finish, key, owner, content, detail=detail_enabled)
            event("llm.usage", model=self.settings.openai_model, cache_hit=False, **usage)
            return ExplanationResponse(status="completed", content=content, **common)
        except BaseException as exc:
            await asyncio.to_thread(self.finish, key, owner, None, detail=detail_enabled)
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            event("llm.failed", error_type=type(exc).__name__, model=self.settings.openai_model)
            return ExplanationResponse(status="failed", message="해설 생성에 실패했습니다. 기본 지표는 계속 볼 수 있습니다.", **common)
