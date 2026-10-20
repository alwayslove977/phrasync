from __future__ import annotations

import os
import platform
import hashlib
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .config import ASSETS_DIR, WORKSPACE, UPLOADS_DIR

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


def font_directories() -> list[Path]:
    home = Path.home()
    system = platform.system().lower()
    directories: list[Path] = []
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
    directories.extend(custom_font_directories())
    return [path for path in directories if path.exists()]


def custom_font_directories() -> list[Path]:
    return list(dict.fromkeys([WORKSPACE / "fonts", Path.home() / "phrasync/fonts",
                              Path(__file__).resolve().parent.parent / "fonts"]))


def custom_font_catalog() -> dict[str, dict]:
    from .storage import list_assets
    paths = {Path(asset["id"]): (UPLOADS_DIR / asset["id"], asset["name"])
             for asset in list_assets() if asset["kind"] == "font"}
    for folder in custom_font_directories():
        if folder.is_dir():
            for path in folder.rglob("*"):
                if path.is_file() and path.suffix.lower() in FONT_EXTENSIONS:
                    paths[path] = (path, path.name)
    result = {}
    for path, name in paths.values():
        try:
            family, variant = ImageFont.truetype(str(path), 24).getname()
        except (OSError, ValueError):
            continue
        key = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
        result[key] = {"id": key, "name": name, "family": f"{family} {variant}", "path": path}
    return result


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
    for path in UPLOADS_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in FONT_EXTENSIONS:
            result.setdefault(path.name.lower(), path)
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
        or 0x1100 <= codepoint <= 0x11FF  # Hangul jamo
        or 0x3130 <= codepoint <= 0x318F
        or 0xAC00 <= codepoint <= 0xD7AF  # Hangul syllables
        or 0xF900 <= codepoint <= 0xFAFF  # CJK compatibility ideographs
        or 0x20000 <= codepoint <= 0x323AF  # supplementary CJK ideographs
        or 0x3000 <= codepoint <= 0x303F  # CJK punctuation
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
    """Preserve the chosen font; search all installed/uploaded CJK fallbacks.

    Cached per token/size, so coverage scans are not repeated on every frame.
    """
    font = load_font(size, preset, custom_path)
    if not any(_is_japanese_character(char) for char in text):
        return font
    if _covers_japanese_text(font, text):
        return font
    index = index_fonts()
    candidates = [index[name.lower()] for name in _PRESET_NAMES["jgothic"] if name.lower() in index]
    candidates.extend(index.values())
    checked = set()
    for path in candidates:
        if path not in checked:
            checked.add(path)
            replacement = _load_font_cached(str(path), max(8, int(size)))
            if _covers_japanese_text(replacement, text):
                return replacement
    characters = " ".join(f"{char} (U+{ord(char):04X})" for char in dict.fromkeys(text)
                          if _is_japanese_character(char))
    raise ValueError(f"No available font covers the required CJK characters: {characters}. "
                     f"Checked the selected font and {len(checked)} fallback fonts. "
                     "Upload a font covering this text or install a suitable Chinese, Japanese or Korean font.")


def refresh_fonts() -> None:
    index_fonts.cache_clear()
    load_font_for_text.cache_clear()
    _load_font_cached.cache_clear()


def font_status() -> dict:
    fonts = index_fonts()
    return {
        "count": len(fonts),
        "presets": {name: str(resolve_font_path(name) or "") for name in _PRESET_NAMES},
    }
