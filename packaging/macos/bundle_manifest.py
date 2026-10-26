# -*- mode: python ; coding: utf-8 -*-
"""Single reviewed definition of what may enter the macOS bundle.

``Phrasync.spec`` used to name the ``static`` and ``assets`` directories and let
PyInstaller copy everything below them. That is a recursive collection of an
arbitrary directory: ``.gitignore`` has no say over it, so an editor backup, a
user upload or a stray video dropped into either directory would ship inside the
release. The only defence was a hand-maintained blocklist, which fails silently
the moment a new kind of file appears.

This module inverts the rule. Each file is admitted only if its path matches an
audited rule; anything else is a *violation* that stops the build instead of
being packaged. Keeping the rules here -- rather than inline in the spec -- lets
the pre-build gate (``privacy_gate.py``) and the spec reject exactly the same
files, so the check cannot drift away from the packaging.

Nothing in this module reads user data; it only lists the source tree.
"""

from __future__ import annotations

import os
from pathlib import Path

# Suffixes that may appear under ``static/``. The editor is plain ES modules,
# one stylesheet, one HTML shell, an SVG favicon and the vendored three.js build.
STATIC_SUFFIXES = {
    ".js", ".css", ".html", ".htm", ".svg", ".png", ".ico",
    ".txt", ".json", ".webmanifest", ".woff2", ".webp", ".map",
}

# Suffixes allowed as *direct* children of ``assets/``: the app icon, the style
# reference still, the Noto Sans JP font and its licence.
ASSETS_TOP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp",
    ".ttf", ".otf", ".woff2", ".txt", ".md", ".json",
}

# Large third-party trees that cannot be enumerated file by file (the export
# browser alone is 13 entries plus Chromium's resource directory, and the
# Whisper model is a fixed set of four files). They are admitted as whole trees
# but still pass through the media/backup deny rules below, so a video or an
# editor backup dropped into them is still refused.
AUDITED_ASSET_TREES = ("browser", "models")

# Any of these anywhere in the build inputs is a hard failure, whatever the
# allowlist says: they are user media, databases, logs or editor debris, none of
# which the application reads from inside its bundle.
#
# ``.pem`` is deliberately absent. ``certifi`` ships ``cacert.pem`` -- a bundle of
# 117 public root certificates that TLS needs -- and refusing it by extension
# would break HTTPS while protecting nothing. A PEM that actually carries a
# private key is caught by ``carries_private_key()``, which reads the bytes.
DENY_SUFFIXES = {
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".mpg", ".mpeg",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".aiff", ".aif", ".ogg", ".opus",
    ".lrc", ".srt", ".ass", ".ssa", ".vtt",
    ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm",
    ".log", ".env", ".key", ".p12", ".pfx", ".mobileprovision",
}

# A PEM container is legitimate unless it holds a private key.
PEM_SUFFIXES = {".pem", ".crt", ".cer"}

# Editor and Finder debris. Matched by name because the suffix test would miss
# ``app.js.bak`` (suffix .bak) but also ``app.js.font-backup`` (suffix
# .font-backup) -- both are listed here so either spelling is caught.
DENY_NAME_MARKERS = (
    ".bak", ".font-backup", ".before_", ".orig", ".rej", ".swp", ".swo",
    "~", ".pyc", ".pyo",
)

# Archives nested inside the inputs are not shipped content; they hide theirs.
ARCHIVE_SUFFIXES = {".zip", ".jar", ".whl", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".7z"}


def is_denied_name(name: str) -> bool:
    """True for Finder metadata and editor backups."""
    if name == ".DS_Store" or name.startswith("._"):
        return True
    return any(marker in name for marker in DENY_NAME_MARKERS)


def carries_private_key(path, limit: int = 65536) -> bool:
    """True when a PEM-ish file actually contains a private key.

    Extension alone cannot decide this: ``certifi/cacert.pem`` is a public CA
    bundle that HTTPS needs, while ``deploy.pem`` holding an RSA key is exactly
    what must never ship. Only the bytes separate them.

    A file that cannot be read is reported as *carrying* a key. That is
    deliberately fail-closed: "I could not look" must never be reported as
    "there is nothing there".
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(limit)
    except OSError:
        return True
    return b"PRIVATE KEY" in head


def _suffix(name: str) -> str:
    return Path(name).suffix.lower()


def _walk(root: Path, subtree: str):
    """Yield ``(path, relative-to-subtree)`` for every regular file."""
    base = root / subtree
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not is_denied_name(d))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            yield path, path.relative_to(base)


def collect(root: Path):
    """Return ``(datas, exclusions, violations)`` for the reviewed inputs.

    *datas*      ``[(source, dest_dir)]`` -- one entry per admitted file, so the
                 bundle receives exactly these files and no directory walk.
    *exclusions* ``[(relative_path, reason)]`` -- audited-but-refused files
                 (backups, .DS_Store). Reported, never fatal: the build must not
                 depend on the developer's working copy being tidy.
    *violations* ``[(relative_path, reason)]`` -- files nobody has reviewed.
                 Any entry here must stop the build.
    """
    root = Path(root)
    datas = []
    exclusions = []
    violations = []

    for path, rel in _walk(root, "static"):
        shown = str(Path("static") / rel)
        if is_denied_name(path.name):
            exclusions.append((shown, "editor/Finder debris"))
            continue
        suffix = _suffix(path.name)
        if suffix in DENY_SUFFIXES:
            violations.append((shown, f"denied suffix {suffix}"))
            continue
        if suffix in ARCHIVE_SUFFIXES:
            violations.append((shown, f"nested archive {suffix}"))
            continue
        if suffix not in STATIC_SUFFIXES:
            violations.append((shown, f"suffix {suffix or '(none)'} is not allowlisted"))
            continue
        datas.append((str(path), str(Path("static") / rel.parent)))

    assets = root / "assets"
    for entry in sorted(assets.iterdir()):
        if is_denied_name(entry.name):
            exclusions.append((f"assets/{entry.name}", "editor/Finder debris"))
            continue

        if entry.is_dir():
            if entry.name not in AUDITED_ASSET_TREES:
                violations.append(
                    (f"assets/{entry.name}/", "directory is not an audited asset tree")
                )
                continue
            for path, rel in _walk(root, f"assets/{entry.name}"):
                shown = f"assets/{entry.name}/{rel}"
                if is_denied_name(path.name):
                    exclusions.append((shown, "editor/Finder debris"))
                    continue
                suffix = _suffix(path.name)
                if suffix in DENY_SUFFIXES:
                    violations.append((shown, f"denied suffix {suffix}"))
                    continue
                datas.append((str(path), str(Path("assets") / entry.name / rel.parent)))
            continue

        suffix = _suffix(entry.name)
        if suffix in DENY_SUFFIXES:
            violations.append((f"assets/{entry.name}", f"denied suffix {suffix}"))
        elif suffix not in ASSETS_TOP_SUFFIXES:
            violations.append(
                (f"assets/{entry.name}", f"suffix {suffix or '(none)'} is not allowlisted")
            )
        else:
            datas.append((str(entry), "assets"))

    for tree in AUDITED_ASSET_TREES:
        if not (assets / tree).is_dir():
            violations.append((f"assets/{tree}/", "audited asset tree is missing"))

    return datas, exclusions, violations


def describe(root: Path) -> str:
    """Human-readable summary for build logs."""
    datas, exclusions, violations = collect(root)
    lines = [
        f"bundle inputs: {len(datas)} file(s) admitted",
        f"bundle inputs: {len(exclusions)} file(s) held out",
    ]
    for shown, reason in exclusions:
        lines.append(f"  held out  {shown}  ({reason})")
    if violations:
        lines.append(f"bundle inputs: {len(violations)} file(s) REFUSED")
        for shown, reason in violations:
            lines.append(f"  REFUSED   {shown}  ({reason})")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    datas, exclusions, violations = collect(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print(describe(Path(sys.argv[1] if len(sys.argv) > 1 else ".")))
    print(f"\nsummary: {len(datas)} admitted, {len(exclusions)} held out, {len(violations)} refused")
    raise SystemExit(1 if violations else 0)
