"""Bounded-memory Web Audio frequency bins for the offline visual renderer.

Match the live analyser's 48 kHz / 256 point Blackman FFT, dB range and byte
quantisation. Smoothing runs on the timeline at 60 Hz, independent of export
FPS. Two seconds of pre-roll preserve its history when exporting an IN range.
The live browser's scheduling/latency can still differ by a display frame.
"""
from __future__ import annotations

import subprocess
import tempfile
import math
import numpy as np
from .media import ffmpeg_exe
from .processes import background_flags


class SpectrumSource:
    SAMPLE_RATE = 48000
    FFT_SIZE = 256
    ANALYSIS_RATE = 60
    SMOOTHING = .78

    def __init__(self, path: str, fps: int, start_time: float = 0):
        if not math.isfinite(start_time) or start_time < 0 or fps <= 0:
            raise ValueError("Invalid spectrum start time or frame rate")
        self.fps = fps
        self.start_time = start_time
        self.position = 0
        self.tick = max(0, math.floor(start_time * self.ANALYSIS_RATE) - 120)
        self.first_tick = self.tick
        self.window = np.zeros(self.FFT_SIZE, dtype=np.float32)
        n = np.arange(self.FFT_SIZE) / self.FFT_SIZE
        self.blackman = .42 - .5 * np.cos(2 * np.pi * n) + .08 * np.cos(4 * np.pi * n)
        self.smoothed = np.zeros(self.FFT_SIZE // 2)
        self.values = [0.0] * (self.FFT_SIZE // 2)
        self.errors = tempfile.TemporaryFile()
        self.process = subprocess.Popen([
            ffmpeg_exe(), "-v", "error", "-ss", str(self.tick / self.ANALYSIS_RATE),
            "-i", path, "-vn", "-ac", "1", "-ar", str(self.SAMPLE_RATE),
            "-f", "f32le", "pipe:1"], stdout=subprocess.PIPE, stderr=self.errors, creationflags=background_flags())

    def read(self, index: int) -> list[float]:
        target_tick = math.floor((self.start_time + index / self.fps) * self.ANALYSIS_RATE + 1e-8)
        if target_tick < self.tick:
            raise ValueError("Spectrum frames must be requested in timeline order")
        while self.tick < target_tick:
            count = self.SAMPLE_RATE // self.ANALYSIS_RATE
            raw = self.process.stdout.read(count * 4)
            self.position += count
            samples = np.frombuffer(raw, dtype=np.float32)
            if len(samples) < count:
                samples = np.pad(samples, (0, count - len(samples)))
            self.window[:] = samples[-self.FFT_SIZE:]
            magnitude = np.abs(np.fft.rfft(self.window * self.blackman))[:self.FFT_SIZE // 2] / self.FFT_SIZE
            self.smoothed = self.SMOOTHING * self.smoothed + (1 - self.SMOOTHING) * magnitude
            db = 20 * np.log10(np.maximum(self.smoothed, 1e-30))
            # getByteFrequencyData floors (not rounds) into the 0..255 range.
            self.values = (np.floor(np.clip((db + 100) / 70, 0, 1) * 255) / 255).tolist()
            self.tick += 1
        return self.values.copy()

    def close(self):
        self.process.stdout.close()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait(timeout=5)
        self.errors.close()
