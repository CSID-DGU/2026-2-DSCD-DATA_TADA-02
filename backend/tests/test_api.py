import math

import pytest

from backend.app.analysis import competition_type, divide, yoy

CODES = ["3120052", "3120104", "3120100", "3120050", "3120053"]


def test_health_catalog_and_timing(client):
    for path in ("/health/live", "/health/ready", "/api/v1/config", "/api/v1/areas"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["x-request-id"]
        assert response.headers["server-timing"].startswith("app;dur=")
    response = client.get("/api/v1/areas")
    assert response.json()["total"] == 1596
    assert len(response.json()["items"]) == 1596
    assert "경계가 아닙니다" in response.json()["marker_meaning"]
    values = client.get("/api/v1/areas", params={"q": "성수역", "district": "성동구"}).json()["items"]
    assert values and all("성수역" in a["name"] and a["district"] == "성동구" for a in values)


@pytest.mark.parametrize("codes", [[], CODES + ["3130310"], [CODES[0], CODES[0]]])
def test_candidate_limit_and_duplicate_validation(client, codes):
    response = client.post("/api/v1/comparisons", json={"area_codes": codes})
    assert response.status_code == 422
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_five_candidates_order_and_independent_arithmetic(client):
    response = client.post("/api/v1/comparisons", json={"area_codes": CODES[::-1]})
    assert response.status_code == 200
    body = response.json()
    assert [i["area"]["code"] for i in body["items"]] == CODES[::-1]
    assert body["meta"]["data_mode"] == "demo"
    for item in body["items"]:
        m = item["metrics"]
        assert math.isclose(m["average_sales_krw"], m["total_sales_krw"] / m["store_count"])
        assert math.isclose(m["average_payment_krw"], m["total_sales_krw"] / m["transaction_count"])
        assert math.isclose(m["transactions_per_store"], m["transaction_count"] / m["store_count"])


def test_missing_data_stays_null(client):
    response = client.get("/api/v1/areas/3130310/analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["current"] is None and data["forecast"] is None
    assert data["missing_reason"] and data["observations"] == []
    assert client.get("/api/v1/areas/unknown/analysis").status_code == 404
    assert client.get("/api/v1/areas/3120052/analysis?quarter=2026Q9").status_code == 422
    assert client.post("/api/v1/comparisons", json={"area_codes": CODES, "industry_code": "CS100001"}).status_code == 422


def test_observations_yoy_and_unvalidated_forecast(client):
    body = client.get(f"/api/v1/areas/{CODES[0]}/analysis").json()
    rows = {r["quarter"]: r for r in body["observations"]}
    for quarter, row in rows.items():
        old = rows.get(str(int(quarter[:4]) - 1) + quarter[4:])
        if old:
            assert math.isclose(row["sales_yoy_pct"], (row["total_sales_krw"] / old["total_sales_krw"] - 1) * 100)
        else:
            assert row["sales_yoy_pct"] is None
    assert [p["quarter"] for p in body["forecast"]["points"]] == ["2026Q3", "2026Q4"]
    assert body["forecast"]["coverage_validated"] is False
    for p in body["forecast"]["points"]:
        assert p["lower90_krw"] < p["lower80_krw"] < p["average_sales_krw"] < p["upper80_krw"] < p["upper90_krw"]
    assert body["boundary"] is None


def test_nearby_radius_filters_and_listing_ownership(client):
    code = CODES[0]
    listing = client.get(f"/api/v1/areas/{code}/analysis").json()["rentals"][0]["id"]
    counts = []
    for radius in (100, 300, 500):
        r = client.get(f"/api/v1/areas/{code}/nearby-stores", params={"listing_id": listing, "radius_m": radius})
        assert r.status_code == 200
        values = r.json()
        assert all(s["distance_m"] <= radius for s in values)
        assert [s["distance_m"] for s in values] == sorted(s["distance_m"] for s in values)
        counts.append(len(values))
    assert counts == sorted(counts) and counts[0] < counts[-1]
    assert client.get(f"/api/v1/areas/{CODES[1]}/nearby-stores", params={"listing_id": listing}).status_code == 404
    assert client.get(f"/api/v1/areas/{code}/nearby-stores", params={"listing_id": listing, "radius_m": 99999}).status_code == 422


def test_metrics_use_route_templates_not_user_values(client):
    for code in CODES:
        client.get(f"/api/v1/areas/{code}/analysis")
    client.get('/unknown-user-path')
    metrics = client.get("/metrics").text
    assert 'route="/api/v1/areas/{area_code}/analysis"' in metrics
    assert 'le="+Inf"' in metrics
    assert CODES[0] not in metrics and 'unknown-user-path' not in metrics


def test_llm_disabled_all_page_contexts_and_missing(client):
    for scope, sections, codes in [("comparison", ["profitability", "competition", "demand", "rent"], CODES),
                                   ("detail", ["profitability", "competition", "demand", "location"], CODES[:1])]:
        for section in sections:
            result = client.post("/api/v1/explanations", json={"scope": scope, "section": section, "area_codes": codes})
            assert result.status_code == 200
            assert result.json()["status"] == "disabled"
            assert result.json()["content"] is None
    assert client.post("/api/v1/explanations", json={"scope": "detail", "section": "competition", "area_codes": CODES}).status_code == 422
    result = client.post("/api/v1/explanations", json={"scope": "comparison", "section": "competition", "area_codes": ["3130310"]})
    assert result.json()["status"] == "unavailable"
    result = client.post("/api/v1/explanations", json={"scope": "detail", "section": "location", "location_view": "stores", "area_codes": CODES[:1]})
    assert result.status_code == 422


def test_zero_denominators_and_boundary_classification():
    assert divide(100, 0) is None and yoy(10, 0) is None and yoy(None, 10) is None
    assert yoy(0, 10) == -100
    assert competition_type(0, 2) == "변화 없음 / 경계"
    assert competition_type(1, 2) == "시장확장형"
    assert competition_type(1, -2) == "매출개선형"
    assert competition_type(-1, 2) == "경쟁압박형"
    assert competition_type(-1, -2) == "시장축소형"


def test_internal_error_and_readiness_failure_are_observable(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("private internal detail")
    monkeypatch.setattr(client.app.state.analysis, "detail", broken)
    response = client.get("/api/v1/areas/3120052/analysis")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private internal detail" not in response.text
    assert response.headers["x-request-id"]
    assert client.get("/health/live").status_code == 200
    monkeypatch.setattr(client.app.state.db.engine, "connect", broken)
    assert client.get("/health/ready").status_code == 503
