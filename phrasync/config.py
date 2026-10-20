from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Phrasync"
APP_VERSION = "0.4.8"
LEGACY_PREFIX = "VERSEFRAME"  # the app shipped under this name before Phrasync


def _env(name: str, default: str) -> str:
    """Read PHRASYNC_<name>, falling back to the pre-rename VERSEFRAME_<name>."""
    return os.environ.get(f"PHRASYNC_{name}") or os.environ.get(f"{LEGACY_PREFIX}_{name}") or default


DEFAULT_HOST = _env("HOST", "127.0.0.1")
DEFAULT_PORT = int(_env("PORT", "5500"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
ASSETS_DIR = PROJECT_ROOT / "assets"


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

MAX_UPLOAD_BYTES = int(_env("MAX_UPLOAD_MB", "16384")) * 1024 * 1024
SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
SUPPORTED_FONT = {".ttf", ".otf", ".ttc"}
SUPPORTED_LYRICS = {".srt", ".lrc", ".txt", ".json", ".vtt"}

# Project files saved before the rename still open normally.
PROJECT_SUFFIX = ".phrasync.json"
LEGACY_PROJECT_SUFFIX = ".verseframe.json"
