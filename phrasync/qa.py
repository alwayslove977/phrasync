from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .align import alignment_stats
from .audio_analysis import analyze_audio
from .font_utils import resolve_font_path
from .media import decode_audio_frame, decode_test, decode_video_frame, probe_duration
from .storage import get_asset, get_av_asset
from .subtitles import estimate_duration, normalize_cues


@dataclass(slots=True)
class Issue:
    level: str
    code: str
    message: str
    cue_id: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "cueId": self.cue_id,
        }


@dataclass(slots=True)
class CriticReport:
    issues: list[Issue] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add(self, level: str, code: str, message: str, cue_id: str | None = None) -> None:
        self.issues.append(Issue(level, code, message, cue_id))

    @property
    def score(self) -> int:
        penalties = {"error": 20, "warning": 6, "note": 1}
        return max(0, 100 - sum(penalties.get(issue.level, 0) for issue in self.issues))

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    def public(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "score": self.score,
            "issues": [issue.public() for issue in self.issues],
            "checks": self.checks,
            "metrics": self.metrics,
        }


def _hex_rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    value = str(value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return fallback
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    values = []
    for channel in rgb:
        value = channel / 255.0
        values.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    l1, l2 = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def preflight_project(project: dict[str, Any]) -> CriticReport:
    report = CriticReport()
    from .footage import prepare_footage
    try:
        prepare_footage(project)
        report.checks.append("Footage sources, trim limits and effects")
    except (ValueError, TypeError, KeyError) as exc:
        report.add("error", "invalid_footage", str(exc))
    canvas = project.get("canvas") or {}
    width = int(canvas.get("width", 1920))
    height = int(canvas.get("height", 1080))
    fps = int(canvas.get("fps", 30))
    report.metrics.update({"width": width, "height": height, "fps": fps})

    if width < 320 or height < 320:
        report.add("error", "canvas_too_small", "Canvas dimensions must be at least 320 px.")
    if width > 3840 or height > 3840:
        report.add("warning", "canvas_large", "4K-class rendering can be slow and memory intensive.")
    if fps not in {23, 24, 25, 30, 50, 60}:
        report.add("warning", "unusual_fps", f"{fps} fps is valid, but 24/25/30/50/60 is easier to deliver.")
    if fps < 12 or fps > 60:
        report.add("error", "fps_range", "FPS must be between 12 and 60.")
    report.checks.append("Canvas geometry and frame rate")

    cues = normalize_cues(project.get("cues") or [])
    report.metrics["cueCount"] = len(cues)
    if not cues:
        report.add("error", "no_cues", "No lyric cues are present.")
    previous_end = 0.0
    for cue in cues:
        cue_id = cue["id"]
        duration = cue["end"] - cue["start"]
        if cue["start"] + 0.08 < previous_end:
            report.add("warning", "cue_overlap", "This cue overlaps the previous cue.", cue_id)
        if duration < 0.35:
            report.add("warning", "cue_too_fast", f"Cue is visible for only {duration:.2f}s.", cue_id)
        if duration > 8.0:
            report.add("note", "cue_long", f"Cue remains on screen for {duration:.1f}s.", cue_id)
        plain = cue["text"].replace("\n", " ")
        if len(plain) > 90:
            report.add("warning", "cue_dense", "Cue is very long and may wrap into too many lines.", cue_id)
        if len(plain.split()) > 16:
            report.add("note", "cue_word_count", "Consider splitting this cue for stronger kinetic timing.", cue_id)
        previous_end = max(previous_end, cue["end"])
    report.checks.append("Cue timing, overlap, density, and readability")

    timed = [cue for cue in cues if len(cue.get("words") or []) > 0]
    report.metrics["wordTimedCues"] = len(timed)
    if cues and not timed:
        report.add(
            "warning",
            "no_word_timing",
            "No cue carries word-level timing, so the kinetic presets fall back to estimated word starts.",
        )
    elif cues and len(timed) < len(cues) * 0.6:
        report.add(
            "note",
            "partial_word_timing",
            f"Only {len(timed)} of {len(cues)} cues have word timing; run Auto-align for tighter sync.",
        )
    for cue in timed:
        words = cue.get("words") or []
        if any(float(word.get("end", 0)) <= float(word.get("start", 0)) for word in words):
            report.add("warning", "word_zero_length", "A word in this cue has no duration.", cue["id"])
        if float(words[0].get("start", cue["start"])) < cue["start"] - 0.05:
            report.add("note", "word_before_cue", "A word starts before its own cue.", cue["id"])
    report.checks.append("Word-level timing integrity")

    audio_id = project.get("audioAssetId")
    audio = get_av_asset(audio_id) if audio_id else None
    audio_decodes = False
    if audio:
        audio_decodes, audio_message = decode_audio_frame(Path(audio.path))
        if not audio_decodes:
            report.add(
                "error",
                "audio_stream_missing",
                "The selected media has no decodable audio stream. Choose a video with audio or an audio file."
                + (f" FFmpeg: {audio_message[:400]}" if audio_message else ""),
            )
        else:
            report.checks.append("Decodable audio stream")
    if audio and audio_decodes and cues:
        try:
            analysis = analyze_audio(Path(audio.path))
            stats = alignment_stats(cues, analysis)
            report.metrics["alignment"] = stats
            report.metrics["bpm"] = analysis.get("bpm")
            if stats["words"]:
                error_ms = round(stats["meanError"] * 1000)
                if stats["score"] < 45:
                    report.add(
                        "warning",
                        "alignment_loose",
                        f"Lyrics sit {error_ms} ms away from the sung attacks on average. Run Auto-align.",
                    )
                elif stats["score"] < 70:
                    report.add(
                        "note",
                        "alignment_fair",
                        f"Average sync error is {error_ms} ms; Auto-align or a global offset can tighten it.",
                    )
                if stats["loose"] > 0.2:
                    report.add(
                        "note",
                        "alignment_outliers",
                        f"{round(stats['loose'] * 100)}% of words are more than 250 ms from any vocal attack.",
                    )
            report.checks.append("Lyric-to-audio alignment against detected onsets")
        except Exception as exc:  # analysis is advisory, never blocks a render
            report.metrics["alignmentError"] = str(exc)
    if audio_id and not audio:
        report.add("error", "missing_audio", "The selected audio asset is unavailable; upload it again.")
    elif not audio:
        report.add("warning", "no_audio", "No audio is attached. Export will use cue timing only.")
    report.checks.append("Audio asset availability")

    background = project.get("background") or {}
    background_type = background.get("type", "dynamic")
    background_id = background.get("assetId")
    if not background.get("footageEnabled") and background_type in {"image", "video"}:
        expected = background_type
        asset = get_asset(background_id, expected) if background_id else None
        if not asset:
            report.add("error", "missing_background", f"The selected {background_type} background is unavailable.")
        else:
            decodes, message = decode_video_frame(Path(asset.path))
            if not decodes:
                report.add(
                    "error",
                    "background_decode_failed",
                    f"FFmpeg could not decode the selected {background_type}: {message[:600]}",
                )
    elif background_type not in {"dynamic", "image", "video"}:
        report.add("error", "background_type", f"Unknown background type: {background_type}")
    if background_type == "dynamic":
        visual = background.get("visual", "aurora")
        text_space = background.get("textSpace", "flat")
        if visual == "scene3d":
            report.add(
                "note",
                "odyssey_webgl_export",
                "Odyssey will be rendered by the WebGL scene engine for MP4 export.",
            )
        elif visual == "scene":
            report.add(
                "note",
                "odyssey_export_rasterized",
                "Odyssey will be rasterized for MP4 export; WebGL lighting may differ slightly from the live preview.",
            )
        elif visual not in {"aurora", "particles", "equalizer", "grid"}:
            report.add("error", "dynamic_visual", f"Unknown dynamic visual: {visual}")
        if visual == "equalizer" and not audio:
            report.add("note", "equalizer_without_audio", "Equalizer will animate gently because no audio is attached.")
    if background.get("textSpace", "flat") == "scene":
        report.add(
            "note",
            "text3d_webgl_export",
            "World-space 3D typography will be rendered by WebGL for MP4 export.",
        )
    report.checks.append("Background asset and dynamic visual logic")

    style = project.get("style") or {}
    custom_font = get_asset(style.get("fontAssetId"), "font") if style.get("fontAssetId") else None
    font_path = Path(custom_font.path) if custom_font else None
    resolved = resolve_font_path(style.get("fontPreset", "impact"), font_path)
    if not resolved:
        report.add("error", "font_missing", "No usable system or custom font was found.")
    report.metrics["font"] = str(resolved or "")
    text_rgb = _hex_rgb(style.get("textColor", "#f3d7ff"), (243, 215, 255))
    estimated_bg = (12, 11, 22)
    contrast = _contrast(text_rgb, estimated_bg)
    report.metrics["estimatedTextContrast"] = round(contrast, 2)
    if contrast < 3.0:
        report.add("warning", "low_contrast", f"Estimated text contrast is low ({contrast:.1f}:1).")
    if float(style.get("fontSize", 140)) < 34:
        report.add("warning", "small_type", "Text may be too small for mobile viewing.")
    if float(style.get("maxWidth", 86)) > 96:
        report.add("note", "safe_margin", "Text is very close to the frame edges.")
    report.checks.append("Font resolution, safe area, and contrast")

    cue_duration = max((float(cue["end"]) for cue in cues), default=0.0)
    duration = max(float(project.get("duration") or 0.0), cue_duration)
    if audio:
        from .media import probe_duration

        detected = probe_duration(Path(audio.path))
        if detected:
            duration = detected
            last_end = max((cue["end"] for cue in cues), default=0.0)
            if last_end > detected + 0.25:
                report.add("warning", "lyrics_after_audio", "Some lyric cues continue after the audio ends.")
    duration = max(duration, max((float(clip["end"]) for clip in (project.get("background") or {}).get("clips", [])), default=0))
    if project.get("timelineDuration") is not None:
        duration = float(project["timelineDuration"])
    if project.get("exportRange") is not None:
        selected = project["exportRange"]
        start, end = float(selected.get("in", 0)), float(selected.get("out", duration))
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration:
            report.add("error", "invalid_export_range", "Export IN/OUT must be within the timeline and OUT must follow IN.")
        else:
            duration = end - start
    report.metrics["duration"] = round(duration, 3)

    frame_count = int(math.ceil(duration * fps))
    report.metrics["estimatedFrames"] = frame_count
    if frame_count > 20_000:
        report.add("warning", "long_render", f"Render contains about {frame_count:,} frames and may take time.")
    report.checks.append("Duration and render workload")
    return report


def postflight_render(output_path: Path, expected_duration: float | None = None) -> CriticReport:
    report = CriticReport()
    if not output_path.exists():
        report.add("error", "output_missing", "Renderer did not produce an output file.")
        return report
    size = output_path.stat().st_size
    report.metrics["fileSize"] = size
    if size < 1_024:
        report.add("error", "output_tiny", "Rendered file is unexpectedly small.")
    elif size < 16_384:
        report.add("note", "output_small", "Rendered file is very small; this is normal for short low-resolution tests.")
    ok, decoder_message = decode_test(output_path)
    if not ok:
        report.add("error", "decode_failed", f"FFmpeg could not decode the finished file: {decoder_message}")
    else:
        report.checks.append("Full output decode with FFmpeg")
    duration = probe_duration(output_path)
    report.metrics["duration"] = duration
    if expected_duration and duration and abs(duration - expected_duration) > max(0.5, expected_duration * 0.03):
        report.add(
            "warning",
            "duration_mismatch",
            f"Output duration {duration:.2f}s differs from expected {expected_duration:.2f}s.",
        )
    if duration and duration <= 0.1:
        report.add("error", "duration_zero", "Output duration is effectively zero.")
    report.checks.append("File size and duration sanity")
    return report
