"""Build a language timeline for one track, then hand each span to Whisper.

Whisper commits to a single language token per decoder window, so a song that
opens in Italian and moves through Portuguese, French and Japanese gets forced
back into the opening language for the whole track. This module detects the
language on a sliding window first, smooths the result into stable spans, and
lets the caller decode each span with its own language locked in.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np

SAMPLE_RATE = 16000
WINDOW_SECONDS = 10.0     # detection window; Whisper pads it to its own 30 s input
MIN_SPAN_SECONDS = 12.0   # shorter runs are absorbed: a song rarely flips faster
BOUNDARY_SNAP_SECONDS = 5.0
MIN_CONFIDENCE = 0.28     # below this a window is instrumental or unintelligible
SWITCH_PENALTY = 2.5      # log-odds a switch must win by, in the Viterbi pass
SILENCE_RATIO = 0.12
RMS_HOP_SECONDS = 0.1
PROBABILITY_FLOOR = 1e-4
MAX_CANDIDATES = 8
TOP_K = 8

# Second pass, one sung phrase at a time. Measured on a six-language track:
# raw phrase detection agrees with the sung language 37/42 times, and this
# penalty lifts that to 41/42 while keeping a genuine line-by-line it/fr
# alternation that any window-sized pass flattens into one language.
PHRASE_PAD_SECONDS = 0.25
PHRASE_SWITCH_PENALTY = 2.0
PHRASE_GAP_DISCOUNT = 0.25   # a long instrumental pause makes a switch cheaper
PHRASE_GAP_FLOOR = 0.4
PHRASE_MARGIN_SECONDS = 1.5
# A language the window pass never chose has to earn its place twice over: one
# confident phrase is how a track picks up a spurious language it never sings,
# and decoding an instrumental bar in that language invents a line.
PHRASE_CANDIDATE_THRESHOLD = 0.75
PHRASE_CANDIDATE_VOTES = 2

MULTI_TOKENS = {"multilingual", "mixed", "multi", "code-switching", "codeswitching", "map"}
SINGLE_TOKENS = {"single", "one", "dominant", "lock", "auto-single"}
AUTO_TOKENS = {"auto", "automatic", ""}
_SPLIT_RE = re.compile(r"[\s,+/;|]+")


def parse_language_request(language: str) -> dict[str, Any]:
    """Turn the language field into a decoding plan.

    ``auto`` and ``multilingual`` both build a language map; ``auto`` still
    collapses to a single pass when the map finds one language. A bare code
    (``it``) locks the track, and a list (``it,en,ja``) restricts the map to
    those languages, which is the most reliable option for a known set.
    """
    parts = [part for part in _SPLIT_RE.split((language or "auto").strip().lower()) if part]
    codes = [part for part in parts if part not in MULTI_TOKENS | SINGLE_TOKENS | AUTO_TOKENS]
    wants_multi = any(part in MULTI_TOKENS for part in parts)
    wants_single = any(part in SINGLE_TOKENS for part in parts)

    if len(codes) > 1 or (codes and wants_multi):
        return {"mode": "map", "codes": codes, "forced": True}
    if codes:
        return {"mode": "fixed", "codes": codes, "forced": False}
    if wants_single:
        return {"mode": "single", "codes": [], "forced": False}
    return {"mode": "map", "codes": [], "forced": wants_multi}


def known_language_codes() -> set[str]:
    try:
        from faster_whisper.tokenizer import _LANGUAGE_CODES

        return set(_LANGUAGE_CODES)
    except Exception:  # pragma: no cover - only when faster-whisper is absent
        return set()


def load_audio(path: Path) -> np.ndarray:
    from faster_whisper.audio import decode_audio

    try:
        return decode_audio(str(path), sampling_rate=SAMPLE_RATE)
    except TypeError as error:
        # Existing source environments may already have PyAV 19 installed.
        # Do not hide unrelated decoder errors or monkey-patch a dependency.
        if "metadata_errors" not in str(error) or "unexpected keyword" not in str(error):
            raise
        from .diagnostics import log_event
        from .media import decode_audio_mono
        log_event("warning", "transcription", "PyAV metadata_errors incompatibility; decoding audio with FFmpeg")
        return decode_audio_mono(path, sample_rate=SAMPLE_RATE)


def _short_time_rms(audio: np.ndarray) -> np.ndarray:
    hop = int(SAMPLE_RATE * RMS_HOP_SECONDS)
    usable = (len(audio) // hop) * hop
    if usable <= 0:
        return np.zeros(1, dtype=np.float32)
    frames = audio[:usable].reshape(-1, hop).astype(np.float32)
    return np.sqrt(np.mean(frames * frames, axis=1))


def detect_language_windows(
    model: Any,
    audio: np.ndarray,
    *,
    allowed: list[str] | None = None,
    window_seconds: float = WINDOW_SECONDS,
    cancel_check: Callable[[], bool] | None = None,
    progress: Callable[[float], None] | None = None,
) -> list[dict[str, Any]]:
    """Score every window of the track with Whisper's own language detector."""
    from faster_whisper.audio import pad_or_trim

    duration = len(audio) / SAMPLE_RATE
    features = model.feature_extractor(audio)
    frames_per_second = model.frames_per_second
    total_frames = features.shape[-1]
    energy = _short_time_rms(audio)
    voiced = energy[energy > 0]
    reference = float(np.median(voiced)) if voiced.size else 0.0

    windows: list[dict[str, Any]] = []
    start = 0.0
    while start < duration - 0.5:
        if cancel_check and cancel_check():
            break
        end = min(duration, start + window_seconds)
        begin_frame = int(round(start * frames_per_second))
        end_frame = min(total_frames, int(round(end * frames_per_second)))
        if end_frame - begin_frame < frames_per_second:  # under a second of audio
            break
        encoder_output = model.encode(pad_or_trim(features[:, begin_frame:end_frame]))
        scores = {
            str(token)[2:-2]: float(probability)
            for token, probability in model.model.detect_language(encoder_output)[0]
        }
        if allowed:
            subset = {code: scores.get(code, 0.0) for code in allowed}
            total = sum(subset.values())
            probabilities = (
                {code: value / total for code, value in subset.items()} if total > 0 else subset
            )
        else:
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            probabilities = dict(ranked[:TOP_K])

        first = int(start / RMS_HOP_SECONDS)
        last = max(first + 1, int(end / RMS_HOP_SECONDS))
        level = float(np.mean(energy[first:last])) if energy[first:last].size else 0.0
        windows.append(
            {
                "start": start,
                "end": end,
                "probabilities": probabilities,
                "silent": reference > 0 and level < SILENCE_RATIO * reference,
            }
        )
        if progress:
            progress(min(1.0, end / max(duration, 1e-6)))
        start += window_seconds
    return windows


def _candidates(windows: list[dict[str, Any]], allowed: list[str] | None) -> list[str]:
    if allowed:
        return list(dict.fromkeys(allowed))
    totals: dict[str, float] = {}
    for window in windows:
        for code, probability in window["probabilities"].items():
            totals[code] = totals.get(code, 0.0) + probability
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [code for code, _ in ranked[:MAX_CANDIDATES]] or ["en"]


def _emissions(window: dict[str, Any], candidates: list[str]) -> dict[str, float]:
    """Log-likelihood per candidate, flattened where the window says nothing.

    An instrumental break or a mumbled window carries no evidence, so every
    candidate scores the same and the path simply keeps whatever it was singing.
    """
    probabilities = window["probabilities"]
    top = max(probabilities.values(), default=0.0)
    if window["silent"] or top < MIN_CONFIDENCE:
        return {code: 0.0 for code in candidates}
    return {
        code: math.log(max(probabilities.get(code, 0.0), PROBABILITY_FLOOR))
        for code in candidates
    }


def _viterbi_labels(
    windows: list[dict[str, Any]],
    candidates: list[str],
    penalty: float = SWITCH_PENALTY,
    gap_discount: float = 0.0,
) -> list[str]:
    """Cheapest consistent language path across the track.

    Labelling each window on its own makes the timeline flicker between the
    languages Whisper confuses when sung (es/pt, fr/ro). Charging every change a
    fixed penalty keeps a switch only where the audio really insists on it.
    """
    if not windows or not candidates:
        return []
    scores = _emissions(windows[0], candidates)
    trail: list[dict[str, str]] = []
    for position, window in enumerate(windows[1:], start=1):
        emission = _emissions(window, candidates)
        cost = penalty
        if gap_discount:
            gap = max(0.0, float(window["start"]) - float(windows[position - 1]["end"]))
            cost = penalty * max(PHRASE_GAP_FLOOR, 1.0 - gap_discount * gap)
        leader = max(scores, key=lambda code: scores[code])
        pointers: dict[str, str] = {}
        updated: dict[str, float] = {}
        for code in candidates:
            stay = scores[code]
            switch = scores[leader] - cost
            if code != leader and switch > stay:
                updated[code] = switch + emission[code]
                pointers[code] = leader
            else:
                updated[code] = stay + emission[code]
                pointers[code] = code
        trail.append(pointers)
        scores = updated

    labels = [max(scores, key=lambda code: scores[code])]
    for pointers in reversed(trail):
        labels.append(pointers[labels[-1]])
    labels.reverse()
    return labels


def _coalesce(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for span in spans:
        if merged and merged[-1]["language"] == span["language"]:
            merged[-1]["end"] = span["end"]
            merged[-1]["scores"].extend(span["scores"])
        else:
            merged.append(dict(span, scores=list(span["scores"])))
    return merged


def _merge_short_spans(spans: list[dict[str, Any]], minimum: float) -> list[dict[str, Any]]:
    while len(spans) > 1:
        index = min(
            range(len(spans)),
            key=lambda position: spans[position]["end"] - spans[position]["start"],
        )
        if spans[index]["end"] - spans[index]["start"] >= minimum:
            break
        left = spans[index - 1] if index > 0 else None
        right = spans[index + 1] if index + 1 < len(spans) else None
        if left is None:
            target = right
        elif right is None:
            target = left
        else:
            target = left if (left["end"] - left["start"]) >= (right["end"] - right["start"]) else right
        target["start"] = min(target["start"], spans[index]["start"])
        target["end"] = max(target["end"], spans[index]["end"])
        target["scores"].extend(spans[index]["scores"])
        spans.pop(index)
        spans = _coalesce(spans)
    return spans


def _snap_boundaries(spans: list[dict[str, Any]], audio: np.ndarray) -> list[dict[str, Any]]:
    """Move each language change onto the quietest moment nearby.

    Detection resolution is one window; the singer switches on a breath. Cutting
    on the local energy minimum keeps a sung line inside a single decode.
    """
    if len(spans) < 2:
        return spans
    energy = _short_time_rms(audio)
    for index in range(1, len(spans)):
        boundary = spans[index]["start"]
        low = max(spans[index - 1]["start"] + 1.0, boundary - BOUNDARY_SNAP_SECONDS)
        high = min(spans[index]["end"] - 1.0, boundary + BOUNDARY_SNAP_SECONDS)
        if high <= low:
            continue
        first = int(low / RMS_HOP_SECONDS)
        last = int(high / RMS_HOP_SECONDS)
        segment = energy[first:last]
        if not segment.size:
            continue
        quietest = low + float(np.argmin(segment)) * RMS_HOP_SECONDS
        spans[index - 1]["end"] = quietest
        spans[index]["start"] = quietest
    return spans


def language_spans(
    windows: list[dict[str, Any]], duration: float, allowed: list[str] | None = None
) -> list[dict[str, Any]]:
    if not windows:
        return []
    labels = _viterbi_labels(windows, _candidates(windows, allowed))
    spans: list[dict[str, Any]] = []
    for label, window in zip(labels, windows):
        score = float(window["probabilities"].get(label, 0.0))
        if spans and spans[-1]["language"] == label:
            spans[-1]["end"] = window["end"]
            spans[-1]["scores"].append(score)
        else:
            spans.append(
                {"language": label, "start": window["start"], "end": window["end"], "scores": [score]}
            )
    spans = _merge_short_spans(spans, MIN_SPAN_SECONDS)
    spans[0]["start"] = 0.0
    spans[-1]["end"] = max(duration, spans[-1]["end"])
    return spans


def build_language_map(
    model: Any,
    audio: np.ndarray,
    *,
    allowed: list[str] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress: Callable[[float], None] | None = None,
) -> list[dict[str, Any]]:
    """Detect, smooth and snap: the finished timeline of language spans."""
    duration = len(audio) / SAMPLE_RATE
    windows = detect_language_windows(
        model, audio, allowed=allowed, cancel_check=cancel_check, progress=progress
    )
    spans = language_spans(windows, duration, allowed)
    spans = _snap_boundaries(spans, audio)
    return [
        {
            "language": span["language"],
            "start": round(float(span["start"]), 3),
            "end": round(float(span["end"]), 3),
            "probability": round(float(np.mean(span["scores"])) if span["scores"] else 0.0, 4),
        }
        for span in spans
    ]


def detect_phrase_languages(
    model: Any,
    audio: np.ndarray,
    phrases: list[dict[str, Any]],
    base_languages: list[str],
    *,
    cancel_check: Callable[[], bool] | None = None,
    progress: Callable[[float], None] | None = None,
) -> list[dict[str, Any]]:
    """Identify the language of every sung phrase, then smooth the sequence.

    The window pass cannot see a switch that happens between two lines, which is
    exactly how a code-switching song is written. Running detection on the
    phrases the first decode found gives one decision per line.
    """
    from faster_whisper.audio import pad_or_trim

    if not phrases:
        return []
    features = model.feature_extractor(audio)
    frames_per_second = model.frames_per_second
    total_frames = features.shape[-1]
    minimum = int(frames_per_second * 0.5)

    scored: list[dict[str, float]] = []
    for index, phrase in enumerate(phrases):
        if cancel_check and cancel_check():
            return []
        start = max(0.0, float(phrase["start"]) - PHRASE_PAD_SECONDS)
        end = float(phrase["end"]) + PHRASE_PAD_SECONDS
        begin_frame = int(start * frames_per_second)
        end_frame = min(total_frames, max(begin_frame + minimum, int(end * frames_per_second)))
        encoder_output = model.encode(pad_or_trim(features[:, begin_frame:end_frame]))
        scored.append(
            {
                str(token)[2:-2]: float(probability)
                for token, probability in model.model.detect_language(encoder_output)[0]
            }
        )
        if progress:
            progress((index + 1) / len(phrases))

    # A language the window pass never settled on can still own a couple of
    # lines, but it needs more than one confident phrase to join the set.
    candidates = list(dict.fromkeys(base_languages))
    votes: dict[str, int] = {}
    for scores in scored:
        code, probability = max(scores.items(), key=lambda item: item[1], default=("", 0.0))
        if code and code not in candidates and probability >= PHRASE_CANDIDATE_THRESHOLD:
            votes[code] = votes.get(code, 0) + 1
    candidates.extend(code for code, count in votes.items() if count >= PHRASE_CANDIDATE_VOTES)
    candidates = candidates[:MAX_CANDIDATES]
    if not candidates:
        return []

    items: list[dict[str, Any]] = []
    for phrase, scores in zip(phrases, scored):
        subset = {code: scores.get(code, 0.0) for code in candidates}
        total = sum(subset.values())
        items.append(
            {
                "start": float(phrase["start"]),
                "end": float(phrase["end"]),
                "probabilities": (
                    {code: value / total for code, value in subset.items()} if total > 0 else subset
                ),
                "silent": False,
            }
        )

    labels = _viterbi_labels(items, candidates, PHRASE_SWITCH_PENALTY, PHRASE_GAP_DISCOUNT)
    return [
        {"language": label, "probability": round(item["probabilities"].get(label, 0.0), 4)}
        for label, item in zip(labels, items)
    ]


def spans_from_phrases(
    phrases: list[dict[str, Any]], decisions: list[dict[str, Any]], duration: float
) -> list[dict[str, Any]]:
    """Turn per-phrase decisions into a timeline that covers the whole track.

    Each change is cut in the middle of the pause between the two phrases, which
    is where the singer actually crosses over.
    """
    spans: list[dict[str, Any]] = []
    for phrase, decision in zip(phrases, decisions):
        if spans and spans[-1]["language"] == decision["language"]:
            spans[-1]["end"] = float(phrase["end"])
            spans[-1]["scores"].append(decision["probability"])
        else:
            spans.append(
                {
                    "language": decision["language"],
                    "start": float(phrase["start"]),
                    "end": float(phrase["end"]),
                    "scores": [decision["probability"]],
                }
            )
    for index in range(1, len(spans)):
        middle = (spans[index - 1]["end"] + spans[index]["start"]) / 2
        spans[index - 1]["end"] = middle
        spans[index]["start"] = middle
    if spans:
        spans[0]["start"] = 0.0
        spans[-1]["end"] = max(duration, spans[-1]["end"])
    return [
        {
            "language": span["language"],
            "start": round(span["start"], 3),
            "end": round(span["end"], 3),
            "probability": round(float(np.mean(span["scores"])) if span["scores"] else 0.0, 4),
        }
        for span in spans
    ]


def phrase_clips(
    phrases: list[dict[str, Any]], duration: float, margin: float = PHRASE_MARGIN_SECONDS
) -> list[tuple[float, float]]:
    """The sung parts of the track, padded and merged.

    The second pass has no business decoding the intro, the outro or a long
    instrumental bridge: the first pass already found nothing there, and asking
    Whisper to read silence in a freshly chosen language is how a track ends up
    captioned "Sous-titres par…".
    """
    ranges: list[tuple[float, float]] = []
    for phrase in phrases:
        start = max(0.0, float(phrase["start"]) - margin)
        end = float(phrase["end"]) + margin
        if duration > 0:
            end = min(end, duration)
        if end <= start:
            continue
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    return ranges


def intersect_clips(
    first: list[tuple[float, float]], second: list[tuple[float, float]] | None
) -> list[tuple[float, float]]:
    if second is None:
        return list(first)
    overlaps: list[tuple[float, float]] = []
    for begin, finish in first:
        for other_begin, other_finish in second:
            start = max(begin, other_begin)
            end = min(finish, other_finish)
            if end - start > 0.05:
                overlaps.append((start, end))
    overlaps.sort()
    return overlaps


def normalize_spans(spans: list[dict[str, Any]] | None, duration: float) -> list[dict[str, Any]]:
    """Clean a caller-supplied language map into a usable timeline.

    Whisper's language detector is confident even when it is wrong, so the app
    hands the detected map back for editing. Whatever comes back is sorted,
    clamped to the track and stripped of overlaps before it drives a decode.
    """
    cleaned: list[dict[str, Any]] = []
    for span in spans or []:
        code = str(span.get("language", "")).strip().lower()
        if not code:
            continue
        start = max(0.0, float(span.get("start", 0.0)))
        end = float(span.get("end", start))
        if duration > 0:
            end = min(end, duration)
        if end - start < 0.5:
            continue
        cleaned.append(
            {
                "language": code,
                "start": start,
                "end": end,
                "probability": float(span.get("probability", 0.0) or 0.0),
            }
        )
    cleaned.sort(key=lambda span: (span["start"], span["end"]))

    ordered: list[dict[str, Any]] = []
    for span in cleaned:
        if ordered:
            span["start"] = max(span["start"], ordered[-1]["end"])
            if span["end"] - span["start"] < 0.5:
                continue
            if ordered[-1]["language"] == span["language"]:
                ordered[-1]["end"] = span["end"]
                continue
        ordered.append(span)
    if ordered:
        ordered[0]["start"] = 0.0
        if duration > 0:
            ordered[-1]["end"] = max(ordered[-1]["end"], duration)
    return ordered


def speech_clips(audio: np.ndarray, vad_parameters: dict[str, Any] | None) -> list[tuple[float, float]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(**(vad_parameters or {}))
    return [
        (chunk["start"] / SAMPLE_RATE, chunk["end"] / SAMPLE_RATE)
        for chunk in get_speech_timestamps(audio, options)
    ]


def span_clip_timestamps(
    span: dict[str, Any], speech: list[tuple[float, float]] | None
) -> list[float]:
    """Clip list in span-local seconds, so VAD survives the per-span decode."""
    origin = float(span["start"])
    length = max(0.0, float(span["end"]) - origin)
    if not speech:
        return [0.0, length]
    clips: list[float] = []
    for begin, finish in speech:
        start = max(begin, origin)
        end = min(finish, float(span["end"]))
        if end - start > 0.05:
            clips.extend([round(start - origin, 3), round(end - origin, 3)])
    return clips


def span_languages(spans: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for span in spans:
        if span["language"] not in seen:
            seen.append(span["language"])
    return seen
