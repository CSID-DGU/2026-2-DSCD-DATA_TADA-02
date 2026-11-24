import asyncio

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.explanations import ExplanationService
from backend.app.main import create_app
from backend.app.schemas import ExplanationBlock, ExplanationContent, ExplanationRequest


def content(evidence):
    overview = evidence["section"] == "competition"
    ids = evidence["area_data"][0]["evidence_ids"]
    return ExplanationContent(
        summary="개발용 가상 자료 해설",
        blocks=[ExplanationBlock(title="수치 관계", text="제공된 가상 수치를 설명합니다.", evidence_ids=ids[:1])] if overview else [],
        caveats=[],
        area_summaries=[{"area_code": area["area_code"], "text": "가상 상권의 상황을 설명합니다."}
                        for area in evidence["area_data"]] if overview else [],
    )


def test_cache_model_context_and_failure_isolation(tmp_path):
    calls = []

    async def provider(evidence):
        calls.append(evidence)
        return content(evidence), {"input_tokens": 10, "output_tokens": 20}

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'llm.db'}", llm_enabled=True,
                        openai_api_key="test-not-a-secret", openai_model="test-model-a", _env_file=None)
    query = {"scope": "comparison", "section": "competition", "area_codes": ["3120052", "3120104"]}
    with TestClient(create_app(settings, provider)) as client:
        first = client.post("/api/v1/explanations", json=query).json()
        second = client.post("/api/v1/explanations", json={**query, "area_codes": query["area_codes"][::-1]}).json()
        assert first["status"] == "completed" and not first["cache_hit"]
        assert second["cache_hit"] and first["cache_key"] == second["cache_key"]
        assert len(calls) == 1
        changed = client.post("/api/v1/explanations", json={**query, "section": "profitability"}).json()
        assert changed["cache_key"] != first["cache_key"] and len(calls) == 2
        client.app.state.explanations.settings.openai_model = "test-model-b"
        newer = client.post("/api/v1/explanations", json=query).json()
        assert newer["cache_key"] != first["cache_key"] and len(calls) == 3


def test_provider_failure_invalid_evidence_and_timeout_leave_analysis_available(tmp_path):
    async def failing(_):
        raise RuntimeError("Do not echo provider details")

    async def invalid(evidence):
        value = content(evidence)
        value.blocks[0].evidence_ids = ["invented"]
        return value, {}

    async def slow(evidence):
        await asyncio.sleep(2)
        return content(evidence), {}

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'failure.db'}", llm_enabled=True,
                        openai_api_key="test", openai_model="test", llm_timeout_seconds=1, _env_file=None)
    with TestClient(create_app(settings, failing)) as client:
        query = {"scope": "comparison", "section": "competition", "area_codes": ["3120052"]}
        for provider in (failing, invalid, slow):
            client.app.state.explanations.provider = provider
            response = client.post("/api/v1/explanations", json=query)
            assert response.status_code == 502 and response.json()["status"] == "failed"
            assert "provider details" not in response.text and "invented" not in response.text
            assert client.get("/api/v1/areas/3120052/analysis").status_code == 200


def test_database_claim_deduplicates_separate_service_instances(tmp_path):
    calls = []

    async def provider(evidence):
        calls.append(1)
        await asyncio.sleep(.05)
        return content(evidence), {}

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'race.db'}", llm_enabled=True,
                        openai_api_key="test", openai_model="test", _env_file=None)
    with TestClient(create_app(settings, provider)) as client:
        original = client.app.state.explanations
        other = ExplanationService(settings, original.db, original.analysis, provider)
        query = ExplanationRequest(scope="comparison", section="competition", area_codes=["3120052"])

        async def race():
            return await asyncio.gather(original.explain(query), other.explain(query))

        results = asyncio.run(race())
        assert {r.status for r in results} == {"completed", "running"}
        assert len(calls) == 1


def test_access_token_is_enforced(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'auth.db'}", service_access_token="test-access", _env_file=None)
    with TestClient(create_app(settings)) as client:
        query = {"scope": "comparison", "section": "rent", "area_codes": ["3120052"]}
        assert client.post("/api/v1/explanations", json=query).status_code == 401
        assert client.get("/metrics").status_code == 401
        assert client.post("/api/v1/explanations", json=query, headers={"Authorization": "Bearer test-access"}).status_code == 200
        assert client.get("/health/live").status_code == 200


def test_comparison_prompt_inputs_partial_data_and_detail_scope(tmp_path):
    calls = []

    async def provider(evidence):
        calls.append(evidence)
        return content(evidence), {}

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'compare.db'}", llm_enabled=True,
                        openai_api_key="test", openai_model="test", _env_file=None)
    query = {"scope": "comparison", "section": "competition", "area_codes": ["3120052", "3130310"]}
    with TestClient(create_app(settings, provider)) as client:
        result = client.post("/api/v1/explanations", json=query).json()
        assert result["status"] == "completed"
        assert {item["area_code"] for item in result["content"]["area_summaries"]} == set(query["area_codes"])
        data = {item["area_code"]: item for item in calls[0]["area_data"]}
        assert data["3120052"]["comparison"]["transaction_count"] > 0
        assert data["3130310"]["current"] is None
        for section in ("profitability", "demand", "rent"):
            payload = {**query, "section": section}
            assert client.post("/api/v1/explanations", json=payload).json()["status"] == "completed"
        assert calls[1]["area_data"][0]["current"].keys() == {"total_sales_krw", "store_count"}
        assert calls[2]["area_data"][0]["current"].keys() == {"total_sales_krw", "transaction_count"}
        assert "comparison" not in calls[2]["area_data"][0]
        assert calls[3]["area_data"][0]["rent_summary"]["monthly_rent_krw"]["used_count"] > 0
        detail = {**query, "scope": "detail", "section": "location", "location_view": "stores",
                  "area_codes": ["3120052"], "listing_id": "unused-listing"}
        assert client.post("/api/v1/explanations", json=detail).json()["status"] == "disabled"
        assert len(calls) == 4

def test_detail_generation_reused_by_another_server(tmp_path):
    calls = []

    async def provider(evidence):
        calls.append(evidence)
        key = next(key for key in ("observations", "distribution", "rental_count") if key in evidence["facts"])
        return ExplanationContent(
            summary="자료를 설명합니다.",
            blocks=[ExplanationBlock(title="지표", text="제공된 지표를 설명합니다.", evidence_ids=[key])],
            caveats=[],
        ), {}

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'detail.db'}", llm_enabled=True,
                        openai_api_key="test", openai_model="test", llm_cache_ttl_seconds=1, _env_file=None)
    base = {"scope": "detail", "area_codes": ["3120052"]}
    queries = [
        {**base, "section": "profitability"},
        {**base, "section": "demand", "demand_metric": "transactions"},
        {**base, "section": "demand", "demand_metric": "floating_population"},
        {**base, "section": "location", "location_view": "rentals"},
    ]
    with TestClient(create_app(settings, provider)) as client:
        first = [client.post("/api/v1/explanations", json=query).json() for query in queries]
        assert all(result["status"] == "completed" and not result["cache_hit"] for result in first)
        assert len({result["cache_key"] for result in first}) == 4
        assert all(item["page"]["scope"] == "detail" for item in calls)
        assert all("nearby_stores" not in item["facts"] for item in calls)

    with TestClient(create_app(settings, provider)) as client:
        for query, original in zip(queries, first):
            result = client.post("/api/v1/explanations", json=query).json()
            assert result["cache_hit"] and result["content"] == original["content"]
    assert len(calls) == 4
