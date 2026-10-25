"""Kinetic lyric engine — Python mirror of static/kinetic.js.

Both files implement the same timing and per-word animation math so the offline
MP4 render matches what the browser preview shows. Any change here must be
mirrored there (and vice versa); tests/test_kinetic.py pins the shared values.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Any


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return min(maximum, max(minimum, value))


def mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_linear(t: float) -> float:
    return t


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_out_quint(t: float) -> float:
    return 1 - (1 - t) ** 5


def ease_out_expo(t: float) -> float:
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_in_out_cubic(t: float) -> float:
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def ease_out_back(t: float) -> float:
    c1 = 1.9
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    layout: str
    lead: float
    pending_alpha: float
    hold: str
    tail: float
    enter: str
    active: str
    past: str
    case_transform: str
    line_height: float
    word_gap: float
    beat_react: float
    size_scale: float = 1.0


PRESETS: dict[str, Preset] = {
    "kinetic-slam": Preset("kinetic-slam", "Kinetic Slam", "inline", 0.10, 0.0, "cue", 0.30, "slam", "accent", "dim", "upper", 0.92, 0.20, 0.55, 1.0),
    "neon-flux": Preset("neon-flux", "Neon Flux", "inline", 0.18, 0.0, "cue", 0.34, "blur", "glow", "fade", "upper", 1.00, 0.26, 0.35, 1.0),
    "focus-word": Preset("focus-word", "Focus Word", "focus", 0.05, 0.0, "word", 0.18, "snap", "accent", "hidden", "upper", 0.90, 0.00, 0.80, 1.34),
    "cascade": Preset("cascade", "Cascade", "cascade", 0.12, 0.0, "cue", 0.32, "rise", "accent", "recede", "upper", 0.98, 0.10, 0.30, 1.0),
    "wipe-fill": Preset("wipe-fill", "Wipe Fill", "inline", 0.0, 0.42, "cue", 0.26, "none", "wipe", "filled", "upper", 1.02, 0.24, 0.15, 1.0),
    "bold-stack": Preset("bold-stack", "Bold Stack", "stack", 0.09, 0.0, "cue", 0.30, "pop", "accent", "none", "upper", 0.86, 0.18, 0.25, 1.0),
    "minimal": Preset("minimal", "Minimal Caption", "inline", 0.14, 0.0, "cue", 0.26, "fade", "accent", "none", "none", 1.16, 0.26, 0.0, 0.5),
}

LEGACY_PRESETS = {"center-punch": "kinetic-slam", "karaoke": "wipe-fill", "neon": "neon-flux"}
PRESETS["spiral"] = replace(PRESETS["focus-word"], id="spiral", label="Spiral Flight", enter="fade", lead=0, tail=.25)
PRESETS["constellation"] = replace(PRESETS["neon-flux"], id="constellation", label="Word Constellation", layout="focus", pending_alpha=.18, lead=0)


def resolved_preset(style: dict[str, Any]) -> Preset:
    """Preset with the project's own timing overrides applied.

    ``style["wordLead"]`` is how far ahead of the sung syllable a word may start
    its entry animation, in seconds. Zero means it appears exactly on the beat.
    """
    base = get_preset((style or {}).get("preset"))
    lead = (style or {}).get("wordLead")
    try:
        value = float(lead)
    except (TypeError, ValueError):
        return base
    return replace(base, lead=max(0.0, min(0.5, value)))


def get_preset(preset_id: str | None) -> Preset:
    if preset_id in PRESETS:
        return PRESETS[preset_id]
    mapped = LEGACY_PRESETS.get(preset_id or "")
    if mapped:
        return PRESETS[mapped]
    return PRESETS["kinetic-slam"]


# --------------------------------------------------------------------------- #
# Word timing
# --------------------------------------------------------------------------- #

_LETTERS = re.compile(r"[^a-zà-öø-ÿ']")
_VOWELS = re.compile(r"[aeiouyà-åè-ïò-öù-ü]+")


def syllable_weight(token: str) -> float:
    letters = _LETTERS.sub("", str(token).lower())
    if not letters:
        return 1.0
    groups = _VOWELS.findall(letters)
    count = len(groups) if groups else 1
    if len(letters) > 3 and letters.endswith("e") and count > 1:
        count -= 1
    return max(1, count) + len(letters) * 0.06


def cue_words(cue: dict[str, Any]) -> list[dict[str, Any]]:
    """Word list for a cue, always timed and monotonic."""
    text = str(cue.get("text", "")).replace("\n", " ")
    token_re = re.compile(
        r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]"
        r"|[^\W_]+(?:['’][^\W_]+)*|[^\w\s]",
        re.UNICODE,
    )
    tokens = token_re.findall(text)
    if not tokens:
        return []
    stored = [w for w in (cue.get("words") or []) if str(w.get("text", "")).strip()]
    start = float(cue.get("start", 0.0) or 0.0)
    end = max(start + 0.2, float(cue.get("end", start + 1) or start + 1))

    if len(stored) == len(tokens):
        result = []
        previous = -math.inf
        for index, word in enumerate(stored):
            ws = max(previous, float(word.get("start", start)))
            we = max(ws + 0.06, float(word.get("end", ws + 0.25)))
            previous = ws
            result.append({"text": tokens[index], "start": ws, "end": we, "index": index})
        return result

    weights = [syllable_weight(token) for token in tokens]
    total = sum(weights) or 1.0
    span = end - start
    cursor = start
    result = []
    for index, token in enumerate(tokens):
        length = span * (weights[index] / total)
        result.append({"text": token, "start": cursor, "end": cursor + max(0.08, length), "index": index})
        cursor += length
    return result


# --------------------------------------------------------------------------- #
# Per-word state
# --------------------------------------------------------------------------- #


@dataclass
class WordState:
    visible: bool = True
    opacity: float = 1.0
    scale: float = 1.0
    dx: float = 0.0
    dy: float = 0.0
    rotate: float = 0.0
    blur: float = 0.0
    fill: float = 0.0
    fill_alpha: float = 1.0
    glow: float = 0.0
    role: str = "idle"
    weight_boost: float = 0.0
    tracking: float = 0.0


HIDDEN = WordState(visible=False, opacity=0.0, fill_alpha=0.0)


def word_state(
    word: dict[str, Any],
    cue: dict[str, Any],
    t: float,
    spec: Preset,
    beat: float = 0.0,
) -> WordState:
    start = float(word["start"])
    end = max(start + 0.06, float(word["end"]))
    cue_start = float(cue["start"])
    cue_end = float(cue["end"])
    pending = spec.pending_alpha
    # Match the browser: geometry and animation may be prepared early, but a
    # phrase cannot become readable before its first timed word is sung.
    first_timed = next((item for item in (cue.get("words") or [])
                        if str(item.get("text", "")).strip()), None)
    phrase_onset = max(cue_start, float(first_timed.get("start", cue_start)) if first_timed else cue_start)
    if t < phrase_onset or (spec.hold == "word" and t < start):
        return HIDDEN

    # Presets with a pending tint lay the whole line out from the cue start, so
    # the phrase stays optically centred while words light up one at a time.
    appear = min(cue_start - 0.05, start - spec.lead) if pending > 0 else start - spec.lead
    entry_from = start - spec.lead
    hold_until = end if spec.hold == "word" else cue_end
    vanish = hold_until + spec.tail

    if t < appear or t > vanish:
        return HIDDEN

    state = WordState()

    entry = clamp((t - entry_from) / spec.lead) if spec.lead > 0 else 1.0
    if t < entry_from:
        state.opacity = pending
    elif entry < 1:
        if spec.enter == "slam":
            e = ease_out_back(entry)
            state.scale = mix(1.22, 1, e)
            state.opacity = ease_out_cubic(clamp(entry * 1.9))
            state.blur = mix(6, 0, ease_out_quint(entry))
            state.dy = mix(-0.05, 0, e)
        elif spec.enter == "blur":
            e = ease_out_quint(entry)
            state.blur = mix(11, 0, e)
            state.opacity = ease_out_cubic(entry)
            state.scale = mix(1.08, 1, e)
        elif spec.enter == "snap":
            e = ease_out_expo(clamp(entry * 1.3))
            state.scale = mix(0.72, 1, e)
            state.opacity = clamp(entry * 3)
            state.rotate = mix(-3, 0, e)
        elif spec.enter == "rise":
            e = ease_out_quint(entry)
            state.dy = mix(0.5, 0, e)
            state.opacity = ease_out_cubic(entry)
            state.blur = mix(5, 0, e)
        elif spec.enter == "pop":
            e = ease_out_back(entry)
            state.scale = mix(0.8, 1, e)
            state.opacity = ease_out_cubic(clamp(entry * 1.6))
        elif spec.enter == "fade":
            state.opacity = ease_out_cubic(entry)
            state.dy = mix(0.12, 0, ease_out_cubic(entry))
        else:
            state.opacity = 1.0
        if pending > 0:
            state.opacity = max(state.opacity, pending)

    if t < start:
        state.role = "pending"
    elif t <= end:
        state.role = "active"
    else:
        state.role = "past"

    if state.role == "pending":
        state.fill = 0.0
    elif state.role == "active":
        p = clamp((t - start) / max(0.001, end - start))
        # The accent ramps over ~90 ms rather than snapping on, which reads as
        # singable rather than as a cut.
        ramp = ease_out_cubic(clamp((t - start) / 0.09))
        state.fill = p if spec.active == "wipe" else ramp
        attack = 1 - ease_out_quint(clamp((t - start) / 0.16))
        if spec.active == "accent":
            state.scale *= 1 + 0.09 * attack
            state.weight_boost = 1.0
            state.glow = 0.5 + 0.5 * attack
        elif spec.active == "glow":
            state.glow = 1.0
            state.scale *= 1 + 0.05 * attack
            state.weight_boost = 1.0
        elif spec.active == "wipe":
            state.glow = 0.35 * attack
            state.weight_boost = 1.0 if p > 0.02 else 0.0
    else:
        # Sung words hand the accent back to the base colour, which is what makes
        # the current word read as "current" instead of everything going monochrome.
        age = ease_in_out_cubic(clamp((t - end) / 0.7))
        # The accent dissolves uniformly instead of un-wiping from the right.
        state.fill = 1.0
        state.fill_alpha = (
            1.0 if spec.past == "filled" else 1 - ease_in_out_cubic(clamp((t - end) / 0.42))
        )
        if spec.past == "dim":
            state.opacity *= mix(1, 0.42, age)
            state.scale *= mix(1, 0.965, age)
        elif spec.past == "fade":
            state.opacity *= mix(1, 0.3, age)
            state.blur += mix(0, 1.6, age)
        elif spec.past == "recede":
            state.opacity *= mix(1, 0.32, age)
            state.scale *= mix(1, 0.86, age)
            state.dy -= mix(0, 0.22, ease_out_cubic(age))
        elif spec.past == "hidden":
            # Hard cut: the outgoing word must clear before the next one lands,
            # otherwise the two overlap on the same centre point.
            state.opacity *= 1 - ease_out_expo(clamp((t - end) / max(0.05, spec.tail)))
            state.scale *= mix(1, 1.18, age)
            state.blur += mix(0, 8, age)

    # --- phrase-level transition ---------------------------------------
    # The outgoing phrase lifts away while the incoming one rises into place.
    # Without that vertical separation the two overlap on the same centre and
    # the dissolve reads as illegible double exposure.
    if spec.tail > 0 and t > hold_until:
        out = clamp((t - hold_until) / spec.tail)
        if spec.past != "hidden":
            state.opacity *= 1 - ease_out_quint(out)
            state.dy -= 0.38 * ease_out_cubic(out)
            state.scale *= 1 - 0.07 * ease_out_cubic(out)
            state.blur += 3 * out
    elif spec.tail > 0:
        rise = 1 - ease_out_cubic(clamp((t - cue_start) / 0.30))
        state.dy += 0.30 * rise
        state.opacity *= 1 - 0.55 * rise * rise

    if spec.beat_react > 0 and beat > 0 and state.role == "active":
        pulse = beat * spec.beat_react
        state.scale *= 1 + 0.035 * pulse
        state.glow = min(1.0, state.glow + 0.25 * pulse)

    if spec.id == "spiral":
        progress = clamp((t-start)/min(.45, max(.08,end-start)*.7))
        radius = (1-ease_out_cubic(progress))*2.8
        angle = (1-progress)*math.pi*3
        state.dx += math.cos(angle)*radius
        state.dy += math.sin(angle)*radius
        state.scale *= .25+.75*ease_out_cubic(progress)
        state.rotate += (1-progress)*-35
    elif spec.id == "constellation" and state.role != "active":
        index = word.get("index", 0)
        phase = (index+1)*2.399963 + cue_start*.17
        state.dx += math.cos(phase)*(2.2+(index%3)*.8)
        state.dy += math.sin(phase)*(1.2+(index%2)*.7)
        state.scale *= .32+(index%3)*.07
        state.opacity *= .5
        state.rotate = math.sin(phase)*12
    state.opacity = clamp(state.opacity)
    return state


def active_cues(
    cues: list[dict[str, Any]], t: float, spec: Preset
) -> list[dict[str, Any]]:
    """Cues that have anything to draw at time t.

    A phrase keeps painting through its tail while the next one is already
    fading in, which is what turns the phrase change into a dissolve instead of
    a cut. Manually added cues can overlap transcribed ones; keep them visible.
    """
    lead = max(spec.lead, 0.05)
    result: list[dict[str, Any]] = []
    for cue in cues:
        if cue["start"] - lead > t:
            break
        if t <= cue["end"] + spec.tail:
            result.append(cue)
    def playing(cue: dict[str, Any]) -> bool:
        return cue["start"] <= t < cue["end"]

    # Manual text overrides the transcribed line at its own timestamp instead
    # of being layered underneath it.
    manual = [cue for cue in result if cue.get("manual") is True and playing(cue)]
    if manual:
        return manual[-1:]
    # Older projects did not tag manual cues; unlike transcribed phrases,
    # they usually have no stored word timings.
    playing_cues = [cue for cue in result if playing(cue)]
    if len(playing_cues) > 1:
        untimed = [cue for cue in playing_cues if not cue.get("words")]
        if untimed:
            return untimed[-1:]
    return result[-2:]


def focus_scale(text: str) -> float:
    """Per-word size multiplier for the one-word-at-a-time layout."""
    return clamp(7 / max(2, len(str(text))), 0.62, 1.5)


def beat_pulse(t: float, bpm: float, offset: float, decay: float = 0.22) -> float:
    if not bpm or bpm <= 0:
        return 0.0
    period = 60.0 / bpm
    phase = ((t - offset) % period + period) % period
    return math.exp(-phase / decay)


# Average glyph width as a fraction of the font size, per font family. Used to
# decide line breaks identically in the browser and the exporter.
FONT_WIDTH = {
    "impact": 0.44, "condensed": 0.46, "modern": 0.53, "serif": 0.51, "mono": 0.60,
    "bebas": 0.37, "geometric": 0.59, "rounded": 0.56, "poster": 0.53, "techno": 0.39, "script": 0.59, "jgothic": 0.6,
}


def char_budget(
    style: dict[str, Any], canvas: dict[str, Any], spec: Preset | None = None
) -> int:
    """How many characters fit on one line for this canvas and type size."""
    height = float(canvas.get("height", 1080) or 1080)
    width = float(canvas.get("width", 1920) or 1920)
    scale = spec.size_scale if spec else 1.0
    # Short edge, so a portrait canvas does not inflate the type.
    reference = min(height, width)
    font_px = float(style.get("fontSize", 160) or 160) * (reference / 1080) * scale
    usable = width * float(style.get("maxWidth", 88) or 88) / 100
    glyph = FONT_WIDTH.get(style.get("fontPreset", "impact"), 0.46) * font_px
    # math.floor(x + .5) matches JavaScript's Math.round, unlike Python's
    # banker's rounding, which would drift from the preview on exact halves.
    return max(6, math.floor(usable / max(1.0, glyph) + 0.5))


def _wrap(words: list[dict[str, Any]], limit: int) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = [[]]
    width = 0
    for word in words:
        cost = len(word["text"]) + 1
        if lines[-1] and width + cost > limit:
            lines.append([])
            width = 0
        lines[-1].append(word)
        width += cost
    return lines


def balanced_wrap(words: list[dict[str, Any]], budget: int) -> list[list[dict[str, Any]]]:
    """Greedy wrap, then re-wrap with an evened-out budget so a phrase never ends
    on a one-word orphan line."""
    first = _wrap(words, budget)
    if len(first) < 2:
        return first

    total = sum(len(word["text"]) + 1 for word in words) - 1
    evened = max(
        max(len(word["text"]) for word in words),
        math.ceil(total / len(first)),
    )
    candidate = _wrap(words, min(budget, evened))
    lines = candidate if len(candidate) == len(first) else first

    # Pull words down onto a stub final line ("...tears / the") until the last
    # two lines are roughly even.
    def chars(line: list[dict[str, Any]]) -> int:
        return sum(len(word["text"]) + 1 for word in line) - 1

    last = lines[-1]
    previous = lines[-2]
    while len(previous) > 1:
        move = previous[-1]
        if chars(last) >= chars(previous) - len(move["text"]) - 1:
            break
        if chars(last) + len(move["text"]) + 1 > budget:
            break
        last.insert(0, previous.pop())
    return lines


def layout_lines(
    words: list[dict[str, Any]], spec: Preset, chars_per_line: int = 22
) -> list[list[dict[str, Any]]]:
    if not words:
        return []
    if spec.layout == "focus":
        return [[word] for word in words]
    if spec.layout == "cascade":
        # Short breath-sized chunks stacked vertically.
        return balanced_wrap(words, max(8, math.floor(chars_per_line * 0.55 + 0.5)))

    lines = balanced_wrap(words, chars_per_line)
    if spec.layout == "stack" and len(lines) == 1 and len(lines[0]) > 2:
        all_words = lines[0]
        cut = max(1, min(len(all_words) - 1, math.ceil(len(all_words) * 0.45)))
        return [all_words[:cut], all_words[cut:]]
    return lines


# --------------------------------------------------------------------------- #
# Alignment helpers (shared with the frontend snap tool)
# --------------------------------------------------------------------------- #


def snap_time(value: float, targets: list[float], window: float, strength: float) -> float:
    """Pull `value` toward the closest target inside `window` seconds."""
    if not targets or window <= 0 or strength <= 0:
        return value
    best = min(targets, key=lambda target: abs(target - value))
    if abs(best - value) > window:
        return value
    return value + (best - value) * clamp(strength)
