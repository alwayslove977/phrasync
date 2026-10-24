"""Validate saved footage without trusting client URLs or filesystem paths."""
from __future__ import annotations

import copy
import math
from .storage import get_asset
from .media import probe_duration

EFFECTS = {"bw": 100, "pendulum": 15, "shake": 8, "flash": 60, "gradient": 80,
           "particles": 100, "spectrum": 150, "bpm": 300, "drop": 30, "pulse": 40}


def effects_enabled(project: dict) -> bool:
    bg = project.get("background") or {}
    return bool(bg.get("footageEnabled")) or any(
        float((bg.get("effects") or {}).get(key) or 0) > 0 for key in EFFECTS if key != "bpm"
    )


def prepare_footage(project: dict) -> dict:
    project = copy.deepcopy(project)
    bg = project.setdefault("background", {})
    fx = bg.get("effects") or {}
    for key, maximum in EFFECTS.items():
        value = float(fx.get(key) or 0)
        if not math.isfinite(value) or value < 0 or value > maximum:
            raise ValueError(f"Invalid footage effect: {key}")
    if not bg.get("footageEnabled"):
        kind = bg.get("type")
        if kind in {"image", "video"}:
            # Older/source projects can contain only assetId. Rehydrate trusted
            # metadata for the browser instead of relying on stale saved URLs.
            asset_id = bg.get("assetId") or (bg.get(kind + "Asset") or {}).get("id")
            asset = get_asset(asset_id, kind) if asset_id else None
            if asset is None:
                raise ValueError(f"Background {kind} is missing. Import it again before exporting.")
            bg.update(assetId=asset.id, url=asset.url, name=asset.name)
            bg[kind + "Asset"] = asset.public()
        return project
    clips = bg.get("clips") or []
    if not isinstance(clips, list) or not clips:
        raise ValueError("Add images or videos to the footage timeline before exporting")
    durations = {}
    tracks = bg.get("tracks") or ["V1"]
    if not isinstance(tracks, list) or not 1 <= len(tracks) <= 4:
        raise ValueError("Use between one and four background tracks")
    for clip in clips:
        data = clip.get("asset") or {}
        if data.get("kind") == "visual":
            settings = data.get("settings") or {}
            if settings.get("visual") not in {"aurora", "particles", "equalizer", "grid", "scene", "scene3d"}:
                raise ValueError("Unknown integrated visual")
            if settings.get("sceneKit", "japan") not in {"japan", "italy", "china", "usa", "ocean"}:
                raise ValueError("Unknown visual environment")
        else:
            if data.get("kind") not in {"image", "video"}:
                raise ValueError("Footage clips must reference an image, video or integrated visual")
            asset = get_asset(data.get("id"), data["kind"])
            if asset is None:
                raise ValueError(f"Footage is missing: {data.get('name', 'clip')}. Import it again.")
            clip["asset"] = asset.public()
        track = clip.get("track", 0)
        if not isinstance(track, int) or not 0 <= track < len(tracks):
            raise ValueError("Clip references an unavailable background track")
        for key, maximum, default in [("opacity", 1, 1), ("fadeIn", 5, 0), ("fadeOut", 5, 0)]:
            value = float(clip.get(key, default))
            if not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError(f"Invalid clip transition value: {key}")
            clip[key] = value
        if clip.get("transition", "cut") not in {"cut", "fade", "wipe", "slide"}:
            raise ValueError("Unknown clip transition")
        numbers = {key: float(clip.get(key, default)) for key, default in
                   [("start", 0), ("end", 0), ("in", 0), ("rate", 1), ("zoomStart", 1), ("zoomEnd", 1),
                    ("xStart", 0), ("yStart", 0), ("xEnd", 0), ("yEnd", 0)]}
        if not all(math.isfinite(value) for value in numbers.values()):
            raise ValueError("Clip timing and movement must be finite numbers")
        if numbers["start"] < 0 or numbers["end"] <= numbers["start"] or numbers["in"] < 0 or not .25 <= numbers["rate"] <= 4:
            raise ValueError("Invalid clip timing or playback speed")
        if any(not 1 <= numbers[key] <= 4 for key in ["zoomStart", "zoomEnd"]) or any(
            not -1 <= numbers[key] <= 1 for key in ["xStart", "yStart", "xEnd", "yEnd"]):
            raise ValueError("Clip pan or zoom is outside the supported range")
        clip.update(numbers)
        if data.get("kind") == "video":
            if asset.id not in durations:
                durations[asset.id] = probe_duration(asset.path)
            duration = durations[asset.id]
            if duration is None or numbers["in"] + (numbers["end"] - numbers["start"]) * numbers["rate"] > duration + .04:
                raise ValueError("Video clip extends beyond its source. Adjust Source in, end or speed.")
            clip["asset"]["duration"] = duration
    return project
