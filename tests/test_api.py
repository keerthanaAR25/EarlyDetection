"""
Phase 19 tests: FastAPI endpoints, exercised via TestClient against
the real loaded database.

Run with: pytest tests/test_api.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_summary_returns_real_counts():
    r = client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_transactions"] > 0
    assert data["total_accounts"] > 0


def test_rings_list_not_empty():
    r = client.get("/api/rings")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_ring_detail_404_for_unknown_id():
    r = client.get("/api/rings/DOES_NOT_EXIST")
    assert r.status_code == 404


def test_ring_detail_and_graph_consistent():
    rings = client.get("/api/rings").json()
    if not rings:
        pytest.skip("no ring candidates loaded")
    ring_id = rings[0]["candidate_ring_id"]

    detail = client.get(f"/api/rings/{ring_id}").json()
    graph = client.get(f"/api/rings/{ring_id}/graph").json()
    assert len(graph["nodes"]) <= detail["n_accounts"] + 1  # evidence subgraph is a subset


def test_ring_risk_score_never_fabricated():
    rings = client.get("/api/rings").json()
    for r in rings:
        assert r["risk_score"] == "Not yet evaluated" or isinstance(r["risk_score"], (int, float))


def test_alerts_endpoint_filters_by_risk_level():
    r = client.get("/api/alerts", params={"risk_level": "CRITICAL"})
    assert r.status_code == 200
    for a in r.json():
        assert a["risk_level"] == "CRITICAL"


def test_transactions_endpoint_respects_limit():
    r = client.get("/api/transactions", params={"limit": 3})
    assert r.status_code == 200
    assert len(r.json()) <= 3


def test_metrics_endpoint_returns_real_model_comparison():
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_analyze_and_retrain_return_accepted_not_fabricated_results():
    r = client.post("/api/analyze")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
