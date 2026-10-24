from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from .config import WORKSPACE
from .cuda import cuda_diagnostics, cuda_runtime_available
from .language_map import (
    build_language_map,
    detect_phrase_languages,
    intersect_clips,
    known_language_codes,
    load_audio,
    normalize_spans,
    parse_language_request,
    phrase_clips,
    span_clip_timestamps,
    span_languages,
    spans_from_phrases,
    speech_clips,
)
from .media import probe_duration
from .model_download import ensure_model
from .subtitles import normalize_cues
from .transcription_guard import (
    gauntlet_report,
    repair_boundary_words,
    segment_diagnostic,
    whisper_options,
    pathological_repetition,
)

MODEL_DIR = WORKSPACE / "models"
MODEL_DIR.mkdir(exist_ok=True)


class TranscriptionUnavailable(RuntimeError):
    pass


class TranscriptionCancelled(RuntimeError):
    pass


def capability_status() -> dict[str, Any]:
    try:
        import faster_whisper  # noqa: F401

        installed = True
    except Exception:
        installed = False
    cuda = False
    if installed:
        try:
            import ctranslate2

            cuda = ctranslate2.get_cuda_device_count() > 0 and cuda_runtime_available()
        except Exception:
            cuda = False
    diagnostics = cuda_diagnostics() if installed else {
        "available": False,
        "deviceCount": 0,
        "runtimeAvailable": False,
        "reason": "Local transcription components are not installed",
        "error": "",
    }
    return {"available": installed, "cuda": cuda, "gpu": diagnostics}


def _device_config() -> tuple[str, str]:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0 and cuda_runtime_available():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


@lru_cache(maxsize=3)
def _load_model(model_source: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - tested via capability endpoint
        raise TranscriptionUnavailable(
            "faster-whisper is not installed. Run the AI dependency installer."
        ) from exc
    model = WhisperModel(
        model_source,
        device=device,
        compute_type=compute_type,
    )
    from .long_audio import BoundedFeatureExtractor

    model.feature_extractor = BoundedFeatureExtractor(model.feature_extractor)
    return model


def _punctuation_break(text: str) -> bool:
    return bool(re.search(r"[.!?;:,]$", text.strip()))


def _hard_stop(text: str) -> bool:
    return bool(re.search(r"[.!?]$", text.strip()))


BREATH_GAP = 0.42       # a pause this long always ends a phrase
LONG_GAP = 0.90         # a pause this long is a section break

# Japanese and Chinese are written without spaces, and Whisper returns one word
# token per character group. Joining those with spaces puts "夜 に 溶 けて ゆ く"
# on screen instead of the line as it is written.
_UNSPACED_SCRIPT = re.compile(
    r"[　-〿぀-ヿ㐀-䶿一-鿿豈-﫿！-｠ｦ-ﾟ]"
)


def _join_words(words: list[dict[str, Any]]) -> str:
    text = ""
    for word in words:
        token = str(word["text"])
        if not token:
            continue
        if text and not (_UNSPACED_SCRIPT.match(text[-1]) and _UNSPACED_SCRIPT.match(token[0])):
            text += " "
        text += token
    return text


def _break_score(words: list[dict[str, Any]], index: int) -> float:
    """How good a phrase break after words[index] would be.

    Silence between two sung words is the single strongest cue for where a
    lyric line ends, so gap length dominates; punctuation is a tie-breaker.
    """
    if index >= len(words) - 1:
        return 0.0
    gap = words[index + 1]["start"] - words[index]["end"]
    score = min(gap, 1.2) * 10.0
    if _hard_stop(words[index]["text"]):
        score += 4.0
    elif _punctuation_break(words[index]["text"]):
        score += 2.0
    # Whisper capitalises the first word of each new lyric line, so a capital
    # following an unpunctuated lowercase word marks a line break in the lyrics.
    following = words[index + 1]["text"]
    current = words[index]["text"]
    if following[:1].isupper() and current[-1:].islower():
        score += 3.5
    # Avoid leaving a single dangling word on the next line.
    if index == len(words) - 2:
        score -= 3.0
    return score


def _chunk_words(
    words: list[dict[str, Any]],
    max_words: int,
    max_chars: int,
    max_duration: float,
    min_words: int = 2,
) -> list[list[dict[str, Any]]]:
    """Split one Whisper segment into singable phrases.

    Greedy filling produces long lines followed by orphan tails ("...posters
    from" / "the walls"). Instead this runs a small dynamic program over every
    legal set of break points and picks the one that balances line length while
    landing the breaks on the pauses the singer actually took.
    """
    total = len(words)
    if total <= min_words:
        return [words] if words else []

    target_chars = max_chars * 0.74
    lengths = [len(word["text"]) for word in words]
    prefix = [0]
    for length in lengths:
        prefix.append(prefix[-1] + length + 1)

    def chunk_cost(begin: int, end: int) -> float:
        count = end - begin
        chars = prefix[end] - prefix[begin] - 1
        duration = words[end - 1]["end"] - words[begin]["start"]
        if count > max_words or chars > max_chars or duration > max_duration:
            return float("inf")
        # Quadratic pull toward the target line length keeps phrases even.
        cost = ((chars - target_chars) / target_chars) ** 2 * 10.0
        if count < min_words and end != total:
            cost += 6.0
        if duration > max_duration * 0.85:
            cost += 2.0
        return cost

    INF = float("inf")
    best = [INF] * (total + 1)
    back = [0] * (total + 1)
    best[0] = 0.0

    for end in range(1, total + 1):
        for begin in range(max(0, end - max_words), end):
            if best[begin] == INF:
                continue
            cost = chunk_cost(begin, end)
            if cost == INF:
                continue
            # Reward breaking where there is silence after words[end - 1].
            bonus = _break_score(words, end - 1) if end < total else 0.0
            value = best[begin] + cost - bonus
            if value < best[end]:
                best[end] = value
                back[end] = begin

    if best[total] == INF:
        # Nothing legal (one enormous word, or a very long held line): fall back
        # to fixed-size slices so the caller always gets usable cues.
        return [words[i : i + max_words] for i in range(0, total, max_words)]

    cuts: list[int] = []
    cursor = total
    while cursor > 0:
        cuts.append(cursor)
        cursor = back[cursor]
    cuts.reverse()

    chunks: list[list[dict[str, Any]]] = []
    begin = 0
    for cut in cuts:
        chunks.append(words[begin:cut])
        begin = cut
    return chunks


def _merge_orphans(
    chunks: list[list[dict[str, Any]]], max_words: int, max_chars: int, max_duration: float
) -> list[list[dict[str, Any]]]:
    """Fold one-word leftovers into whichever neighbour they were sung with."""
    merged: list[list[dict[str, Any]]] = []
    for chunk in chunks:
        if (
            merged
            and len(chunk) == 1
            and len(merged[-1]) + 1 <= max_words
            and sum(len(w["text"]) + 1 for w in merged[-1] + chunk) <= max_chars + 6
            and chunk[-1]["end"] - merged[-1][0]["start"] <= max_duration + 0.8
            and chunk[0]["start"] - merged[-1][-1]["end"] < BREATH_GAP
        ):
            merged[-1] = merged[-1] + chunk
        else:
            merged.append(chunk)
    return merged


def _reflow_segments(
    segments: list[dict[str, Any]],
    max_words: int = 8,
    max_chars: int = 42,
    max_duration: float = 4.6,
) -> list[dict[str, Any]]:
    """Turn Whisper segments into phrase cues that break where the singer breathes.

    Whisper segment boundaries stay hard boundaries: a cue may be split inside a
    segment but never merged across two of them.
    """
    cues: list[dict[str, Any]] = []
    cue_index = 0
    last_end = 0.0

    for segment in segments:
        raw_words = segment.get("words") or []
        segment_language = segment.get("language")

        words = sorted(
            [
                {
                    "text": str(w.get("text", "")).strip(),
                    "start": float(w.get("start", segment["start"])),
                    "end": float(w.get("end", segment["end"])),
                }
                for w in raw_words
                if str(w.get("text", "")).strip()
            ],
            key=lambda w: (w["start"], w["end"]),
        )

        # No word timestamps: keep Whisper's own segment intact.
        if not words:
            start = max(last_end, float(segment["start"]))
            end = max(start + 0.1, float(segment["end"]))
            cue_index += 1
            cues.append(
                {
                    "id": f"cue-{cue_index}",
                    "start": start,
                    "end": end,
                    "text": str(segment["text"]).strip(),
                    "words": [],
                    "language": segment_language,
                }
            )
            last_end = end
            continue

        previous_end = max(last_end, words[0]["start"])
        for word in words:
            word["start"] = max(word["start"], previous_end)
            word["end"] = max(word["start"] + 0.03, word["end"])
            previous_end = word["end"]

        chunks = _merge_orphans(
            _chunk_words(words, max_words, max_chars, max_duration),
            max_words,
            max_chars,
            max_duration,
        )

        for chunk in chunks:
            if not chunk:
                continue
            start = max(last_end, chunk[0]["start"])
            end = max(start + 0.08, chunk[-1]["end"])

            fixed_words = []
            previous = start
            for word in chunk:
                ws = max(previous, word["start"])
                we = max(ws + 0.03, word["end"])
                fixed_words.append({"text": word["text"], "start": ws, "end": we})
                previous = we

            cue_index += 1
            cues.append(
                {
                    "id": f"cue-{cue_index}",
                    "start": start,
                    "end": max(end, fixed_words[-1]["end"]),
                    "text": _join_words(fixed_words),
                    "words": fixed_words,
                    "language": segment_language,
                }
            )
            last_end = cues[-1]["end"]

    return normalize_cues(cues)


def _guard(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check and cancel_check():
        raise TranscriptionCancelled("Transcription cancelled")


def _decode_pass(
    model: Any,
    source: Any,
    options: dict[str, Any],
    *,
    offset: float = 0.0,
    language: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
    on_time: Callable[[float], None] | None = None,
    recover_loops: bool = True,
) -> dict[str, Any]:
    """Run one Whisper decode and return its segments in track time."""
    try:
        segments, info = model.transcribe(source, **options)
    except TypeError as error:
        if not isinstance(source, (str, Path)) or "metadata_errors" not in str(error) or "unexpected keyword" not in str(error):
            raise
        source = load_audio(Path(source))
        _guard(cancel_check)
        segments, info = model.transcribe(source, **options)
    collected: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    repaired_words = 0
    loops: list[tuple[int, int, float, float]] = []
    try:
        for segment in segments:
            _guard(cancel_check)
            start = float(segment.start) + offset
            end = float(segment.end) + offset
            words: list[dict[str, Any]] = []
            for word in segment.words or []:
                token = str(word.word).strip()
                if not token:
                    continue
                words.append(
                    {
                        "text": token,
                        "start": (float(word.start) if word.start is not None else float(segment.start)) + offset,
                        "end": (float(word.end) if word.end is not None else float(segment.end)) + offset,
                    }
                )
            segment_text = str(segment.text).strip()
            words, repaired = repair_boundary_words(segment_text, words, start, end)
            repaired_words += repaired
            diagnostic = segment_diagnostic(segment)
            diagnostic["start"] = round(start, 3)
            diagnostic["end"] = round(end, 3)
            diagnostics.append(diagnostic)
            collected.append(
                {
                    "start": start,
                    "end": max(end, *(word["end"] for word in words)) if words else end,
                    "text": segment_text,
                    "words": words,
                    "language": language or getattr(info, "language", None),
                }
            )
            if recover_loops and pathological_repetition(segment):
                loops.append((len(collected)-1,len(diagnostics)-1,float(segment.start),float(segment.end)))
            if on_time:
                on_time(end)
    finally:
        close = getattr(segments, "close", None)
        if callable(close):
            close()
    if loops:
        audio = load_audio(Path(source)) if isinstance(source, (str, Path)) else source
        for index, diagnostic_index, begin, finish in reversed(loops):
            _guard(cancel_check)
            left=max(0,begin-.35); right=min(len(audio)/16000,finish+.35)
            retry_options=dict(options)
            retry_options.update(condition_on_previous_text=False,vad_filter=False)
            retry_options.pop("clip_timestamps",None); retry_options.pop("vad_parameters",None)
            retry = _decode_pass(model,audio[round(left*16000):round(right*16000)],retry_options,
                offset=offset+left,language=language,cancel_check=cancel_check,recover_loops=False)
            recovered=[]
            for candidate, check in zip(retry["segments"],retry["diagnostics"]):
                if check["unstable"] or candidate["end"] <= offset+begin or candidate["start"] >= offset+finish:
                    continue
                words=[w for w in candidate["words"] if offset+begin <= w["start"] < offset+finish]
                if words:
                    words=[{**w,"end":min(offset+finish,w["end"])} for w in words]
                    recovered.append({**candidate,"start":words[0]["start"],"end":min(offset+finish,words[-1]["end"]),
                                      "text":_join_words(words),"words":words})
            collected[index:index+1]=recovered
            diagnostics[diagnostic_index]["loopRecovery"]="recovered" if recovered else "unresolved"
            if recovered: diagnostics[diagnostic_index]["unstable"]=False
            diagnostics[diagnostic_index]["discardedRunawayTokens"]=True
    return {
        "segments": collected,
        "diagnostics": diagnostics,
        "repairedWords": repaired_words,
        "info": info,
    }


def _span_options(span_language: str, vad_filter: bool, clips: list[float]) -> dict[str, Any]:
    """Decode options for one language span.

    ``clip_timestamps`` makes faster-whisper skip its own VAD, so speech mode
    passes the voiced ranges of this span in as the clips instead.
    """
    options = whisper_options(span_language, vad_filter)
    options["vad_filter"] = False
    options.pop("vad_parameters", None)
    options["clip_timestamps"] = clips
    return options


def _decode_language_map(
    model: Any,
    audio: Any,
    spans: list[dict[str, Any]],
    *,
    vad_filter: bool,
    speech: list[tuple[float, float]] | None,
    duration: float,
    cancel_check: Callable[[], bool] | None,
    progress: Callable[[float, str], None] | None,
    low: float,
    high: float,
) -> dict[str, Any]:
    """Decode every span of a language map and stitch the results together."""
    if len(spans) <= 1:
        # One language across the whole track: a single conditioned pass reads
        # better than stitching, and detection already used every window rather
        # than only the opening thirty seconds.
        only = spans[0]["language"] if spans else "auto"
        return _decode_pass(
            model,
            audio,
            whisper_options(only, vad_filter),
            language=only if spans else None,
            cancel_check=cancel_check,
            on_time=(
                lambda end: progress(
                    min(high, low + (high - low) * end / duration),
                    f"Transcribed {end:.1f}s of {duration:.1f}s",
                )
            )
            if progress and duration > 0
            else None,
        )

    segments: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    repaired_words = 0
    info: Any = None
    covered = sum(span["end"] - span["start"] for span in spans) or 1.0
    done = 0.0
    for index, span in enumerate(spans):
        _guard(cancel_check)
        clips = span_clip_timestamps(span, speech)
        begin = int(span["start"] * 16000)
        finish = min(len(audio), int(span["end"] * 16000))
        length = span["end"] - span["start"]
        if finish - begin < 1600 or not clips:
            done += length
            continue
        if progress:
            progress(
                low + (high - low) * (done / covered),
                f"Transcribing {span['language']} from {span['start']:.0f}s to {span['end']:.0f}s"
                f" ({index + 1}/{len(spans)})",
            )
        outcome = _decode_pass(
            model,
            audio[begin:finish],
            _span_options(span["language"], vad_filter, clips),
            offset=span["start"],
            language=span["language"],
            cancel_check=cancel_check,
        )
        segments.extend(outcome["segments"])
        diagnostics.extend(outcome["diagnostics"])
        repaired_words += outcome["repairedWords"]
        info = info or outcome["info"]
        done += length
    return {
        "segments": segments,
        "diagnostics": diagnostics,
        "repairedWords": repaired_words,
        "info": info,
    }


def _language_mode_label(mode: str, languages: list[str]) -> str:
    if mode == "override":
        return f"your language map ({', '.join(languages)})" if languages else "your language map"
    if mode == "fixed":
        return f"fixed language ({languages[0]})" if languages else "fixed language"
    if mode == "single":
        return "automatic single language"
    if len(languages) > 1:
        return f"multi-language ({', '.join(languages)})"
    return f"automatic single language ({languages[0]})" if languages else "automatic single language"


def transcribe_audio(
    path: Path,
    model_name: str = "base",
    language: str = "auto",
    vad_filter: bool = False,
    progress: Callable[..., None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    language_spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not capability_status()["available"]:
        raise TranscriptionUnavailable(
            "Local transcription is optional and not installed. Run install_ai.* or pip install -r requirements-ai.txt."
        )

    allowed_models = {"tiny", "base", "small", "medium", "large-v3", "distil-large-v3"}
    if model_name not in allowed_models:
        raise ValueError(f"Unknown model: {model_name}")

    plan = parse_language_request(language)
    override = normalize_spans(language_spans, 0.0)
    codes = known_language_codes()
    requested_codes = plan["codes"] + [span["language"] for span in override]
    unknown = [code for code in requested_codes if codes and code not in codes]
    if unknown:
        raise ValueError(f"Unknown language code: {', '.join(sorted(set(unknown)))}")

    model_source = ensure_model(
        model_name,
        MODEL_DIR,
        progress=progress,
        cancel_check=cancel_check,
    )
    _guard(cancel_check)
    device, compute_type = _device_config()
    if progress:
        accelerator = "NVIDIA GPU" if device == "cuda" else "CPU"
        progress(
            0.14,
            f"Loading Whisper {model_name} on {accelerator}",
            {"phase": "model-load", "device": device, "etaSeconds": None},
        )
    model = _load_model(str(model_source), device, compute_type)
    _guard(cancel_check)
    duration = probe_duration(path) or 0.0

    raw_segments: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    repaired_words = 0
    spans: list[dict[str, Any]] = []
    info: Any = None

    if not override and plan["mode"] in {"fixed", "single"}:
        requested = plan["codes"][0] if plan["mode"] == "fixed" else "auto"
        outcome = _decode_pass(
            model,
            str(path),
            whisper_options(requested, vad_filter),
            language=plan["codes"][0] if plan["mode"] == "fixed" else None,
            cancel_check=cancel_check,
            on_time=(
                lambda end: progress(min(0.96, end / duration), f"Transcribed {end:.1f}s of {duration:.1f}s")
            )
            if progress and duration > 0
            else None,
        )
        raw_segments = outcome["segments"]
        diagnostics = outcome["diagnostics"]
        repaired_words = outcome["repairedWords"]
        info = outcome["info"]
        detected = getattr(info, "language", None) or requested
        languages = [detected]
        span_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
    else:
        if progress:
            progress(0.03, "Applying your language map" if override else "Listening for language changes")
        audio = load_audio(path)
        duration = duration or len(audio) / 16000
        if override:
            spans = normalize_spans(override, duration)
        else:
            spans = build_language_map(
                model,
                audio,
                allowed=plan["codes"] or None,
                cancel_check=cancel_check,
                progress=(lambda ratio: progress(0.03 + 0.11 * ratio, "Mapping languages")) if progress else None,
            )
        _guard(cancel_check)
        languages = span_languages(spans)
        speech = speech_clips(audio, whisper_options("auto", True)["vad_parameters"]) if vad_filter else None

        outcome = _decode_language_map(
            model,
            audio,
            spans,
            vad_filter=vad_filter,
            speech=speech,
            duration=duration,
            cancel_check=cancel_check,
            progress=progress,
            low=0.14,
            high=0.54 if plan["mode"] == "map" and not override else 0.96,
        )

        # Second pass. The window map cannot see a switch that lands between two
        # sung lines, so the phrases the first pass found are re-identified one
        # by one and anything that disagrees is decoded again in its own
        # language. A track that turns out to be consistent skips this entirely.
        if not override:
            first_cues = _reflow_segments(outcome["segments"])
            decisions = detect_phrase_languages(
                model,
                audio,
                first_cues,
                span_languages(spans),
                cancel_check=cancel_check,
                progress=(lambda ratio: progress(0.54 + 0.06 * ratio, "Checking each line's language"))
                if progress
                else None,
            )
            _guard(cancel_check)
            corrections = sum(
                1
                for decision, cue in zip(decisions, first_cues)
                if decision["language"] != cue.get("language")
            )
            if corrections:
                refined = spans_from_phrases(first_cues, decisions, duration)
                if progress:
                    progress(0.6, f"Re-reading {corrections} line(s) in another language")
                outcome = _decode_language_map(
                    model,
                    audio,
                    refined,
                    vad_filter=vad_filter,
                    speech=intersect_clips(phrase_clips(first_cues, duration), speech),
                    duration=duration,
                    cancel_check=cancel_check,
                    progress=progress,
                    low=0.6,
                    high=0.96,
                )
                spans = refined
                languages = span_languages(spans)

        raw_segments = outcome["segments"]
        diagnostics = outcome["diagnostics"]
        repaired_words = outcome["repairedWords"]
        info = outcome["info"]
        covered = sum(span["end"] - span["start"] for span in spans) or 1.0
        span_probability = (
            sum(span["probability"] * (span["end"] - span["start"]) for span in spans) / covered
        )

    _guard(cancel_check)
    raw_segments.sort(key=lambda segment: (segment["start"], segment["end"]))
    for index, segment in enumerate(raw_segments):
        segment["id"] = f"segment-{index + 1}"

    cues = _reflow_segments(raw_segments)
    # Which language the song is mostly in, measured over the lines that were
    # actually sung; a span map also covers intros and instrumental tails.
    sung: dict[str, float] = {}
    for cue in cues:
        code = cue.get("language")
        if code:
            sung[code] = sung.get(code, 0.0) + cue["end"] - cue["start"]
    dominant = (
        max(sung.items(), key=lambda item: item[1])[0]
        if sung
        else (languages[0] if languages else "auto")
    )
    language_mode = _language_mode_label("override" if override else plan["mode"], languages)
    quality = gauntlet_report(diagnostics, repaired_words, language_mode)
    if progress:
        progress(1.0, "Transcription complete")
    return {
        "cues": cues,
        "rawSegments": normalize_cues(raw_segments),
        "language": dominant,
        "languageMode": language_mode,
        "languages": languages,
        "languageSpans": spans,
        "detectedLanguage": dominant,
        "languageProbability": float(span_probability),
        "transcriptionGauntlet": quality,
        "segmentDiagnostics": diagnostics,
        "options": {
            "task": "transcribe",
            "languageMode": quality["languageMode"],
            "languageRequest": plan["mode"],
            "vadFilter": bool(vad_filter),
            "adaptiveTemperatureFallback": True,
        },
        "duration": duration,
        "device": device,
        "computeType": compute_type,
        "model": model_name,
    }
