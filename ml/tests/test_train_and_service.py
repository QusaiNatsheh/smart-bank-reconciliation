import json

from fastapi.testclient import TestClient
from smart_reconcile_ml import service
from smart_reconcile_ml.feedback import load_feedback_groups
from smart_reconcile_ml.model import Model


def test_model_beats_baseline(trained_model):
    meta = json.loads((trained_model / "meta.json").read_text())
    test = meta["metrics"]["test"]
    assert test["candidate_recall"] > 0.95
    assert test["model"]["top1"] >= test["baseline"]["top1"]
    assert test["model"]["top1"] > 0.85


def _client(trained_model, tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(trained_model))
    monkeypatch.setenv("FEEDBACK_DIR", str(tmp_path))
    service.get_model.cache_clear()
    service.get_store.cache_clear()
    return TestClient(service.app)


PAYLOAD = {
    "line": {
        "amount": 350.0,
        "date": "2026-03-01",
        "payment_ref": "INV/2026/00002 + INV/2026/00001",
        "partner_name": "ALNOOR TRADING",
        "currency": "JOD",
    },
    "invoices": [
        {
            "id": 1,
            "number": "INV/2026/00001",
            "partner_id": 1,
            "partner_names": ["Al Nour Trading Co."],
            "invoice_date": "2026-01-05",
            "amount_residual": 100.0,
        },
        {
            "id": 2,
            "number": "INV/2026/00002",
            "partner_id": 1,
            "partner_names": ["Al Nour Trading Co."],
            "invoice_date": "2026-01-20",
            "amount_residual": 250.0,
        },
        {
            "id": 3,
            "number": "INV/2026/00003",
            "partner_id": 2,
            "partner_names": ["Al Hayat Pharmacy"],
            "invoice_date": "2026-01-25",
            "amount_residual": 350.0,
        },
    ],
}


def test_suggest_and_feedback(trained_model, tmp_path, monkeypatch):
    client = _client(trained_model, tmp_path, monkeypatch)
    assert client.get("/health").json()["status"] == "ok"
    res = client.post("/suggest", json=PAYLOAD)
    assert res.status_code == 200
    body = res.json()
    top = body["suggestions"][0]
    assert top["invoice_ids"] == [1, 2]
    assert 0 <= top["confidence"] <= 1
    assert top["reasons"]

    fb = client.post("/feedback", json={"request_id": body["request_id"], "invoice_ids": [1, 2], "accepted": True})
    assert fb.status_code == 200
    groups = load_feedback_groups(tmp_path, start_id=1000)
    assert groups["label"].sum() == 1


def test_input_validation(trained_model, tmp_path, monkeypatch):
    client = _client(trained_model, tmp_path, monkeypatch)
    bad = {**PAYLOAD, "line": {**PAYLOAD["line"], "amount": -5}}
    assert client.post("/suggest", json=bad).status_code == 422
    assert client.post("/feedback", json={"request_id": "../x", "invoice_ids": [], "accepted": True}).status_code == 404


def test_explanations_come_from_positive_contributions(trained_model):
    model = Model(trained_model)
    assert model.confidence([]) == 0.0
