from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health_reports_inference_device() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["device"] in {"cpu", "cuda"}


def test_stages_match_pipeline_order() -> None:
    response = client.get("/api/stages")
    assert response.status_code == 200
    assert [stage["id"] for stage in response.json()] == [
        "input",
        "quality",
        "restoration",
        "grade",
        "lesion",
        "report",
    ]


def test_model_checkpoints_are_detected() -> None:
    response = client.get("/api/models")
    assert response.status_code == 200
    models = response.json()
    assert {model["id"] for model in models} == {
        "quality",
        "restoration",
        "grade",
        "lesion",
    }
    assert all(model["checkpoint_present"] for model in models)


def test_rejects_non_image_upload() -> None:
    response = client.post(
        "/api/analyze",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 422


def test_rejects_invalid_session_id() -> None:
    response = client.get("/api/analysis/not-a-session")
    assert response.status_code == 404


def test_explorer_architectures_use_real_model_blocks() -> None:
    expected_minimums = {"quality": 20, "restoration": 40, "grade": 20, "lesion": 25}
    for model_id, minimum in expected_minimums.items():
        response = client.get(f"/api/explorer/{model_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["block_count"] >= minimum
        assert payload["parameter_count"] > 0
        assert len(payload["blocks"]) == payload["block_count"]


def test_rejects_unknown_explorer_model() -> None:
    response = client.get("/api/explorer/invented-model")
    assert response.status_code == 404
