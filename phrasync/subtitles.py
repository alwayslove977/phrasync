from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SRT_BLOCK_RE = re.compile(
    r"(?:^|\n)\s*(?:\d+\s*\n)?"
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})[^\n]*\n"
    r"(?P<text>.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)
LRC_RE = re.compile(r"\[(?P<min>\d{1,3}):(?P<sec>\d{1,2}(?:[.:]\d{1,3})?)\](?P<text>.*)")


def parse_timestamp(value: str) -> float:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    return float(value)


def format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_lrc_time(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    minutes, rem = divmod(total_cs, 6000)
    secs, centis = divmod(rem, 100)
    return f"[{minutes:02d}:{secs:02d}.{centis:02d}]"


def normalize_cue(cue: dict[str, Any], index: int = 0) -> dict[str, Any]:
    start = max(0.0, float(cue.get("start", 0.0)))
    end = max(start + 0.05, float(cue.get("end", start + 2.0)))
    text = str(cue.get("text", "")).replace("\r\n", "\n").strip()
    words: list[dict[str, Any]] = []
    for word in cue.get("words", []) or []:
        token = str(word.get("text", word.get("word", ""))).strip()
        if not token:
            continue
        w_start = max(start, float(word.get("start", start)))
        w_end = min(end, max(w_start + 0.01, float(word.get("end", w_start + 0.2))))
        words.append({"text": token, "start": w_start, "end": w_end})
    normalized = {
        "id": str(cue.get("id") or f"cue-{index + 1}"),
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
        "words": words,
    }
    # Transcription tags each cue with the language it was decoded in; imported
    # cues have no tag and stay untouched.
    if cue.get("language"):
        normalized["language"] = str(cue["language"])
    if cue.get("manual") is True:
        normalized["manual"] = True
    return normalized


def normalize_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = [normalize_cue(cue, index) for index, cue in enumerate(cues)]
    cleaned = [cue for cue in cleaned if cue["text"]]
    cleaned.sort(key=lambda cue: (cue["start"], cue["end"]))
    for index, cue in enumerate(cleaned):
        cue["id"] = cue.get("id") or f"cue-{index + 1}"
    return cleaned


def parse_srt(text: str) -> list[dict[str, Any]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    cues: list[dict[str, Any]] = []
    for index, match in enumerate(SRT_BLOCK_RE.finditer(normalized)):
        cue_text = re.sub(r"<[^>]+>", "", match.group("text")).strip()
        cues.append(
            normalize_cue(
                {
                    "id": f"cue-{index + 1}",
                    "start": parse_timestamp(match.group("start")),
                    "end": parse_timestamp(match.group("end")),
                    "text": cue_text,
                },
                index,
            )
        )
    return normalize_cues(cues)


def parse_vtt(text: str) -> list[dict[str, Any]]:
    stripped = re.sub(r"^WEBVTT[^\n]*\n+", "", text.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r"(\d{1,2}:\d{2})\.(\d{3})", r"00:\1.\2", stripped)
    return parse_srt(stripped)


def parse_lrc(text: str, default_duration: float = 3.0) -> list[dict[str, Any]]:
    timestamp_re = re.compile(
        r"\[(?P<min>\d{1,3}):(?P<sec>\d{1,2}(?:[.:]\d{1,3})?)\]"
    )
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[dict[str, Any]] = []

    def stamp(match: re.Match[str]) -> float:
        return int(match.group("min")) * 60 + float(match.group("sec").replace(":", "."))

    # Enhanced/character LRC: each timestamp starts the text following it.
    for line in lines:
        matches = list(timestamp_re.finditer(line))
        if len(matches) < 2:
            continue
        words: list[dict[str, Any]] = []
        for pos, match in enumerate(matches):
            token = line[match.end():matches[pos + 1].start() if pos + 1 < len(matches) else len(line)].strip()
            if not token:
                continue
            start = stamp(match)
            end = stamp(matches[pos + 1]) if pos + 1 < len(matches) else start + default_duration
            words.append({
                "text": token,
                "start": start,
                "end": max(start + 0.01, end),
            })
        if not words:
            continue
        cue_start = words[0]["start"]
        cue_end = max(cue_start + 0.05, max(word["end"] for word in words))
        cues.append(normalize_cue({
            "id": f"cue-{len(cues) + 1}",
            "start": cue_start,
            "end": cue_end,
            "text": "".join(word["text"] for word in words),
            "words": words,
        }, len(cues)))

    if cues:
        return normalize_cues(cues)

    # Standard line-level LRC fallback.
    points: list[tuple[float, str]] = []
    for line in lines:
        match = LRC_RE.match(line.strip())
        if not match:
            continue
        start = int(match.group("min")) * 60 + float(match.group("sec").replace(":", "."))
        lyric = match.group("text").strip()
        if lyric:
            points.append((start, lyric))
    points.sort(key=lambda item: item[0])
    for index, (start, lyric) in enumerate(points):
        next_start = points[index + 1][0] if index + 1 < len(points) else start + default_duration
        cues.append(normalize_cue({
            "id": f"cue-{index + 1}",
            "start": start,
            "end": max(start + 0.35, next_start - 0.03),
            "text": lyric,
        }, index))
    return normalize_cues(cues)


def parse_plain(text: str, duration: float | None = None, seconds_per_line: float = 3.0) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines:
        return []
    total = max(seconds_per_line * len(lines), duration or 0.0)
    slot = total / len(lines)
    cues = [
        {
            "id": f"cue-{index + 1}",
            "start": index * slot,
            "end": (index + 1) * slot - 0.03,
            "text": line,
            "words": [],
        }
        for index, line in enumerate(lines)
    ]
    return normalize_cues(cues)


def parse_lyrics_file(path: Path, duration: float | None = None) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(text)
    if suffix == ".vtt":
        return parse_vtt(text)
    if suffix == ".lrc":
        return parse_lrc(text)
    if suffix == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("cues", [])
        if not isinstance(data, list):
            raise ValueError("Lyrics JSON must contain a cue list")
        return normalize_cues(data)
    return parse_plain(text, duration=duration)


def cues_to_srt(cues: list[dict[str, Any]]) -> str:
    blocks = []
    for index, cue in enumerate(normalize_cues(cues), 1):
        blocks.append(
            f"{index}\n{format_srt_time(cue['start'])} --> {format_srt_time(cue['end'])}\n{cue['text']}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def cues_to_lrc(cues: list[dict[str, Any]]) -> str:
    return "\n".join(f"{format_lrc_time(cue['start'])}{cue['text'].replace(chr(10), ' / ')}" for cue in normalize_cues(cues))


def estimate_duration(cues: list[dict[str, Any]], fallback: float = 8.0) -> float:
    cleaned = normalize_cues(cues)
    return max(fallback, max((cue["end"] for cue in cleaned), default=0.0) + 0.5)


def format_vtt_time(seconds: float) -> str:
    return format_srt_time(max(0.0, seconds)).replace(",", ".")


def format_ass_time(seconds: float) -> str:
    total = max(0.0, seconds)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    whole = total % 60
    return f"{hours}:{minutes:02d}:{whole:05.2f}"


def cues_to_vtt(cues: list[dict[str, Any]]) -> str:
    """WebVTT, the browser-native caption format."""
    blocks = ["WEBVTT", ""]
    for index, cue in enumerate(normalize_cues(cues), start=1):
        blocks.append(str(index))
        blocks.append(f"{format_vtt_time(cue['start'])} --> {format_vtt_time(cue['end'])}")
        blocks.append(str(cue["text"]))
        blocks.append("")
    return "\n".join(blocks)


def cues_to_enhanced_lrc(cues: list[dict[str, Any]]) -> str:
    """Enhanced LRC: per-word <mm:ss.xx> tags, the karaoke-player standard.

    Plain LRC throws the word timings away, which is most of what this app
    knows about a song.
    """
    from .kinetic import cue_words

    lines = []
    for cue in normalize_cues(cues):
        words = cue_words(cue)
        if not words:
            lines.append(f"{format_lrc_time(cue['start'])}{cue['text']}")
            continue
        parts = [format_lrc_time(cue['start'])]
        for word in words:
            parts.append("<" + format_lrc_time(word["start"]).strip("[]") + ">" + word["text"] + " ")
        lines.append("".join(parts).rstrip())
    return "\n".join(lines) + "\n"


def cues_to_ass(cues: list[dict[str, Any]], style: dict[str, Any] | None = None,
                canvas: dict[str, Any] | None = None) -> str:
    """Advanced SubStation Alpha with \k karaoke timing.

    This is the one interchange format that carries word-level timing into a
    real video pipeline — Aegisub, mpv, ffmpeg burn-in, Premiere and Resolve via
    import — so the sync work survives outside Phrasync.
    """
    from .kinetic import cue_words

    style = style or {}
    canvas = canvas or {}
    width = int(canvas.get("width", 1920) or 1920)
    height = int(canvas.get("height", 1080) or 1080)
    reference = min(width, height)
    size = max(12, round(float(style.get("fontSize", 160) or 160) * reference / 1080 * 0.42))

    def ass_colour(value: str, fallback: str) -> str:
        raw = str(value or fallback).strip().lstrip("#")
        if len(raw) == 3:
            raw = "".join(c * 2 for c in raw)
        if len(raw) != 6:
            raw = fallback.lstrip("#")
        # ASS stores &HAABBGGRR, so the RGB channels are reversed.
        return f"&H00{raw[4:6]}{raw[2:4]}{raw[0:2]}".upper()

    primary = ass_colour(style.get("accentColor"), "ff3d7f")
    secondary = ass_colour(style.get("textColor"), "ffffff")
    outline = ass_colour(style.get("strokeColor"), "05040c")
    font = {"impact": "Impact", "condensed": "Arial Narrow", "modern": "Arial",
            "serif": "Georgia", "mono": "Consolas", "bebas": "Bebas Neue",
            "geometric": "Montserrat", "rounded": "Poppins", "poster": "Nexa",
            "techno": "DIN Pro", "script": "Segoe Script",
            "jgothic": "Yu Gothic"}.get(style.get("fontPreset", "impact"), "Arial")

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour,"
        " BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,"
        " BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Phrasync,{font},{size},{primary},{secondary},{outline},&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,{max(1, round(size * 0.06))},{max(0, round(size * 0.04))},"
        f"2,{round(width * 0.06)},{round(width * 0.06)},{round(height * 0.08)},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    uppercase = bool(style.get("uppercase", True))
    for cue in normalize_cues(cues):
        words = cue_words(cue)
        if words:
            chunks = []
            for index, word in enumerate(words):
                following = words[index + 1]["start"] if index + 1 < len(words) else cue["end"]
                # \k is expressed in centiseconds.
                duration = max(1, round((following - word["start"]) * 100))
                token = word["text"].upper() if uppercase else word["text"]
                chunks.append(chr(123) + chr(92) + f"k{duration}" + chr(125) + f"{token} ")
            body = "".join(chunks).rstrip()
        else:
            body = cue["text"].upper() if uppercase else cue["text"]
        body = body.replace(chr(10), chr(92) + "N")
        header.append(
            f"Dialogue: 0,{format_ass_time(cue['start'])},{format_ass_time(cue['end'])},"
            f"Phrasync,,0,0,0,,{body}"
        )
    return "\n".join(header) + "\n"
