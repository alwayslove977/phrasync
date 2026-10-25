from __future__ import annotations

import fnmatch
import threading
import time
from pathlib import Path
from typing import Any, Callable


MODEL_REPOSITORIES = {
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "tiny": "Systran/faster-whisper-tiny",
    "base.en": "Systran/faster-whisper-base.en",
    "base": "Systran/faster-whisper-base",
    "small.en": "Systran/faster-whisper-small.en",
    "small": "Systran/faster-whisper-small",
    "medium.en": "Systran/faster-whisper-medium.en",
    "medium": "Systran/faster-whisper-medium",
    "large-v1": "Systran/faster-whisper-large-v1",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large": "Systran/faster-whisper-large-v3",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

MODEL_SIZE_ESTIMATES = {
    "tiny": 80_000_000,
    "tiny.en": 80_000_000,
    "base": 150_000_000,
    "base.en": 150_000_000,
    "small": 490_000_000,
    "small.en": 490_000_000,
    "medium": 1_550_000_000,
    "medium.en": 1_550_000_000,
    "large": 3_100_000_000,
    "large-v1": 3_100_000_000,
    "large-v2": 3_100_000_000,
    "large-v3": 3_100_000_000,
    "distil-large-v3": 1_550_000_000,
    "large-v3-turbo": 1_650_000_000,
    "turbo": 1_650_000_000,
}

_ALLOWED = ("config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*")


def model_path(root: Path, model_name: str) -> Path:
    safe = model_name.replace("/", "--").replace("\\", "--")
    return root / safe


def model_is_ready(path: Path) -> bool:
    return (path / "config.json").is_file() and (path / "model.bin").is_file()


def bundled_model(root: Path, model_name: str) -> Path | None:
    """Find a model shipped inside the application bundle.

    The folder inside the bundle can be named after the short alias (``tiny``),
    after the Hugging Face repository (``Systran--faster-whisper-tiny``) or with
    a ``whisper-`` prefix, so all of those are probed before giving up and
    falling back to a download.
    """
    name = (model_name or "").strip()
    if not name:
        return None
    repository = MODEL_REPOSITORIES.get(name, name)
    candidates = [name, repository, f"whisper-{name}"]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        folder = model_path(root, candidate)
        if model_is_ready(folder):
            return folder
    return None


def downloaded_bytes(path: Path) -> int:
    """Return payload file sizes for cache diagnostics, not transfer progress.

    ``huggingface_hub`` stores active local-directory downloads below
    ``.cache/huggingface/download`` with an ``.incomplete`` suffix.  Those are
    the large payload files, while the other cache entries are only locks and
    metadata. Xet may buffer writes or preallocate files, so these sizes must
    never drive the live download percentage; use Hub byte callbacks instead.
    """
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        in_cache = ".cache" in item.parts
        if in_cache and not item.name.endswith(".incomplete"):
            continue
        try:
            total += item.stat().st_size
        except OSError:
            pass
    return total


def repository_id(model_name: str) -> str:
    if "/" in model_name:
        return model_name
    try:
        return MODEL_REPOSITORIES[model_name]
    except KeyError as exc:
        raise ValueError(f"Unknown Whisper model: {model_name}") from exc


def remote_model_size(model_name: str) -> int:
    """Read the real download size, falling back to a conservative estimate."""
    fallback = MODEL_SIZE_ESTIMATES.get(model_name, 0)
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repository_id(model_name), files_metadata=True)
        sizes = []
        for sibling in info.siblings or []:
            name = str(getattr(sibling, "rfilename", ""))
            if any(fnmatch.fnmatch(name, pattern) for pattern in _ALLOWED):
                sizes.append(int(getattr(sibling, "size", 0) or 0))
        return sum(sizes) or fallback
    except Exception:
        return fallback


def _format_bytes(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f} GB"
    return f"{value / 1_000_000:.0f} MB"


def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "estimating time remaining"
    minutes, remainder = divmod(int(round(seconds)), 60)
    if minutes:
        return f"about {minutes} min remaining"
    return f"about {max(1, remainder)} sec remaining"


def _byte_progress():
    """Collect Hub byte callbacks even without a terminal/progress-bar display.

    Xet receives data before flushing/reconstructing local payloads, so file
    size cannot measure this transfer. Never add transfer to reconstruction:
    these counters describe two stages of the same data.
    """
    from tqdm.auto import tqdm

    lock = threading.Lock()
    values = {"transfer": 0, "reconstruction": 0}

    class ByteProgress(tqdm):
        def __init__(self, *args, **kwargs):
            description = str(kwargs.get("desc", "")).lower()
            self.counter = ("transfer" if "downloading bytes" in description else "reconstruction") if kwargs.get("unit") == "B" else None
            kwargs.pop("name", None)
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)
            if self.counter:
                with lock:
                    values[self.counter] += int(kwargs.get("initial", 0) or 0)

        def update(self, n=1):
            # tqdm skips counter updates when disable=True. GUI reporting must
            # remain active independently of stdout/stderr or HF display flags.
            amount = int(n or 0)
            self.n += amount
            if self.counter:
                with lock:
                    values[self.counter] += amount

    def snapshot():
        with lock:
            return dict(values)

    return ByteProgress, snapshot


def ensure_model(
    model_name: str,
    root: Path,
    *,
    progress: Callable[..., None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    bundled_root: Path | None = None,
) -> Path:
    """Download a model once while reporting bytes, percentage, speed and ETA.

    A model that ships inside the application bundle is used in place, so the
    packaged app can transcribe offline without touching the network.
    """
    if bundled_root is not None:
        bundled = bundled_model(bundled_root, model_name)
        if bundled is not None:
            if progress:
                progress(0.13, f"Loading bundled Whisper {model_name}…", {
                    "phase": "model-load",
                    "downloadedBytes": downloaded_bytes(bundled),
                    "totalBytes": downloaded_bytes(bundled),
                    "etaSeconds": None,
                })
            return bundled

    target = model_path(root, model_name)
    if model_is_ready(target):
        return target

    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0.01, f"Checking Whisper {model_name} download…", {
            "phase": "model-download", "downloadedBytes": 0,
            "totalBytes": None, "etaSeconds": None,
        })
    expected = 0
    result: dict[str, Any] = {}
    failure: list[BaseException] = []
    progress_class, byte_snapshot = _byte_progress()
    completed_before = sum(item.stat().st_size for item in target.iterdir()
                           if item.is_file() and any(fnmatch.fnmatch(item.name, pattern) for pattern in _ALLOWED))

    def download() -> None:
        nonlocal expected
        try:
            expected = remote_model_size(model_name)
            result["metadataReady"] = True
            result["path"] = snapshot_download(repository_id(model_name), local_dir=str(target),
                                                allow_patterns=list(_ALLOWED), tqdm_class=progress_class)
        except BaseException as exc:  # handed back to the transcription worker
            failure.append(exc)

    worker = threading.Thread(target=download, name=f"phrasync-download-{model_name}", daemon=True)
    worker.start()
    last_bytes = 0
    last_report = 0.0
    samples: list[tuple[float, int]] = []
    while worker.is_alive():
        current_time = time.monotonic()
        counters = byte_snapshot()
        # Network/reconstruction can differ due to compression and Xet cache
        # reuse; use the furthest observed stage, not their (double-counted) sum.
        # Previously present files may be downloaded again if their Hub
        # metadata is missing/stale. Adding them would double-count those
        # bytes. Keep a conservative monotonic lower bound until completion.
        measured_bytes = max(completed_before, last_bytes, *counters.values())
        current_bytes = min(measured_bytes, expected) if expected else measured_bytes
        samples.append((current_time, current_bytes))
        samples = [sample for sample in samples if current_time - sample[0] <= 12]
        speed = 0.0
        if len(samples) > 1 and samples[-1][0] > samples[0][0]:
            speed = max(0.0, (samples[-1][1] - samples[0][1]) / (samples[-1][0] - samples[0][0]))
        eta = (expected - current_bytes) / speed if expected > current_bytes and speed > 1024 else None
        ratio = min(0.99, current_bytes / expected) if expected else 0.0
        if progress and (current_bytes != last_bytes or current_time - last_report >= 1):
            message = (
                f"Downloading Whisper {model_name}: {round(ratio * 100)}% · "
                f"{_format_bytes(current_bytes)} / {_format_bytes(expected)} · {_format_eta(eta)}"
                if expected
                else f"Downloading Whisper {model_name}: {_format_bytes(current_bytes)} · estimating size"
            )
            if not result.get("metadataReady"):
                message = f"Checking Whisper {model_name} download…"
            progress(
                0.01 + ratio * 0.11,
                message,
                {
                    "phase": "model-download",
                    "downloadedBytes": current_bytes,
                    "totalBytes": expected or None,
                    "etaSeconds": round(eta) if eta is not None else None,
                    "transferredBytes": counters["transfer"],
                    "reconstructedBytes": counters["reconstruction"],
                },
            )
            last_report = current_time
        last_bytes = current_bytes
        if cancel_check and cancel_check():
            # huggingface_hub has no cooperative cancellation hook. The worker
            # is allowed to finish the current file so the cache is not corrupt;
            # the transcription itself is cancelled immediately afterwards.
            pass
        worker.join(timeout=0.5)

    if failure:
        raise failure[0]
    if not model_is_ready(target):
        raise RuntimeError(f"Whisper {model_name} download did not produce a complete model")
    if progress:
        progress(
            0.13,
            f"Whisper {model_name} downloaded. Loading model…",
            {
                "phase": "model-load",
                "downloadedBytes": expected or downloaded_bytes(target),
                "totalBytes": expected or downloaded_bytes(target),
                "etaSeconds": None,
            },
        )
    return Path(result.get("path") or target)
