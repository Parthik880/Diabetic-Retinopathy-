"""Thread-safe, per-image analysis job state and bounded queue."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Callable

from inference.pipeline import PipelineState, TERMINAL_STATES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisJobManager:
    def __init__(self, max_workers: int = 1):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="retina-analysis")
        self._lock = Lock()
        self._jobs: dict[str, dict] = {}

    def create(self, job_id: str, eye: str | None) -> None:
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "eye": eye,
                "state": PipelineState.WAITING.value,
                "state_history": [{"state": PipelineState.WAITING.value, "at": _now()}],
                "result": None,
                "error": None,
                "updated_at": _now(),
            }

    def transition(self, job_id: str, state: PipelineState) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job["state"] in {item.value for item in TERMINAL_STATES}:
                return
            job["state"] = state.value
            if job["state_history"][-1]["state"] != state.value:
                job["state_history"].append({"state": state.value, "at": _now()})
            job["updated_at"] = _now()

    def complete(self, job_id: str, result: dict) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["state"] = result["state"]
            job["state_history"] = deepcopy(result["state_history"])
            job["result"] = deepcopy(result)
            job["error"] = None
            job["updated_at"] = _now()

    def fail(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job["state"] != PipelineState.FAILED.value:
                job["state"] = PipelineState.FAILED.value
                job["state_history"].append({"state": PipelineState.FAILED.value, "at": _now()})
            job["error"] = message
            job["updated_at"] = _now()

    def submit(self, job_id: str, worker: Callable[[], dict]) -> None:
        def run() -> None:
            try:
                self.complete(job_id, worker())
            except Exception as exc:
                self.fail(job_id, str(exc) or exc.__class__.__name__)

        self._executor.submit(run)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job is not None else None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
