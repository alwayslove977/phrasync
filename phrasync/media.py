from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np
from .config import discard, scratch_dir
from .processes import background_flags

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover - surfaced by health endpoint
    imageio_ffmpeg = None

DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def ffmpeg_exe() -> str:
    override = shutil.which("ffmpeg")
    if override:
        return override
    if imageio_ffmpeg is not None:
        return imageio_ffmpeg.get_ffmpeg_exe()
    raise RuntimeError("FFmpeg is unavailable. Install imageio-ffmpeg or FFmpeg.")


def run_ffmpeg(args: list[str], *, check: bool = True, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    command = [ffmpeg_exe(), *args]
    return subprocess.run(
        command,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        creationflags=background_flags(),
    )


def probe_duration(path: Path) -> float | None:
    process = run_ffmpeg(["-hide_banner", "-i", str(path)], check=False)
    text = process.stderr.decode("utf-8", errors="replace")
    match = DURATION_RE.search(text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def decode_audio_mono(path: Path, sample_rate: int = 8000) -> np.ndarray:
    process = run_ffmpeg(
        [
            "-v",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=True,
    )
    if not process.stdout:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(process.stdout, dtype=np.float32).copy()


def audio_envelope(
    path: Path | None,
    duration: float,
    fps: int,
    sample_rate: int = 8000,
    progress: Callable[[float], None] | None = None,
) -> np.ndarray:
    frame_count = max(1, int(round(duration * fps)))
    if path is None:
        return np.zeros(frame_count, dtype=np.float32)
    per_frame = sample_rate / fps
    envelope = np.zeros(frame_count, dtype=np.float32)
    frame_offset = 0
    # Minute boundaries fall on whole video frames, so each bounded audio
    # block can be reduced independently without losing frame alignment.
    blocks = iter_audio_mono(path, sample_rate=sample_rate)
    try:
        for samples in blocks:
            count = min(frame_count - frame_offset, int(np.ceil(samples.size / per_frame)))
            if count <= 0:
                break
            edges = np.minimum(samples.size, np.arange(count + 1, dtype=np.int64) * sample_rate // fps)
            sums = np.concatenate(([0.0], np.cumsum(samples.astype(np.float64) ** 2)))
            lengths = np.diff(edges)
            means = np.divide(sums[edges[1:]] - sums[edges[:-1]], lengths,
                              out=np.zeros(count), where=lengths > 0)
            envelope[frame_offset:frame_offset + count] = np.sqrt(means + 1e-12)
            frame_offset += count
            if progress:
                progress(frame_offset / frame_count)
            if frame_offset >= frame_count:
                break
    finally:
        blocks.close()
    peak = float(np.percentile(envelope, 98)) if envelope.size else 0.0
    if peak > 1e-6:
        envelope = np.clip(envelope / peak, 0.0, 1.25)
    # A small temporal smoothing makes visuals feel musical instead of jittery.
    if envelope.size >= 5:
        kernel = np.array([0.1, 0.2, 0.4, 0.2, 0.1], dtype=np.float32)
        envelope = np.convolve(envelope, kernel, mode="same").astype(np.float32)
    return envelope


def iter_audio_mono(path: Path, sample_rate: int = 8000):
    """Stream bounded PCM blocks with the base FFmpeg dependency only."""
    command = [ffmpeg_exe(), "-v", "error", "-i", str(path), "-vn", "-ac", "1",
               "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
    # A named log instead of TemporaryFile: an anonymous temporary file is
    # unlinked the moment it is opened, which locked-down accounts refuse.
    error_log = scratch_dir() / f"phrasync-audio-{os.getpid()}-{int(time.monotonic() * 1e6)}.log"
    errors = open(error_log, "w+b")
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, creationflags=background_flags())
        try:
            while True:
                data = process.stdout.read(sample_rate * 60 * 4)
                if not data:
                    break
                yield np.frombuffer(data, dtype=np.float32)
            if process.wait() != 0:
                errors.seek(0)
                raise RuntimeError(errors.read(8192).decode("utf-8", errors="replace"))
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
            process.wait()
    finally:
        errors.close()
        discard(error_log)


def decode_test(path: Path) -> tuple[bool, str]:
    process = run_ffmpeg(
        ["-v", "error", "-i", str(path), "-map", "0", "-f", "null", "-"],
        check=False,
    )
    message = process.stderr.decode("utf-8", errors="replace").strip()
    return process.returncode == 0, message


def decode_video_frame(path: Path) -> tuple[bool, str]:
    """Decode one video frame to validate an input without scanning it in full."""
    process = run_ffmpeg(
        [
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    message = process.stderr.decode("utf-8", errors="replace").strip()
    return process.returncode == 0, message


def decode_audio_frame(path: Path) -> tuple[bool, str]:
    """Decode a short audio sample, failing cleanly when no audio stream exists."""
    process = run_ffmpeg(
        [
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-t",
            "0.05",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    message = process.stderr.decode("utf-8", errors="replace").strip()
    return process.returncode == 0, message
