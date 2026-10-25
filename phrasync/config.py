from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Phrasync"
APP_VERSION = "0.4.7"
LEGACY_PREFIX = "VERSEFRAME"  # the app shipped under this name before Phrasync


def _env(name: str, default: str) -> str:
    """Read PHRASYNC_<name>, falling back to the pre-rename VERSEFRAME_<name>."""
    return os.environ.get(f"PHRASYNC_{name}") or os.environ.get(f"{LEGACY_PREFIX}_{name}") or default


DEFAULT_HOST = _env("HOST", "127.0.0.1")
DEFAULT_PORT = int(_env("PORT", "5500"))


def is_frozen() -> bool:
    """True when the code runs from a PyInstaller bundle rather than the repo."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Read-only resources (static/, assets/) inside the running application.

    In a PyInstaller onedir bundle ``sys._MEIPASS`` is the bundle's Frameworks
    directory, which is exactly where the collected ``static/`` and ``assets/``
    folders land. Running from source keeps the repository root, so both
    layouts resolve identically and no working directory is required.
    """
    if is_frozen():
        bundled = getattr(sys, "_MEIPASS", None)
        if bundled:
            return Path(bundled)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def writable_data_dir() -> Path:
    """User-writable data that must never be written inside the app bundle."""
    if not is_frozen():
        return PROJECT_ROOT
    for candidate in (
        Path.home() / "Library" / "Application Support" / APP_NAME,
        Path.home() / f".{APP_NAME.lower()}",
    ):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    return Path.home()


PROJECT_ROOT = resource_root()
STATIC_DIR = PROJECT_ROOT / "static"
ASSETS_DIR = PROJECT_ROOT / "assets"
CUSTOM_FONTS_DIR = writable_data_dir() / "fonts"
# Models shipped inside the bundle so a fresh Mac can transcribe offline.
BUNDLED_MODELS_DIR = ASSETS_DIR / "models"


def workspace_root() -> Path:
    """Resolve the workspace, adopting a pre-rename ~/.verseframe folder once.

    That folder holds uploaded songs, saved projects and multi-gigabyte Whisper
    models, so the rename renames the directory rather than orphaning it. If the
    move is not possible the old folder keeps being used in place.
    """
    override = os.environ.get("PHRASYNC_HOME") or os.environ.get(f"{LEGACY_PREFIX}_HOME")
    if override:
        root = Path(override).expanduser()
    else:
        root = Path.home() / ".phrasync"
        legacy = Path.home() / ".verseframe"
        if not root.exists() and legacy.is_dir():
            try:
                legacy.rename(root)
            except OSError:
                root = legacy
    root.mkdir(parents=True, exist_ok=True)
    for child in ("uploads", "renders", "jobs", "projects", "tmp"):
        (root / child).mkdir(exist_ok=True)
    return root


WORKSPACE = workspace_root()
UPLOADS_DIR = WORKSPACE / "uploads"
RENDERS_DIR = WORKSPACE / "renders"
JOBS_DIR = WORKSPACE / "jobs"
PROJECTS_DIR = WORKSPACE / "projects"
TMP_DIR = WORKSPACE / "tmp"


def scratch_dir() -> Path:
    """Directory for short-lived render scratch files.

    ``tempfile`` picks the system temp directory by creating a probe file and
    deleting it again. Locked-down accounts (and some management profiles) refuse
    that delete, so every ``tempfile`` call raises ``FileNotFoundError``. Falling
    back to the workspace's own tmp folder keeps effects export working there and
    changes nothing on a normal Mac.
    """
    import tempfile

    try:
        return Path(tempfile.gettempdir())
    except (FileNotFoundError, OSError):
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        return TMP_DIR


def discard(path: Path) -> None:
    """Best-effort delete: a refused cleanup must not fail a finished export."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass

MAX_UPLOAD_BYTES = int(_env("MAX_UPLOAD_MB", "16384")) * 1024 * 1024
SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
SUPPORTED_FONT = {".ttf", ".otf", ".ttc"}
SUPPORTED_LYRICS = {".srt", ".lrc", ".txt", ".json", ".vtt"}

# Project files saved before the rename still open normally.
PROJECT_SUFFIX = ".phrasync.json"
LEGACY_PROJECT_SUFFIX = ".verseframe.json"
