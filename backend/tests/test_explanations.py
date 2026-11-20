import asyncio

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.explanations import ExplanationService
from backend.app.main import create_app
from backend.app.schemas import ExplanationBlock, ExplanationContent, ExplanationRequest


def content(evidence):
    ids = list(evidence["facts"])
    return ExplanationContent(summary="개발용 가상 자료 해설", blocks=[
        ExplanationBlock(title="수치 관계", text="제공된 가상 수치를 설명합니다.", evidence_ids=ids[:1]),
    ], caveats=["실제 분석 결과가 아닙니다."])


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
        query = {"scope": "detail", "section": "profitability", "area_codes": ["3120052"]}
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
