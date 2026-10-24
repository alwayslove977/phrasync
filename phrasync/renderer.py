from __future__ import annotations

import math
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from . import kinetic
from .processes import background_flags
from .media import audio_envelope, decode_audio_frame, ffmpeg_exe, probe_duration
from .storage import Asset, get_asset, get_av_asset
from .render_backgrounds import DynamicBackground
from .render_typography import render_text_layer
from .render_utils import apply_dim, cover, scale_for_canvas
from .subtitles import normalize_cues
from .webgl_renderer import render_webgl_video
from .encoding import rate_control_args
from .footage import prepare_footage, effects_enabled

ProgressCallback = Callable[[float, str], None]


def webgl_color_args(encoded_format):
    # Canvas VideoFrames are sRGB / BT.709. Some Windows hardware encoders
    # omit the H.264 VUI, making players incorrectly assume a BT.601 matrix.
    # Set tags without another encode; the legacy CPU path uses its own matrix.
    return ['-bsf:v', 'h264_metadata=colour_primaries=1:transfer_characteristics=13:'
            'matrix_coefficients=1:video_full_range_flag=0'] if encoded_format == 'h264-gpu' else []


@dataclass(slots=True)
class RenderContext:
    project: dict[str, Any]
    width: int
    height: int
    fps: int
    duration: float
    frame_count: int
    cues: list[dict[str, Any]]
    audio: Asset | None
    background_asset: Asset | None
    font_asset: Asset | None
    envelope: np.ndarray
    start_time: float = 0.0


class VideoFrameSource:
    def __init__(self, path: Path, width: int, height: int, fps: int, frame_count: int, start_time: float = 0):
        self.frame_size = width * height * 3
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps}"
        )
        self.stderr = tempfile.TemporaryFile()
        self.process = subprocess.Popen(
            [
                ffmpeg_exe(),
                "-v",
                "error",
                "-stream_loop",
                "-1",
                "-ss", str(start_time),
                "-i",
                str(path),
                "-an",
                "-vf",
                vf,
                "-frames:v",
                str(frame_count),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            creationflags=background_flags(),
        )

    def read_sized(self, width: int, height: int) -> Image.Image:
        assert self.process.stdout is not None
        chunks = bytearray()
        while len(chunks) < self.frame_size:
            chunk = self.process.stdout.read(self.frame_size - len(chunks))
            if not chunk:
                break
            chunks.extend(chunk)
        raw = bytes(chunks)
        if len(raw) != self.frame_size:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            self.stderr.seek(0)
            details = self.stderr.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                "Background video decoder stopped before the export completed"
                + (f": {details}" if details else ".")
            )
        return Image.frombytes("RGB", (width, height), raw)

    def close(self) -> None:
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        self.stderr.close()


class FrameComposer:
    """Builds one finished frame: background, dim, then the lyric layer.

    render_project streams these to FFmpeg; scripts/qa_sync.py renders single
    frames with the same code so a QA contact sheet shows exactly what the
    export will show.
    """

    def __init__(self, ctx: RenderContext):
        self.ctx = ctx
        project = ctx.project
        background = project.get("background") or {}
        self.background = background
        self.type = background.get("type", "dynamic")
        self.shade = float(background.get("shade", 0.20))
        self.motion = float(background.get("motion", 0.0))
        style_for_background = {**(project.get("style") or {}), **background}
        self.dynamic = DynamicBackground(
            ctx.width, ctx.height, style_for_background, background.get("visual", "aurora")
        )
        timing = project.get("timing") or {}
        self.bpm = float(timing.get("bpm", 0) or 0)
        self.beat_offset = float(timing.get("beatOffset", 0) or 0)
        self.beat_react = bool((project.get("style") or {}).get("beatReact", True))

        self.video_source: VideoFrameSource | None = None
        self.image: Image.Image | None = None
        if self.type == "video" and ctx.background_asset:
            self.video_source = VideoFrameSource(
                Path(ctx.background_asset.path), ctx.width, ctx.height, ctx.fps, ctx.frame_count, ctx.start_time
            )
        elif self.type == "image" and ctx.background_asset:
            image = ImageOps.exif_transpose(Image.open(ctx.background_asset.path)).convert("RGB")
            image = cover(image, (ctx.width, ctx.height))
            blur = float(background.get("blur", 0))
            if blur > 0:
                image = image.filter(ImageFilter.GaussianBlur(scale_for_canvas(blur, ctx.height)))
            brightness = float(background.get("brightness", 1.0))
            if abs(brightness - 1.0) > 0.01:
                image = ImageEnhance.Brightness(image).enhance(brightness)
            self.image = image

    def pulse(self, t: float) -> float:
        if not self.beat_react:
            return 0.0
        return kinetic.beat_pulse(t, self.bpm, self.beat_offset)

    def amplitude(self, frame_index: int) -> float:
        envelope = self.ctx.envelope
        if not len(envelope):
            return 0.0
        return float(envelope[min(frame_index, len(envelope) - 1)])

    def background_frame(self, t: float, frame_index: int) -> Image.Image:
        amplitude = self.amplitude(frame_index)
        pulse = self.pulse(t)
        if self.type == "video" and self.video_source:
            return self.video_source.read_sized(self.ctx.width, self.ctx.height)
        elif self.type == "image" and self.image is not None:
            if self.motion > 0.001:
                zoom = 1.0 + self.motion * 0.025 * (0.5 + 0.5 * math.sin(t * 0.34))
                resized = self.image.resize(
                    (int(self.ctx.width * zoom), int(self.ctx.height * zoom)),
                    Image.Resampling.LANCZOS,
                )
                left = (resized.width - self.ctx.width) // 2
                top = (resized.height - self.ctx.height) // 2
                return resized.crop((left, top, left + self.ctx.width, top + self.ctx.height))
            return self.image.copy()
        return self.dynamic.render(t, amplitude, frame_index, pulse)

    def frame(self, t: float, frame_index: int) -> Image.Image:
        frame = apply_dim(self.background_frame(t, frame_index), self.shade)
        lyric_layer = render_text_layer(self.ctx, t)
        if lyric_layer is not None:
            frame = Image.alpha_composite(frame.convert("RGBA"), lyric_layer).convert("RGB")
        return frame

    def close(self) -> None:
        if self.video_source:
            source = self.video_source
            self.video_source = None
            source.close()


def _build_context(project: dict[str, Any], progress: ProgressCallback | None = None) -> RenderContext:
    canvas = project.get("canvas") or {}
    width = int(canvas.get("width", 1920))
    height = int(canvas.get("height", 1080))
    fps = int(canvas.get("fps", 30))
    if width < 320 or height < 320 or width > 3840 or height > 3840:
        raise ValueError("Canvas dimensions must be between 320 and 3840 pixels")
    if fps < 12 or fps > 60:
        raise ValueError("FPS must be between 12 and 60")
    cues = normalize_cues(project.get("cues") or [])
    audio = get_av_asset(project.get("audioAssetId")) if project.get("audioAssetId") else None
    if audio:
        audio_decodes, _ = decode_audio_frame(Path(audio.path))
        if not audio_decodes:
            raise ValueError("The selected media has no decodable audio stream.")
    background = project.get("background") or {}
    background_asset = None
    if not background.get("footageEnabled") and background.get("type") in {"image", "video"} and background.get("assetId"):
        background_asset = get_asset(background.get("assetId"), background.get("type"))
        if not background_asset:
            raise ValueError("Background asset is missing")
    style = project.get("style") or {}
    font_asset = get_asset(style.get("fontAssetId"), "font") if style.get("fontAssetId") else None
    cue_duration = max((float(cue["end"]) for cue in cues), default=0.0)
    duration = max(float(project.get("duration") or 0.0), cue_duration)
    if background.get("footageEnabled"):
        duration = max(duration, max((clip["end"] for clip in background.get("clips", [])), default=0))
    if audio:
        duration = probe_duration(Path(audio.path)) or duration
        if background.get("footageEnabled"):
            duration = max(duration, max((clip["end"] for clip in background.get("clips", [])), default=0))
    if background_asset and background.get("type") == "video":
        duration = max(duration, probe_duration(Path(background_asset.path)) or 0)
    if project.get("timelineDuration") is not None:
        duration = float(project["timelineDuration"])
        if not math.isfinite(duration) or duration < .5:
            raise ValueError("Timeline duration must be a finite number of at least 0.5 seconds")
    duration = max(0.5, duration)
    full_duration = duration
    start_time = 0.0
    export_range = project.get("exportRange")
    if export_range is not None:
        start_time = float(export_range.get("in", 0))
        end_time = float(export_range.get("out", duration))
        if not math.isfinite(start_time) or not math.isfinite(end_time) or not 0 <= start_time < end_time <= duration:
            raise ValueError("Export range must satisfy 0 <= IN < OUT <= timeline duration")
        duration = end_time - start_time
    # Decimal IN/OUT subtraction can turn 18 frames into 18.000000000000004.
    # Do not encode a phantom frame that the exact-duration mux then removes.
    frame_count = max(1, int(math.ceil(duration * fps - 1e-9)))
    if progress:
        progress(0.015, "Analyzing audio")
    envelope = audio_envelope(
        Path(audio.path) if audio else None,
        full_duration,
        fps,
        progress=(lambda value: progress(0.015 + value * 0.045, "Analyzing audio")) if progress else None,
    )
    envelope = envelope[round(start_time * fps):round(start_time * fps) + frame_count]
    return RenderContext(
        project=project,
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        frame_count=frame_count,
        cues=cues,
        audio=audio,
        background_asset=background_asset,
        font_asset=font_asset,
        envelope=envelope,
        start_time=start_time,
    )


def render_project(
    project: dict[str, Any],
    output_path: Path,
    progress: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    project = prepare_footage(project)
    ctx = _build_context(project, progress)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".partial.mp4")
    temporary.unlink(missing_ok=True)

    background = project.get("background") or {}
    exact_webgl = (
        background.get("textSpace", "flat") == "scene"
        or (background.get("type") == "dynamic" and background.get("visual") == "scene3d")
        or effects_enabled(project)
    )
    if exact_webgl:
        encoded = output_path.with_suffix(".partial.h264")
        try:
            flat_over_webgl = background.get("textSpace", "flat") != "scene"
            def composite_flat_frame(raw, timestamp):
                frame = Image.frombytes("RGBA", (ctx.width, ctx.height), raw)
                lyric = render_text_layer(ctx, timestamp)
                return Image.alpha_composite(frame, lyric).tobytes() if lyric is not None else raw

            encoded_format = render_webgl_video(
                project,
                encoded,
                width=ctx.width,
                height=ctx.height,
                fps=ctx.fps,
                frame_count=ctx.frame_count,
                envelope=ctx.envelope.astype(float).tolist(),
                progress=progress,
                cancel_check=cancel_check,
                frame_transform=composite_flat_frame if flat_over_webgl else None,
            )
            # Flat lyrics are composited before the first encode, not decoded
            # and encoded again. Both typography paths only need audio muxing.
            command = [ffmpeg_exe(), "-y", "-v", "error"]
            if encoded_format in {"h264", "h264-gpu"}:
                command.extend(["-r", str(ctx.fps), "-f", "h264"])
            command.extend(["-i", str(encoded)])
            if ctx.audio:
                command.extend(["-ss", str(ctx.start_time), "-i", ctx.audio.path])
            command.extend(["-map", "0:v:0"])
            if ctx.audio:
                command.extend(["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"])
            command.extend([*webgl_color_args(encoded_format), "-c:v", "copy", "-t", f"{ctx.duration:.6f}",
                            "-movflags", "+faststart", str(temporary)])
            if progress:
                progress(0.90, "Muxing WebGL video and audio")
            completed = subprocess.run(command, capture_output=True, text=True, creationflags=background_flags())
            if completed.returncode != 0:
                raise RuntimeError(f"FFmpeg WebGL mux failed: {completed.stderr.strip() or 'unknown error'}")
            temporary.replace(output_path)
            if progress:
                progress(1.0, "Render complete")
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            encoded.unlink(missing_ok=True)
        return {
            "path": str(output_path), "duration": ctx.duration, "frames": ctx.frame_count,
            "width": ctx.width, "height": ctx.height, "fps": ctx.fps,
            "elapsed": round(time.monotonic() - started, 3), "engine": "webgl",
        }

    composer = FrameComposer(ctx)

    command = [
        ffmpeg_exe(),
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s:v",
        f"{ctx.width}x{ctx.height}",
        "-r",
        str(ctx.fps),
        "-i",
        "pipe:0",
    ]
    if ctx.audio:
        command.extend(["-ss", str(ctx.start_time), "-i", ctx.audio.path])
    command.extend(
        [
            "-map",
            "0:v:0",
        ]
    )
    if ctx.audio:
        command.extend(["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            str(project.get("export", {}).get("preset", "medium")),
            *rate_control_args(project),
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{ctx.duration:.6f}",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=background_flags())
    assert encoder.stdin is not None
    try:
        for frame_index in range(ctx.frame_count):
            if cancel_check and cancel_check():
                raise RuntimeError("Render cancelled")
            t = ctx.start_time + frame_index / ctx.fps
            encoder.stdin.write(composer.frame(t, frame_index).tobytes())
            if progress and frame_index % max(1, ctx.frame_count // 200) == 0:
                progress(0.06 + 0.90 * (frame_index / ctx.frame_count), f"Rendering frame {frame_index + 1}/{ctx.frame_count}")
        encoder.stdin.close()
        stderr = encoder.stderr.read().decode("utf-8", errors="replace") if encoder.stderr else ""
        return_code = encoder.wait()
        if return_code != 0:
            raise RuntimeError(f"FFmpeg export failed: {stderr.strip() or 'unknown error'}")
        temporary.replace(output_path)
        if progress:
            progress(1.0, "Render complete")
    except Exception:
        try:
            encoder.stdin.close()
        except Exception:
            pass
        if encoder.poll() is None:
            encoder.kill()
        encoder.wait(timeout=5)
        if encoder.stderr:
            encoder.stderr.close()
        composer.close()
        temporary.unlink(missing_ok=True)
        raise
    finally:
        composer.close()

    return {
        "path": str(output_path),
        "duration": ctx.duration,
        "frames": ctx.frame_count,
        "width": ctx.width,
        "height": ctx.height,
        "fps": ctx.fps,
        "elapsed": round(time.monotonic() - started, 3),
    }
