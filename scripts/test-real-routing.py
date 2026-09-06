"""Checkpoint-backed GOOD/USABLE/RECAPTURE routing and queue verification."""

from io import BytesIO
import json
from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app


def png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


with Image.open(ROOT / "resources/test-images/20170629163635747.jpg") as source:
    base = source.convert("RGB").resize((256, 256))
inputs = {
    "GOOD": ImageEnhance.Brightness(base).enhance(0.5),
    "USABLE": ImageEnhance.Brightness(base).enhance(0.35),
    "RECAPTURE": ImageEnhance.Brightness(base).enhance(0.02),
}
input_dir = ROOT / "work" / "routing-test-inputs"
input_dir.mkdir(parents=True, exist_ok=True)
for name, image in inputs.items():
    image.save(input_dir / f"{name.lower()}.png")

with TestClient(app) as client:
    jobs = {}
    # Submit all images before polling. The bounded worker leaves later jobs in
    # WAITING until their own isolated run begins.
    for expected, image in inputs.items():
        response = client.post(
            "/api/analysis-jobs",
            files={"file": (f"{expected.lower()}.png", png_bytes(image), "image/png")},
            data={"eye": "OS"},
        )
        assert response.status_code == 202, response.text
        jobs[expected] = response.json()["job_id"]
    assert len(set(jobs.values())) == 3

    deadline = time.monotonic() + 180
    snapshots = {}
    while time.monotonic() < deadline:
        snapshots = {name: client.get(f"/api/analysis-jobs/{job_id}").json() for name, job_id in jobs.items()}
        if all(item["state"] in ("COMPLETE", "RECAPTURE_REQUIRED", "FAILED") for item in snapshots.values()):
            break
        time.sleep(0.1)

    good = snapshots["GOOD"]["result"]
    usable = snapshots["USABLE"]["result"]
    recapture = snapshots["RECAPTURE"]["result"]
    assert snapshots["GOOD"]["state"] == "COMPLETE", snapshots["GOOD"]
    assert snapshots["USABLE"]["state"] == "COMPLETE", snapshots["USABLE"]
    assert snapshots["RECAPTURE"]["state"] == "RECAPTURE_REQUIRED", snapshots["RECAPTURE"]

    assert good["quality"]["normalized_quality"] == "GOOD"
    assert good["invocation_counts"] == {"iqa": 1, "nafnet": 0, "grading": 1, "lesions": 1}
    assert good["analysis_source"] == "original" and good["restored_image_url"] is None
    assert good["grading"]["image_path"] == good["analysis_image_url"]
    assert good["lesions"]["image"] == good["analysis_image_url"]

    assert usable["quality"]["normalized_quality"] == "USABLE"
    assert usable["invocation_counts"] == {"iqa": 1, "nafnet": 1, "grading": 1, "lesions": 1}
    assert usable["analysis_source"] == "restored"
    assert usable["original_image_url"] != usable["restored_image_url"] == usable["analysis_image_url"]
    assert usable["grading"]["image_path"] == usable["analysis_image_url"]
    assert usable["lesions"]["image"] == usable["analysis_image_url"]
    assert client.get(usable["original_image_url"]).status_code == 200
    assert client.get(usable["restored_image_url"]).status_code == 200
    report_destination = ROOT / "work" / "test-routing-reports"
    report_destination.mkdir(exist_ok=True)
    exported = client.post("/api/reports/export", json={
        "destination": str(report_destination),
        "run_id": usable["run_id"],
        "patient": {"name": "Usable Routing Test", "id": "ROUTING-TEST", "eye": "OS"},
    })
    assert exported.status_code == 200, exported.text
    exported_files = set(exported.json()["files"])
    assert {"original_fundus.jpg", "restored_fundus.png", "report.pdf", "results.json"} <= exported_files

    assert recapture["quality"]["normalized_quality"] == "RECAPTURE"
    assert recapture["invocation_counts"] == {"iqa": 1, "nafnet": 0, "grading": 0, "lesions": 0}
    assert recapture["grading"] is None and recapture["lesions"] is None

    summary = {
        name: {
            "job_id": jobs[name],
            "quality": snapshots[name]["result"]["quality"],
            "state": snapshots[name]["state"],
            "state_history": [item["state"] for item in snapshots[name]["state_history"]],
            "invocation_counts": snapshots[name]["result"]["invocation_counts"],
            "analysis_source": snapshots[name]["result"]["analysis_source"],
            "original_image_url": snapshots[name]["result"]["original_image_url"],
            "restored_image_url": snapshots[name]["result"]["restored_image_url"],
            "report_files": sorted(exported_files) if name == "USABLE" else None,
        }
        for name in inputs
    }
    output = ROOT / "work" / "real-routing-test.json"
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
