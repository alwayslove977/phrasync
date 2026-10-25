from __future__ import annotations

import os
import platform
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .config import ASSETS_DIR, CUSTOM_FONTS_DIR

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}

_PRESET_NAMES = {
    "impact": [
        "impact.ttf",
        "Impact.ttf",
        "Anton-Regular.ttf",
        "Arial Narrow Bold.ttf",
        "DejaVuSansCondensed-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    "condensed": [
        "ARIALNB.TTF",
        "ARIALN.TTF",
        "Arial Narrow Bold.ttf",
        "Arial Narrow.ttf",
        "DejaVuSansCondensed-Bold.ttf",
        "LiberationSansNarrow-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    "modern": [
        "arialbd.ttf",
        "arial.ttf",
        "Arial Bold.ttf",
        "Arial.ttf",
        "Helvetica.ttc",
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    "serif": [
        "timesbd.ttf",
        "georgiab.ttf",
        "Times New Roman Bold.ttf",
        "Georgia Bold.ttf",
        "DejaVuSerif-Bold.ttf",
        "LiberationSerif-Bold.ttf",
    ],
    "bebas": [
        "BebasNeue-Regular.otf",
        "BebasNeue-Regular.ttf",
        "BebasKai.ttf",
        "Anton-Regular.ttf",
        "Oswald-Bold.ttf",
        "DIN Condensed Bold.ttf",
        "DejaVuSansCondensed-Bold.ttf",
        "LiberationSansNarrow-Bold.ttf",
    ],
    "geometric": [
        "Montserrat-Black.ttf",
        "Montserrat-ExtraBold.ttf",
        "Montserrat-Bold.ttf",
        "Futura.ttc",
        "Poppins-Black.otf",
        "ariblk.ttf",
        "Arial Black.ttf",
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    "rounded": [
        "Poppins-Black.otf",
        "Poppins-Black.ttf",
        "Poppins-ExtraBold.otf",
        "Quicksand-Bold.ttf",
        "Nunito-Black.ttf",
        "VarelaRound-Regular.ttf",
        "CenturyGothic.ttf",
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    "poster": [
        "NexaBlack.otf",
        "NexaHeavy.otf",
        "seguibl.ttf",
        "ariblk.ttf",
        "Arial Black.ttf",
        "Helvetica.ttc",
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    "techno": [
        "DINPro-CondBlack.otf",
        "DINPro-CondBold.otf",
        "DIN Condensed Bold.ttf",
        "DINCondensed-Bold.ttf",
        "bahnschrift.ttf",
        "Oswald-Bold.ttf",
        "DejaVuSansCondensed-Bold.ttf",
        "LiberationSansNarrow-Bold.ttf",
    ],
    "script": [
        "segoescb.ttf",
        "segoesc.ttf",
        "Bradley Hand Bold.ttf",
        "Noteworthy.ttc",
        "Caveat-Bold.ttf",
        "Gabriola.ttf",
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ],
    "jgothic": [
        "YuGothB.ttc",
        "YuGothM.ttc",
        "meiryob.ttc",
        "msgothic.ttc",
        "HiraginoSans-W7.ttc",
        "NotoSansJP-Bold.otf",
        "NotoSansJP-VF.ttf",
        "DejaVuSans-Bold.ttf",
    ],
    "mono": [
        "consolab.ttf",
        "consola.ttf",
        "Consolas Bold.ttf",
        "Menlo.ttc",
        "DejaVuSansMono-Bold.ttf",
        "LiberationMono-Bold.ttf",
    ],
}



# Writable font folder. From source this is the repo's fonts/ directory; in a
# packaged app it resolves to ~/Library/Application Support/Phrasync/fonts so a
# read-only bundle never needs writes for user-supplied fonts.
CUSTOM_FONT_DIR = CUSTOM_FONTS_DIR


def resolve_custom_font_path(filename: str | None) -> Path | None:
    """Resolve a custom font strictly inside the project's fonts directory."""
    if not filename:
        return None
    name = Path(str(filename)).name
    if name != str(filename) or Path(name).suffix.lower() not in FONT_EXTENSIONS:
        return None
    candidate = CUSTOM_FONT_DIR / name
    try:
        if candidate.is_file() and candidate.resolve().parent == CUSTOM_FONT_DIR.resolve():
            return candidate
    except OSError:
        pass
    return None


def list_custom_fonts() -> list[dict[str, str]]:
    """List custom fonts and their embedded family names."""
    CUSTOM_FONT_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(CUSTOM_FONT_DIR.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in FONT_EXTENSIONS:
            continue
        try:
            font = ImageFont.truetype(str(path), 24)
            family, style = font.getname()
            display_name = f"{family} {style}".strip()
        except Exception:
            display_name = path.stem
        result.append({"filename": path.name, "name": display_name})
    return result


def font_directories() -> list[Path]:
    home = Path.home()
    system = platform.system().lower()
    directories: list[Path] = []
    directories.append(CUSTOM_FONT_DIR)
    if system == "windows":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        directories.extend([windir / "Fonts", home / "AppData/Local/Microsoft/Windows/Fonts"])
    elif system == "darwin":
        directories.extend(
            [
                Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"),
                home / "Library/Fonts",
            ]
        )
    else:
        directories.extend(
            [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                home / ".fonts",
                home / ".local/share/fonts",
            ]
        )
    return [path for path in directories if path.exists()]


@lru_cache(maxsize=1)
def index_fonts() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for directory in font_directories():
        try:
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in FONT_EXTENSIONS:
                    result.setdefault(path.name.lower(), path)
        except (OSError, PermissionError):
            continue
    bundled_japanese = ASSETS_DIR / "NotoSansJP-VF.ttf"
    if bundled_japanese.is_file():
        result.setdefault(bundled_japanese.name.lower(), bundled_japanese)
    return result


def resolve_font_path(preset: str = "impact", custom_path: Path | None = None) -> Path | None:
    if custom_path and custom_path.exists() and custom_path.suffix.lower() in FONT_EXTENSIONS:
        return custom_path
    index = index_fonts()
    candidates = _PRESET_NAMES.get(preset, _PRESET_NAMES["modern"])
    for candidate in candidates:
        found = index.get(candidate.lower())
        if found:
            return found
    # Last resort: pick any bold font, then any font. This still gives a useful export.
    for name, path in index.items():
        if "bold" in name and "emoji" not in name:
            return path
    return next(iter(index.values()), None)


@lru_cache(maxsize=256)
def _load_font_cached(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, max(8, int(size)))
    except Exception:
        return ImageFont.load_default()


def load_font(size: int, preset: str = "impact", custom_path: Path | None = None):
    resolved = resolve_font_path(preset, custom_path)
    if resolved:
        return _load_font_cached(str(resolved), max(8, int(size)))
    return ImageFont.load_default()


def _is_japanese_character(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3040 <= codepoint <= 0x30FF  # hiragana and katakana
        or 0x3400 <= codepoint <= 0x9FFF  # common kanji and extension A
        or 0xFF66 <= codepoint <= 0xFF9D  # half-width katakana
    )


def _covers_japanese_text(font, text: str) -> bool:
    # Pillow does not perform the per-glyph fallback used by the browser. A
    # missing character is drawn with the same .notdef box as this noncharacter.
    missing = font.getmask("\U0010FFFF")
    missing_signature = (missing.size, bytes(missing))
    return all(
        (mask.size, bytes(mask)) != missing_signature
        for char in text if _is_japanese_character(char)
        for mask in (font.getmask(char),)
    )


@lru_cache(maxsize=4096)
def load_font_for_text(size: int, preset: str, text: str, custom_path: Path | None = None):
    """Preserve the chosen font except where Japanese glyphs would be boxes."""
    font = load_font(size, preset, custom_path)
    if not any(_is_japanese_character(char) for char in text):
        return font
    if _covers_japanese_text(font, text):
        return font
    candidates = []
    for candidate in _PRESET_NAMES["jgothic"]:
        path = index_fonts().get(candidate.lower())
        if path:
            candidates.append(path)

    # Always try the bundled Japanese font, even when it is not indexed.
    bundled_font = ASSETS_DIR / "NotoSansJP-VF.ttf"
    if bundled_font.is_file():
        candidates.append(bundled_font)

    # Search all indexed fonts as well, including fonts with Chinese glyphs.
    for path in index_fonts().values():
        if path not in candidates:
            candidates.append(path)

    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        replacement_font = _load_font_cached(key, max(8, int(size)))
        if _covers_japanese_text(replacement_font, text):
            return replacement_font
    raise ValueError(f"No suitable CJK font is available for text: {text!r}")


def font_status() -> dict:
    fonts = index_fonts()
    return {
        "count": len(fonts),
        "presets": {name: str(resolve_font_path(name) or "") for name in _PRESET_NAMES},
    }
