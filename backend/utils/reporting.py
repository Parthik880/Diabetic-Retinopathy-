"""Offline RetinaGram PDF and inference bundle export."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from typing import Any

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


GRADE_LABELS = {
    0: "No diabetic retinopathy",
    1: "Mild NPDR",
    2: "Moderate NPDR",
    3: "Severe NPDR",
    4: "Proliferative DR",
}

RECOMMENDATIONS = {
    0: "No signs of diabetic retinopathy were identified by the screening system. Routine ophthalmic screening is recommended.",
    1: "Features consistent with mild diabetic retinopathy were identified. Ophthalmic follow-up is recommended.",
    2: "Features consistent with moderate diabetic retinopathy were identified. Ophthalmologist evaluation and follow-up are recommended.",
    3: "Features requiring prompt ophthalmic evaluation were identified. Referral to an ophthalmologist is recommended.",
    4: "Features requiring prompt ophthalmic evaluation were identified. Referral to an ophthalmologist is recommended.",
}

LESION_NAMES = {
    "MA": "Microaneurysms",
    "HE": "Hemorrhages",
    "EX": "Hard Exudates",
    "SE": "Soft Exudates",
}

MASK_FILENAMES = {
    "MA": "microaneurysm.png",
    "HE": "hemorrhage.png",
    "EX": "hard_exudate.png",
    "SE": "soft_exudate.png",
}


def sanitize_windows_name(value: str, fallback: str = "Patient") -> str:
    """Return a readable Windows-safe path component."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(value or ""))
    cleaned = re.sub(r"\s+", "", cleaned).strip(" .")
    cleaned = cleaned[:64].strip(" .")
    return cleaned or fallback


def _local_artifact(run_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    prefix = f"/artifacts/{run_dir.name}/"
    if not value.startswith(prefix):
        return None
    candidate = (run_dir / value[len(prefix):]).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _unique_report_directory(destination: Path, patient_name: str, generated_at: datetime) -> Path:
    base = f"RetinaGram_{sanitize_windows_name(patient_name)}_{generated_at.strftime('%Y%m%d_%H%M%S')}"
    candidate = destination / base
    suffix = 2
    while candidate.exists():
        candidate = destination / f"{base}_{suffix}"
        suffix += 1
    candidate.mkdir()
    return candidate


def create_report_root(destination: Path, patient_name: str, generated_at: datetime | None = None) -> Path:
    destination = destination.expanduser().resolve()
    if not destination.is_dir():
        raise ValueError("The selected report destination is not an existing folder.")
    return _unique_report_directory(destination, patient_name, generated_at or datetime.now().astimezone())


def _draw_fit_image(pdf: canvas.Canvas, image_path: Path | None, x: float, y: float, width: float, height: float) -> None:
    pdf.setStrokeColor(HexColor("#CBD9CF"))
    pdf.setLineWidth(0.7)
    pdf.roundRect(x, y, width, height, 6, stroke=1, fill=0)
    if image_path is None:
        pdf.setFillColor(HexColor("#64736A"))
        pdf.setFont("Helvetica", 8)
        pdf.drawCentredString(x + width / 2, y + height / 2, "Image unavailable")
        return
    reader = ImageReader(str(image_path))
    source_width, source_height = reader.getSize()
    scale = min((width - 8) / source_width, (height - 8) / source_height)
    draw_width, draw_height = source_width * scale, source_height * scale
    pdf.drawImage(
        reader,
        x + (width - draw_width) / 2,
        y + (height - draw_height) / 2,
        draw_width,
        draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )


def _wrapped_lines(pdf: canvas.Canvas, text: str, font: str, size: float, max_width: float) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and pdf.stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_label_value(pdf: canvas.Canvas, x: float, y: float, label: str, value: Any, width: float) -> float:
    if value in (None, ""):
        return y
    pdf.setFillColor(HexColor("#64736A"))
    pdf.setFont("Helvetica", 6.8)
    pdf.drawString(x, y, label.upper())
    pdf.setFillColor(HexColor("#142018"))
    pdf.setFont("Helvetica-Bold", 8.2)
    rendered = str(value)
    while pdf.stringWidth(rendered, "Helvetica-Bold", 8.2) > width and len(rendered) > 8:
        rendered = rendered[:-2] + "..."
    pdf.drawString(x, y - 11, rendered)
    return y - 24


def build_report_pdf(
    output_path: Path,
    *,
    logo_path: Path,
    original_path: Path | None,
    restored_path: Path | None,
    overlay_path: Path | None,
    patient: dict[str, Any],
    result: dict[str, Any],
    generated_at: datetime,
) -> None:
    """Build a single-page A4 screening report without HTML rendering."""
    width, _height = A4
    pdf = canvas.Canvas(str(output_path), pagesize=A4, pageCompression=1)
    pdf.setTitle(f"RetinaGram screening report {result.get('run_id', '')}")
    pdf.setAuthor("RetinaGram")

    green = HexColor("#075B35")
    green_soft = HexColor("#EAF5EE")
    ink = HexColor("#142018")
    muted = HexColor("#64736A")
    line = HexColor("#CBD9CF")
    amber = HexColor("#A06400")

    pdf.setFillColor(HexColor("#F7FBF8"))
    pdf.roundRect(30, 759, width - 60, 55, 8, stroke=0, fill=1)
    if logo_path.is_file():
        pdf.drawImage(ImageReader(str(logo_path)), 38, 766, 40, 40, preserveAspectRatio=True, mask="auto")
    pdf.setFillColor(green)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(86, 790, "RetinaGram")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(86, 777, "AI Retinal Screening")
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawRightString(width - 40, 793, "Diabetic Retinopathy")
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(width - 40, 777, "Screening Report")

    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(34, 740, "Patient information")
    pdf.setStrokeColor(line)
    pdf.line(34, 734, width - 34, 734)
    left_items = [
        ("Patient name", patient.get("name")),
        ("Patient ID", patient.get("id")),
        ("Age / gender", " / ".join(str(value) for value in (patient.get("age"), patient.get("gender")) if value not in (None, ""))),
        ("Date and time of scan", patient.get("scan_datetime")),
    ]
    right_items = [
        ("Referring doctor", patient.get("referring_doctor")),
        ("Device", result.get("device_name") or result.get("device")),
        ("Image eye", "Left (OS)" if patient.get("eye") == "OS" else "Right (OD)" if patient.get("eye") == "OD" else patient.get("eye")),
        ("Report ID", result.get("run_id")),
    ]
    for column_x, items in ((38, left_items), (315, right_items)):
        row_y = 724
        for label, value in items:
            if value not in (None, ""):
                row_y = _draw_label_value(pdf, column_x, row_y, label, value, 235)

    analysis_top = 620
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(34, analysis_top, "Main analysis")
    image_y, image_h = 390, 209
    image_count = 3 if restored_path else 2
    gap = 8
    grade_w = 125
    image_w = (width - 68 - grade_w - gap * image_count) / image_count
    left_x = 34
    center_x = left_x + image_w + gap
    overlay_x = center_x + image_w + gap if restored_path else center_x
    grade_x = overlay_x + image_w + gap
    grade_w = width - 34 - grade_x
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica-Bold", 7.3)
    pdf.drawString(left_x, 606, "ORIGINAL FUNDUS IMAGE")
    if restored_path:
        pdf.drawString(center_x, 606, "RESTORED FUNDUS IMAGE")
    pdf.drawString(overlay_x, 606, "AI ANALYSIS / LESION OVERLAY")
    _draw_fit_image(pdf, original_path, left_x, image_y, image_w, image_h)
    if restored_path:
        _draw_fit_image(pdf, restored_path, center_x, image_y, image_w, image_h)
    _draw_fit_image(pdf, overlay_path, overlay_x, image_y, image_w, image_h)

    grading = result.get("grading") or {}
    grade = grading.get("predicted_grade")
    label = GRADE_LABELS.get(grade, "Unavailable")
    confidence = grading.get("confidence")
    pdf.setFillColor(green_soft)
    pdf.roundRect(grade_x, image_y, grade_w, image_h + 14, 8, stroke=0, fill=1)
    pdf.setFillColor(green)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(grade_x + 13, 581, "DR GRADE")
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 15)
    label_lines = _wrapped_lines(pdf, label, "Helvetica-Bold", 15, grade_w - 26)[:2]
    for index, line_text in enumerate(label_lines):
        pdf.drawString(grade_x + 13, 552 - index * 17, line_text)
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(muted)
    pdf.drawString(grade_x + 13, 512, f"Grade {grade}" if grade is not None else "Grade unavailable")
    pdf.setStrokeColor(HexColor("#B8D7C3"))
    pdf.line(grade_x + 13, 493, grade_x + grade_w - 13, 493)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(grade_x + 13, 477, "CONFIDENCE")
    pdf.setFillColor(green)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(grade_x + 13, 449, f"{confidence * 100:.1f}%" if isinstance(confidence, (int, float)) else "Unavailable")

    section_y, section_h = 265, 105
    lesions_data = (result.get("lesions") or {}).get("lesions") or {}
    pdf.setFillColor(white)
    pdf.setStrokeColor(line)
    pdf.roundRect(34, section_y, 325, section_h, 7, stroke=1, fill=1)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(46, 350, "Lesion detection")
    for index, code in enumerate(("MA", "HE", "EX", "SE")):
        item = lesions_data.get(code)
        value = "Detected" if item and item.get("detected") else "Not detected" if item else "Unavailable"
        row_x = 46 + (index % 2) * 154
        row_y = 325 - (index // 2) * 33
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 7.2)
        pdf.drawString(row_x, row_y + 10, LESION_NAMES[code])
        pdf.setFillColor(green if value == "Detected" else ink)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(row_x, row_y - 1, value)

    quality = result.get("quality") or {}
    source_quality = quality.get("quality")
    display_quality = {"Good": "Good", "Usable": "Usable", "Reject": "Poor - Recapture recommended"}.get(source_quality, "Unavailable")
    pdf.setFillColor(green_soft if source_quality != "Reject" else HexColor("#FFF1E5"))
    pdf.setStrokeColor(line)
    pdf.roundRect(369, section_y, width - 403, section_h, 7, stroke=1, fill=1)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(381, 350, "Image quality")
    pdf.setFillColor(green if source_quality in ("Good", "Usable") else amber)
    pdf.setFont("Helvetica-Bold", 12)
    for index, line_text in enumerate(_wrapped_lines(pdf, display_quality, "Helvetica-Bold", 12, width - 427)[:2]):
        pdf.drawString(381, 324 - index * 14, line_text)
    quality_note = (
        "Image is of sufficient quality for reliable screening analysis."
        if source_quality == "Good"
        else "Image is usable for screening; clinician review remains required."
        if source_quality == "Usable"
        else "Image quality may limit analysis. Recapture is recommended."
        if source_quality == "Reject"
        else "Image quality assessment is unavailable."
    )
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7.2)
    note_y = 290
    for line_text in _wrapped_lines(pdf, quality_note, "Helvetica", 7.2, width - 427)[:3]:
        pdf.drawString(381, note_y, line_text)
        note_y -= 9

    recommendation = RECOMMENDATIONS.get(grade, "A screening recommendation is unavailable because DR grading did not complete.")
    pdf.setFillColor(HexColor("#F7FBF8"))
    pdf.roundRect(34, 145, width - 68, 100, 7, stroke=0, fill=1)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(46, 222, "Screening recommendation")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8.4)
    recommendation_y = 202
    for line_text in _wrapped_lines(pdf, recommendation, "Helvetica", 8.4, width - 92)[:3]:
        pdf.drawString(46, recommendation_y, line_text)
        recommendation_y -= 11

    pdf.setStrokeColor(line)
    pdf.line(34, 55, width - 34, 55)
    disclaimer = "This report is generated by an AI-assisted retinal screening system and is not a substitute for professional medical diagnosis."
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawString(34, 39, disclaimer)
    pdf.drawRightString(width - 34, 25, "Page 1 of 1")
    pdf.setFillColor(HexColor("#87968D"))
    pdf.drawString(34, 25, f"Generated locally {generated_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")

    pdf.showPage()
    pdf.save()


def export_report_bundle(
    destination: Path,
    *,
    run_dir: Path,
    patient: dict[str, Any],
    logo_path: Path,
    report_root: Path | None = None,
) -> dict[str, Any]:
    """Create a patient-specific report directory from one completed inference run."""
    destination = destination.expanduser().resolve()
    if not destination.is_dir():
        raise ValueError("The selected report destination is not an existing folder.")
    response_path = run_dir / "response.json"
    if not response_path.is_file():
        raise ValueError("The selected inference run is unavailable.")
    result = json.loads(response_path.read_text(encoding="utf-8"))
    generated_at = datetime.now().astimezone()
    root_dir = report_root or _unique_report_directory(destination, str(patient.get("name") or ""), generated_at)
    eye = str(patient.get("eye") or "")
    eye_folder = "Left_OS" if eye == "OS" else "Right_OD" if eye == "OD" else "Eye"
    report_dir = root_dir / eye_folder
    report_dir.mkdir(parents=True, exist_ok=False)

    original_source = _local_artifact(run_dir, result.get("original_image_url") or result.get("image_url"))
    restored_source = _local_artifact(run_dir, result.get("restored_image_url"))
    overlay_source = _local_artifact(run_dir, (result.get("lesions") or {}).get("combined_overlay_path"))
    original_output: Path | None = None
    restored_output: Path | None = None
    overlay_output: Path | None = None
    if original_source:
        original_output = report_dir / "original_fundus.jpg"
        with Image.open(original_source) as image:
            image.convert("RGB").save(original_output, "JPEG", quality=95, optimize=True)
    if restored_source:
        restored_output = report_dir / "restored_fundus.png"
        shutil.copy2(restored_source, restored_output)
    if overlay_source:
        overlay_output = report_dir / "lesion_overlay.png"
        shutil.copy2(overlay_source, overlay_output)

    exported_masks: dict[str, str] = {}
    lesions_data = (result.get("lesions") or {}).get("lesions") or {}
    for code, filename in MASK_FILENAMES.items():
        source = _local_artifact(run_dir, (lesions_data.get(code) or {}).get("mask_png_path"))
        if source:
            mask_dir = report_dir / "masks"
            mask_dir.mkdir(exist_ok=True)
            target = mask_dir / filename
            shutil.copy2(source, target)
            exported_masks[code] = f"masks/{filename}"

    structured_lesions = {}
    for code, name in LESION_NAMES.items():
        item = lesions_data.get(code)
        if not item:
            continue
        structured_lesions[code] = {
            "label": name,
            "detected": bool(item.get("detected")),
            "region_count": item.get("num_regions"),
            "mask_file": exported_masks.get(code),
        }

    quality = result.get("quality") or None
    grading = result.get("grading") or None
    structured = {
        "report_id": result.get("run_id"),
        "patient": {key: value for key, value in {
            "name": patient.get("name"),
            "id": patient.get("id"),
            "age": patient.get("age"),
            "gender": patient.get("gender"),
            "eye": patient.get("eye"),
            "scan_datetime": patient.get("scan_datetime"),
            "referring_doctor": patient.get("referring_doctor"),
        }.items() if value not in (None, "")},
        "image_quality": None if not quality else {
            "class": quality.get("quality"),
            "confidence": quality.get("confidence"),
            "probabilities": quality.get("probabilities"),
        },
        "dr_grading": None if not grading else {
            "grade": grading.get("predicted_grade"),
            "label": GRADE_LABELS.get(grading.get("predicted_grade")),
            "confidence": grading.get("confidence"),
            "probabilities": grading.get("probabilities"),
        },
        "lesions": structured_lesions,
        "inference_device": result.get("device_name") or result.get("device"),
        "pipeline_state": result.get("state"),
        "analysis_source": result.get("analysis_source"),
        "original_image_file": "original_fundus.jpg" if original_output else None,
        "restored_image_file": "restored_fundus.png" if restored_output else None,
        "generated_at": generated_at.isoformat(),
    }
    (report_dir / "results.json").write_text(
        json.dumps(structured, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    report_path = report_dir / "report.pdf"
    build_report_pdf(
        report_path,
        logo_path=logo_path,
        original_path=original_output,
        restored_path=restored_output,
        overlay_path=overlay_output,
        patient=structured["patient"],
        result=result,
        generated_at=generated_at,
    )
    return {
        "folder": str(root_dir),
        "eye_folder": str(report_dir),
        "report": str(report_path),
        "files": sorted(str(path.relative_to(root_dir)).replace("\\", "/") for path in root_dir.rglob("*") if path.is_file()),
    }
