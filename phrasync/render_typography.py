from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import kinetic
from .font_utils import load_font, load_font_for_text, resolve_custom_font_path
from .render_utils import clamp, hex_color, scale_for_canvas

if TYPE_CHECKING:
    from .renderer import RenderContext


def _text_mask(text: str, font, stroke_width: int = 0) -> tuple[Image.Image, tuple[int, int, int, int]]:
    dummy = Image.new("L", (8, 8), 0)
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.text((-bbox[0], -bbox[1]), text, font=font, fill=255, stroke_width=0)
    return mask, bbox


def _cue_at(cues: list[dict[str, Any]], time_seconds: float) -> dict[str, Any] | None:
    # Cue lists are short in typical lyric videos; linear scan is faster than maintaining extra state here.
    for cue in cues:
        if cue["start"] <= time_seconds < cue["end"]:
            return cue
    return None


LEGACY_MOTION = {"pop": 1.0, "rise": 1.0, "slide": 1.0, "fade": 0.6, "none": 0.0}


def _motion_strength(style: dict[str, Any]) -> float:
    """Motion intensity multiplier, accepting the pre-kinetic string values."""
    value = style.get("animation", 1)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return LEGACY_MOTION.get(value, 1.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _word_image(
    token: str,
    font,
    base_color: tuple[int, int, int],
    accent_top: tuple[int, int, int],
    accent_bottom: tuple[int, int, int],
    stroke_color: tuple[int, int, int],
    stroke: int,
    shadow: int,
    fill: float,
    fill_alpha: float,
    glow: float,
) -> tuple[Image.Image, int, int, tuple[int, int]]:
    """Draw one word: shadow, stroked base text, clipped gradient fill, glow."""
    dummy = Image.new("L", (8, 8))
    measure = ImageDraw.Draw(dummy)
    bbox = measure.textbbox((0, 0), token, font=font, stroke_width=stroke)
    text_w = max(1, bbox[2] - bbox[0])
    text_h = max(1, bbox[3] - bbox[1])
    glow_pad = int(font.size * 0.42 * glow) if glow > 0.01 else 0
    pad = stroke * 2 + shadow * 2 + glow_pad + 6

    layer = Image.new("RGBA", (text_w + pad * 2, text_h + pad * 2), (0, 0, 0, 0))
    origin = (pad - bbox[0], pad - bbox[1])

    if shadow > 0:
        shadow_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow_layer).text(
            (origin[0] + shadow, origin[1] + int(shadow * 1.15)),
            token, font=font, fill=(0, 0, 0, 205),
            stroke_width=stroke, stroke_fill=(0, 0, 0, 185),
        )
        layer.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(max(1, shadow))))

    if glow > 0.01:
        glow_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow_layer).text(
            origin, token, font=font,
            fill=(*accent_top, int(190 * clamp(glow))),
            stroke_width=stroke, stroke_fill=(*accent_top, int(150 * clamp(glow))),
        )
        layer.alpha_composite(glow_layer.filter(ImageFilter.GaussianBlur(max(2, int(font.size * 0.09)))))

    draw = ImageDraw.Draw(layer)
    draw.text(
        origin, token, font=font, fill=(*base_color, 255),
        stroke_width=stroke, stroke_fill=(*stroke_color, 240),
    )

    if fill > 0.002 and fill_alpha > 0.004:
        mask, mask_bbox = _text_mask(token, font)
        gradient = np.zeros((mask.height, mask.width, 4), dtype=np.uint8)
        alpha = np.asarray(mask)
        for row in range(mask.height):
            ratio = row / max(1, mask.height - 1)
            gradient[row, :, :3] = [
                int(accent_top[channel] * (1 - ratio) + accent_bottom[channel] * ratio)
                for channel in range(3)
            ]
            gradient[row, :, 3] = (alpha[row] * clamp(fill_alpha)).astype(np.uint8)
        overlay = Image.fromarray(gradient, "RGBA")
        if fill < 0.998:
            keep = max(1, int(overlay.width * clamp(fill)))
            overlay = overlay.crop((0, 0, keep, overlay.height))
        layer.alpha_composite(overlay, (pad - bbox[0] + mask_bbox[0], pad - bbox[1] + mask_bbox[1]))

    return layer, text_w, text_h, (pad, pad)


def _render_kinetic(
    ctx: RenderContext,
    cue: dict[str, Any],
    t: float,
    style: dict[str, Any],
    spec: kinetic.Preset,
    fonts: dict[str, Any],
    max_width: int,
    center_y: int,
    beat: float,
) -> Image.Image | None:
    layer = Image.new("RGBA", (ctx.width, ctx.height), (0, 0, 0, 0))
    words = kinetic.cue_words(cue)
    if not words:
        return None

    uppercase = bool(style.get("uppercase", True))
    strength = _motion_strength(style)
    base_color = hex_color(style.get("textColor"), (244, 221, 255))
    accent = hex_color(style.get("accentColor"), (225, 97, 255))
    accent2 = hex_color(style.get("accentColor2"), (186, 83, 255))
    stroke_color = hex_color(style.get("strokeColor"), (9, 8, 17))

    body_font = fonts["body"]
    lead_font = fonts["lead"]
    line_gap = int(scale_for_canvas(float(style.get("lineGap", 0) or 0), ctx.height, ctx.width))
    stroke = max(0, int(scale_for_canvas(float(style.get("strokeWidth", 3)), ctx.height, ctx.width)))
    shadow = max(0, int(scale_for_canvas(float(style.get("shadow", 7)), ctx.height, ctx.width)))

    dummy = Image.new("L", (8, 8))
    measure = ImageDraw.Draw(dummy)

    # Same character budget as the browser, so both engines break lines alike.
    lines = kinetic.layout_lines(
        words, spec, kinetic.char_budget(style, ctx.project.get("canvas") or {}, spec)
    )

    focus_fonts: dict[int, Any] = {}

    def font_for(line_index: int):
        if spec.layout == "focus":
            word = lines[line_index][0]
            size = max(18, int(body_font.size * kinetic.focus_scale(word["text"])))
            if size not in focus_fonts:
                focus_fonts[size] = load_font(size, fonts["preset"], fonts["path"])
            return focus_fonts[size]
        if spec.layout == "stack" and line_index == 0 and len(lines) > 1:
            return lead_font
        return body_font

    def token_of(word: dict[str, Any]) -> str:
        return word["text"].upper() if uppercase else word["text"]

    def font_for_token(line_index: int, word: dict[str, Any]):
        base_font = font_for(line_index)
        return load_font_for_text(base_font.size, fonts["preset"], token_of(word), fonts["path"])

    # ---- layout pass: static geometry, so words never jitter horizontally ----
    placed: list[tuple[dict[str, Any], Any, int, int, bool]] = []
    line_boxes: list[tuple[float, int]] = []
    for line_index, line in enumerate(lines):
        font = font_for(line_index)
        gap = int(font.size * spec.word_gap)
        widths = [measure.textlength(token_of(word), font=font_for_token(line_index, word)) for word in line]
        total = sum(widths) + gap * max(0, len(line) - 1)
        line_boxes.append((total, int(font.size * spec.line_height)))

    if spec.layout == "focus":
        total_height = line_boxes[0][1] if line_boxes else 0
    else:
        total_height = sum(height for _, height in line_boxes) + line_gap * (len(line_boxes) - 1)
    y = center_y - total_height // 2

    for line_index, line in enumerate(lines):
        font = font_for(line_index)
        gap = int(font.size * spec.word_gap)
        total, line_height = line_boxes[line_index]
        line_y = center_y - line_height // 2 if spec.layout == "focus" else y
        x = (ctx.width - total) / 2
        for word in line:
            token = token_of(word)
            font = font_for_token(line_index, word)
            width = measure.textlength(token, font=font)
            lead = spec.layout == "stack" and line_index == 0 and len(lines) > 1
            placed.append((word, font, int(x), int(line_y + line_height * 0.5), lead))
            x += width + gap
        if spec.layout != "focus":
            y += line_height + line_gap

    # ---- draw pass ---------------------------------------------------------
    drew = False
    for word, font, word_x, word_center_y, lead in placed:
        state = kinetic.word_state(word, cue, t, spec, beat)
        fill = max(state.fill, 1.0) if lead else state.fill
        if not state.visible or state.opacity <= 0.004:
            continue

        scale = 1 + (state.scale - 1) * strength
        blur = state.blur * strength
        dx = state.dx * strength * font.size
        dy = state.dy * strength * font.size
        rotate = state.rotate * strength

        token = word["text"].upper() if uppercase else word["text"]
        image, text_w, text_h, pad = _word_image(
            token, font, base_color, accent, accent2, stroke_color,
            stroke, shadow, fill, state.fill_alpha, state.glow,
        )

        if blur > 0.05:
            image = image.filter(ImageFilter.GaussianBlur(blur * ctx.height / 1080))
        if abs(rotate) > 0.05:
            image = image.rotate(rotate, resample=Image.Resampling.BICUBIC, expand=True)
        if abs(scale - 1) > 0.002:
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        if state.opacity < 0.998:
            alpha = image.getchannel("A").point(lambda value: int(value * state.opacity))
            image.putalpha(alpha)

        # Anchor on the word's static centre so scaling grows outward evenly.
        anchor_x = word_x + text_w / 2
        dest_x = int(anchor_x - image.width / 2 + dx)
        dest_y = int(word_center_y - image.height / 2 + dy)
        layer.alpha_composite(image, (dest_x, dest_y))
        drew = True

    return layer if drew else None


def render_text_layer(ctx: RenderContext, t: float) -> Image.Image | None:
    style = ctx.project.get("style") or {}
    timing = ctx.project.get("timing") or {}
    lyric_t = t - float(timing.get("offset", 0.0) or 0.0)

    spec = kinetic.resolved_preset(style)
    cues = kinetic.active_cues(ctx.cues, lyric_t, spec)
    if not cues:
        return None

    font_preset = style.get("fontPreset", "impact")
    font_path = (
        Path(ctx.font_asset.path)
        if ctx.font_asset
        else resolve_custom_font_path(style.get("fontPath"))
    )
    base_size = max(18, int(scale_for_canvas(float(style.get("fontSize", 160)), ctx.height, ctx.width)))
    if spec.layout == "focus":
        base_size = int(base_size * 1.34)
    if spec.id == "minimal":
        base_size = int(base_size * 0.5)
        font_preset = style.get("fontPreset", "modern")
    lead_size = max(16, int(base_size * float(style.get("topScale", 0.58))))

    fonts = {
        "body": load_font(base_size, font_preset, font_path),
        "lead": load_font(lead_size, font_preset, font_path),
        "preset": font_preset,
        "path": font_path,
    }
    max_width = int(ctx.width * float(style.get("maxWidth", 88)) / 100.0)
    center_y = int(ctx.height * float(style.get("positionY", 52)) / 100.0)

    beat = 0.0
    if style.get("beatReact", True):
        beat = kinetic.beat_pulse(
            lyric_t,
            float(timing.get("bpm", 0) or 0),
            float(timing.get("beatOffset", 0) or 0),
        )

    layer: Image.Image | None = None
    for cue in cues:
        rendered = _render_kinetic(
            ctx, cue, lyric_t, style, spec, fonts, max_width, center_y, beat
        )
        if rendered is None:
            continue
        layer = rendered if layer is None else Image.alpha_composite(layer, rendered)
    return layer
