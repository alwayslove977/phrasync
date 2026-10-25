"""Bounded-memory frequency bands for the offline overlay, not fake amplitude bars."""
from __future__ import annotations

import os
import subprocess
import time
import numpy as np
from .config import discard, scratch_dir
from .media import ffmpeg_exe
from .processes import background_flags


class SpectrumSource:
    def __init__(self, path: str, fps: int, start_time: float = 0):
        self.fps = fps
        self.position = 0
        self.window = np.zeros(2048, dtype=np.float32)
        self.hann = np.hanning(2048).astype(np.float32)
        # Named log instead of TemporaryFile, which unlinks on open.
        self.error_log = scratch_dir() / f"phrasync-spectrum-{os.getpid()}-{int(time.monotonic() * 1e6)}.log"
        self.errors = open(self.error_log, "w+b")
        self.process = subprocess.Popen([
            ffmpeg_exe(), "-v", "error", "-ss", str(start_time), "-i", path, "-vn", "-ac", "1", "-ar", "8000",
            "-f", "f32le", "pipe:1"], stdout=subprocess.PIPE, stderr=self.errors, creationflags=background_flags())
        frequencies = np.fft.rfftfreq(2048, 1 / 8000)
        edges = np.geomspace(40, 3900, 33)
        self.bands = [np.flatnonzero((frequencies >= edges[i]) & (frequencies < edges[i + 1])) for i in range(32)]

    def read(self, index: int) -> list[float]:
        target = round((index + 1) * 8000 / self.fps)
        count = max(0, target - self.position)
        raw = self.process.stdout.read(count * 4)
        self.position = target
        samples = np.frombuffer(raw, dtype=np.float32)
        if len(samples) < count:
            samples = np.pad(samples, (0, count - len(samples)))
        if count >= len(self.window):
            self.window[:] = samples[-len(self.window):]
        elif count:
            self.window = np.roll(self.window, -count); self.window[-count:] = samples
        fft = np.abs(np.fft.rfft(self.window * self.hann)) / 512
        return [round(float(np.clip((20 * np.log10(max(1e-5, float(fft[band].max()) if len(band) else 0)) + 80) / 80, 0, 1)), 4) for band in self.bands]

    def close(self):
        self.process.stdout.close()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait(timeout=5)
        self.errors.close()
        discard(self.error_log)
