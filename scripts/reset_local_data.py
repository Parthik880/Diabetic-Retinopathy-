"""Reset RetinaGram CPU patient/session data and generated runtime artifacts."""

from __future__ import annotations

import os
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]


def remove_inside_project(path: Path) -> None:
    resolved = path.resolve()
    resolved.relative_to(ROOT.resolve())
    if resolved.exists():
        shutil.rmtree(resolved) if resolved.is_dir() else resolved.unlink()
        print(f"Removed: {resolved}")


def remove_cpu_user_data() -> None:
    app_data = os.environ.get("APPDATA")
    if not app_data:
        return
    target = (Path(app_data) / "RetinaGram CPU").resolve()
    expected_parent = Path(app_data).resolve()
    if target.parent != expected_parent or target.name != "RetinaGram CPU":
        raise RuntimeError(f"Refusing unexpected user-data path: {target}")
    if target.exists():
        shutil.rmtree(target)
        print(f"Removed: {target}")


def main() -> None:
    remove_cpu_user_data()
    remove_inside_project(ROOT / "work")
    remove_inside_project(ROOT / "backend" / "inference" / "outputs")
    for name in ("reports", "results", "history", "sessions", "batch_results", "exports", "temp", "tmp", "cache"):
        remove_inside_project(ROOT / name)
    (ROOT / "work" / "runs").mkdir(parents=True, exist_ok=True)
    print("RetinaGram CPU local data reset complete; models, checkpoints, schema code, and assets were preserved.")


if __name__ == "__main__":
    main()
