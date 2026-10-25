from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import JOBS_DIR, RENDERS_DIR, discard
from .diagnostics import log_event, log_exception
from .align import align_cues, alignment_stats
from .audio_analysis import analyze_audio
from .qa import postflight_render, preflight_project
from .renderer import render_project
from .transcribe import TranscriptionCancelled, transcribe_audio


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_title(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return cleaned[:64] or "phrasync_export"


@dataclass
class Job:
    id: str
    kind: str
    state: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    result: dict[str, Any] | None = None
    error: str | None = None
    traceback: str | None = None
    preflight: dict[str, Any] | None = None
    postflight: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    cancel_requested: bool = False
    phase: str | None = None
    downloaded_bytes: int | None = None
    transferred_bytes: int | None = None
    reconstructed_bytes: int | None = None
    total_bytes: int | None = None
    eta_seconds: int | None = None
    device: str | None = None

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("traceback", None)
        return data


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phrasync-job")

    def _save(self, job: Job) -> None:
        job.updated_at = _utc_now()
        (JOBS_DIR / f"{job.id}.json").write_text(
            json.dumps(job.public(), indent=2), encoding="utf-8"
        )

    def create_render(self, project: dict[str, Any], title: str = "phrasync_export", output_dir: Path | None = None) -> Job:
        if output_dir is None or not output_dir.is_dir():
            raise ValueError("Choose an export folder before starting a render")
        job = Job(id=uuid.uuid4().hex, kind="render")
        log_event("info", "render", f"Queued job {job.id[:8]}")
        with self.lock:
            self.jobs[job.id] = job
            self._save(job)
        self.executor.submit(self._run_render, job.id, project, title, output_dir)
        return job

    def create_transcription(
        self,
        path: Path,
        model: str,
        language: str,
        vad_filter: bool,
        align: bool = True,
        language_spans: list[dict[str, Any]] | None = None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            kind="transcription",
            message="Waiting to transcribe",
            request={
                "model": model,
                "language": language or "auto",
                "task": "transcribe",
                "vadFilter": bool(vad_filter),
                "align": bool(align),
                "languageSpans": list(language_spans or []),
            },
        )
        log_event("info", "transcription", f"Queued job {job.id[:8]}, model {model}, language {language}")
        with self.lock:
            self.jobs[job.id] = job
            self._save(job)
        self.executor.submit(
            self._run_transcription,
            job.id,
            path,
            model,
            language,
            vad_filter,
            align,
            language_spans,
        )
        return job

    def _run_transcription(
        self,
        job_id: str,
        path: Path,
        model: str,
        language: str,
        vad_filter: bool,
        align: bool,
        language_spans: list[dict[str, Any]] | None = None,
    ) -> None:
        job = self.get(job_id)
        if not job:
            return

        def cancelled() -> bool:
            with self.lock:
                return job.cancel_requested

        def update(value: float, message: str, details: dict[str, Any] | None = None) -> None:
            with self.lock:
                job.progress = max(job.progress, min(0.84, 0.04 + float(value) * 0.80))
                job.message = message
                if details:
                    if "phase" in details:
                        job.phase = details["phase"]
                    if "downloadedBytes" in details:
                        job.downloaded_bytes = details["downloadedBytes"]
                    if "transferredBytes" in details:
                        job.transferred_bytes = details["transferredBytes"]
                    if "reconstructedBytes" in details:
                        job.reconstructed_bytes = details["reconstructedBytes"]
                    if "totalBytes" in details:
                        job.total_bytes = details["totalBytes"]
                    if "etaSeconds" in details:
                        job.eta_seconds = details["etaSeconds"]
                    if "device" in details:
                        job.device = details["device"]
                elif job.phase in {"model-download", "model-load"}:
                    job.phase = "transcribing"
                    job.eta_seconds = None
                self._save(job)

        try:
            if cancelled():
                raise TranscriptionCancelled("Transcription cancelled")
            with self.lock:
                job.state = "running"
                job.progress = 0.02
                job.message = f"Loading Whisper {model}"
                self._save(job)

            result = transcribe_audio(
                path,
                model,
                language,
                vad_filter,
                progress=update,
                cancel_check=cancelled,
                language_spans=language_spans,
            )
            if cancelled():
                raise TranscriptionCancelled("Transcription cancelled")

            if align:
                with self.lock:
                    job.progress = 0.88
                    job.message = "Analysing audio for alignment"
                    job.phase = "aligning"
                    self._save(job)
                analysis = analyze_audio(path, True)
                if cancelled():
                    raise TranscriptionCancelled("Transcription cancelled")
                aligned = align_cues(result["cues"], analysis)
                result["cues"] = aligned["cues"]
                result["alignment"] = aligned["report"]
                result["alignmentStats"] = alignment_stats(aligned["cues"], analysis)

            with self.lock:
                job.result = result
                job.state = "complete"
                job.progress = 1.0
                job.message = "Transcription complete"
                job.phase = "complete"
                self._save(job)
            log_event("info", "transcription", f"Completed job {job.id[:8]} on {job.device or 'unknown device'}")
        except TranscriptionCancelled:
            with self.lock:
                job.state = "cancelled"
                job.message = "Transcription cancelled"
                job.error = None
                self._save(job)
        except Exception as exc:
            log_exception("transcription", exc)
            with self.lock:
                job.state = "cancelled" if job.cancel_requested else "failed"
                job.error = None if job.cancel_requested else str(exc)
                job.traceback = traceback.format_exc()
                job.message = "Transcription cancelled" if job.cancel_requested else "Transcription failed"
                self._save(job)

    def _run_render(self, job_id: str, project: dict[str, Any], title: str, output_dir: Path) -> None:
        job = self.get(job_id)
        if not job:
            return
        output_path = None
        output_reserved = False
        try:
            report = preflight_project(project)
            with self.lock:
                job.preflight = report.public()
                if not report.ok:
                    job.state = "failed"
                    job.error = "Preflight critic found blocking errors."
                    job.progress = 1.0
                    job.message = "Preflight failed"
                    self._save(job)
                    log_event("error", "render", f"Job {job.id[:8]} failed preflight")
                    return
                job.state = "running"
                job.progress = 0.01
                job.message = "Starting renderer"
                self._save(job)

            base = _safe_title(title)
            index = 1
            while True:
                output_name = f"{base}{f' ({index})' if index > 1 else ''}.mp4"
                output_path = output_dir / output_name
                try:
                    with output_path.open("xb"):
                        pass
                    output_reserved = True
                    break
                except FileExistsError:
                    index += 1

            def update(value: float, message: str) -> None:
                with self.lock:
                    job.progress = max(job.progress, min(1.0, float(value)))
                    job.message = message
                    self._save(job)

            def cancelled() -> bool:
                with self.lock:
                    return job.cancel_requested

            result = render_project(project, output_path, progress=update, cancel_check=cancelled)
            postflight = postflight_render(output_path, expected_duration=result.get("duration"))
            result["filename"] = output_name
            result["downloadUrl"] = f"/api/render/{job.id}/download"
            with self.lock:
                job.result = result
                job.postflight = postflight.public()
                job.progress = 1.0
                if postflight.ok:
                    job.state = "complete"
                    job.message = "Render complete"
                else:
                    job.state = "failed"
                    job.error = "Post-render critic found a blocking error."
                    job.message = "Postflight failed"
                self._save(job)
            log_event("info" if postflight.ok else "error", "render", f"Job {job.id[:8]} {'complete' if postflight.ok else 'failed postflight'}")
        except Exception as exc:
            if output_reserved and output_path is not None and output_path.exists() and output_path.stat().st_size == 0:
                discard(output_path)  # cleanup must not mask the real error
            log_exception("render", exc)
            with self.lock:
                job.state = "cancelled" if job.cancel_requested else "failed"
                job.error = str(exc)
                job.traceback = traceback.format_exc()
                job.progress = 1.0
                job.message = "Cancelled" if job.cancel_requested else "Render failed"
                self._save(job)

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.state not in {"queued", "running"}:
                return False
            job.cancel_requested = True
            job.message = "Cancellation requested"
            self._save(job)
            return True

    def cancel_all(self, message: str = "Stopping because Phrasync is closing") -> int:
        """Ask every unfinished job to stop; used when the app is shutting down.

        A worker stops at its next checkpoint instead of abandoning the job, so a
        half-written export is removed by the normal failure path rather than
        being left behind under the user's name.
        """
        requested = 0
        with self.lock:
            for job in self.jobs.values():
                if job.state in {"queued", "running"}:
                    job.cancel_requested = True
                    job.message = message
                    self._save(job)
                    requested += 1
        return requested

    def wait_idle(self, timeout: float = 8.0) -> int:
        """Wait for unfinished jobs to stop; return how many are still running."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            with self.lock:
                active = [job for job in self.jobs.values() if job.state in {"queued", "running"}]
            if not active:
                return 0
            if time.monotonic() >= deadline:
                return len(active)
            time.sleep(0.1)

    def shutdown(self) -> None:
        """Retire the worker pool so no idle thread outlives the window.

        ``concurrent.futures`` joins its workers at interpreter exit, so leaving
        the pool alive makes the process depend on those threads finishing.
        """
        self.executor.shutdown(wait=False, cancel_futures=True)

    def output_path(self, job_id: str) -> Path | None:
        job = self.get(job_id)
        if not job or not job.result:
            return None
        path = Path(job.result.get("path", ""))
        return path if path.exists() else None


manager = JobManager()
