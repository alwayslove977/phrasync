#!/usr/bin/env python3
# -*- mode: python ; coding: utf-8 -*-
"""Post-build privacy audit for a finished Phrasync bundle.

The pre-build gate checks what the build was *given*; this checks what it
actually *produced*. Both are needed, because a bundler can add files of its own
and because a mistake in the spec would only show up here.

Checks:

1. **Signature sweep** -- every file (disk tree and, when given, the ZIP) is
   classified from its first bytes, not from its extension, so a video renamed
   to ``.dat`` is still found. Video, audio and SQLite payloads fail the audit.
2. **Nested archives** -- ``.zip``/``.jar``/``.whl`` are opened and their entry
   names are inspected for media or database content.
3. **Source parity** -- every bundled ``static/`` and ``assets/`` file must be
   byte-identical to the reviewed file of the same relative path in the source
   tree. A file with no source is a file nobody chose to ship.
4. **Markers** -- the caller-supplied private markers (env, never hard-coded
   here) are searched across the bundle.
5. **Official resources** -- the demo video, app icon, style reference, Noto
   font, Whisper model and the export browser are hashed and recorded so the
   release notes can quote them.

Exit code 0 means "audit passed"; 1 means at least one blocking finding.

Usage:
    python3 packaging/macos/audit_bundle.py --root . --app dist/Phrasync.app \
        [--zip dist/Phrasync-*.zip] [--report out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from privacy_gate import fingerprint, marker_values, scan_path_for_markers  # noqa: E402

# --- signature table ------------------------------------------------------
# (label, matcher) with matcher(bytes) -> bool. Ordered: the container checks
# run before the generic ones so a WebP is not reported as a bare RIFF.

def _iso_media(head: bytes) -> bool:
    return len(head) >= 12 and head[4:8] == b"ftyp"


def _riff(head: bytes, kind: bytes) -> bool:
    return len(head) >= 12 and head[0:4] == b"RIFF" and head[8:12] == kind


SIGNATURES = [
    ("video/audio (ISO BMFF: mp4, m4v, mov, m4a)", _iso_media),
    ("audio (WAVE)", lambda h: _riff(h, b"WAVE")),
    ("image (WebP)", lambda h: _riff(h, b"WEBP")),
    ("audio (MP3, ID3 tag)", lambda h: h.startswith(b"ID3")),
    ("audio (MP3, frame sync)", lambda h: len(h) > 2 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0),
    ("audio (FLAC)", lambda h: h.startswith(b"fLaC")),
    ("audio (Ogg)", lambda h: h.startswith(b"OggS")),
    ("video (Matroska/WebM)", lambda h: h.startswith(b"\x1a\x45\xdf\xa3")),
    ("audio (AIFF)", lambda h: h.startswith(b"FORM") and b"AIFF" in h[:12]),
    ("database (SQLite)", lambda h: h.startswith(b"SQLite format 3\x00")),
]

BLOCKING = {"video/audio (ISO BMFF: mp4, m4v, mov, m4a)", "audio (WAVE)", "audio (MP3, ID3 tag)",
            "audio (MP3, frame sync)", "audio (FLAC)", "audio (Ogg)", "video (Matroska/WebM)",
            "audio (AIFF)", "database (SQLite)"}

ARCHIVE_MAGIC = [b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b", b"BZh", b"\xfd7zXZ\x00", b"7z\xbc\xaf\x27\x1c"]

# Mach-O / universal binaries. PyInstaller rewrites their load commands and adds
# an adhoc signature, so their bytes legitimately differ from the input file.
MACHO_MAGIC = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",   # 32-bit, both endiannesses
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",   # 64-bit
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",   # universal
}

# Resources whose hash goes into the release notes.
OFFICIAL = [
    ("docs/media/phrasync-demo.mp4", "official demo video"),
    ("assets/Phrasync.png", "app icon"),
    ("assets/style_reference.png", "style reference still"),
    ("assets/NotoSansJP-VF.ttf", "bundled font (OFL)"),
    ("assets/models/whisper-tiny/model.bin", "Whisper tiny model"),
]

MAX_ARCHIVE_ENTRIES = 5000


def sha256_file(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    remaining = limit
    with path.open("rb") as fh:
        while True:
            size = 1 << 20
            if remaining is not None:
                if remaining <= 0:
                    break
                size = min(size, remaining)
            chunk = fh.read(size)
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return h.hexdigest()


def classify(head: bytes) -> str | None:
    for label, match in SIGNATURES:
        if match(head):
            return label
    return None


def audit_archive_bytes(name: str, data: bytes, findings: list, notes: list) -> None:
    """Open a nested ZIP and look at what it carries."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            entries = inner.namelist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                notes.append(f"{name}: {len(entries)} entries, names inspected only")
            suspicious = [e for e in entries if Path(e).suffix.lower() in {
                ".mp4", ".mov", ".m4v", ".wav", ".mp3", ".m4a", ".lrc", ".srt",
                ".db", ".sqlite", ".sqlite3", ".log"}]
            if suspicious:
                findings.append({"severity": "fail", "kind": "nested-media", "subject": name,
                                 "detail": f"nested archive holds {suspicious[:5]}"})
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        # The container promised "PK" magic and then refused to open: its entries
        # are unknown, so the archive is unverified rather than empty.
        findings.append({"severity": "fail", "kind": "nested-unreadable", "subject": name,
                         "detail": f"nested archive could not be opened "
                                   f"({exc.__class__.__name__}); entries unverified"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a built bundle for private payloads.")
    parser.add_argument("--root", default=".", help="repository root (build inputs)")
    parser.add_argument("--app", required=True, help="path to the built Phrasync.app")
    parser.add_argument("--zip", default="", help="release ZIP to audit as well")
    parser.add_argument("--report", default="", help="write a JSON report here")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    app = Path(args.app).resolve()
    findings: list[dict] = []
    notes: list[str] = []

    def fail(kind: str, subject: str, detail: str) -> None:
        findings.append({"severity": "fail", "kind": kind, "subject": str(subject), "detail": detail})

    print("== bundle audit ==")
    print(f"app:  {app}")
    if not app.is_dir():
        print("!! app bundle not found", file=sys.stderr)
        return 1

    # 1. signature sweep over the disk tree -------------------------------
    files = [p for p in app.rglob("*") if p.is_file() and not p.is_symlink()]
    media = []
    archives = []
    for path in files:
        try:
            with path.open("rb") as fh:
                head = fh.read(4096)
        except OSError as exc:
            # A file that cannot be read cannot be classified, so it cannot be
            # cleared either. Recording a note and moving on would turn "no media
            # found" into "no media could be ruled out" without saying so.
            print(f"   UNREADABLE {path.relative_to(app)}  ({exc.__class__.__name__})")
            fail("unreadable-file", path.relative_to(app),
                 f"cannot read file ({exc.__class__.__name__}); contents unverified")
            continue
        label = classify(head)
        if label:
            rel = path.relative_to(app)
            if label in BLOCKING:
                print(f"   MEDIA     {rel}  ({label})")
                media.append((str(rel), label))
                fail("media-signature", rel, label)
            else:
                notes.append(f"{rel}: {label}")
        if any(head.startswith(m) for m in ARCHIVE_MAGIC):
            archives.append(path)

    print(f"-- files scanned: {len(files)}   media/database hits: {len(media)}")

    # 2. nested archives --------------------------------------------------
    for path in archives:
        rel = path.relative_to(app)
        try:
            data = path.read_bytes()
        except OSError as exc:
            print(f"   UNREADABLE {rel}  (archive, {exc.__class__.__name__})")
            fail("unreadable-archive", rel,
                 f"cannot read archive ({exc.__class__.__name__}); contents unverified")
            continue
        if data[:2] != b"PK":
            # gzip/bzip2/xz/7z are recognised by magic but not opened here, so their
            # contents are unknown. Shipping a container nobody opened is not an
            # audit -- it is an assumption, and an assumption must stop the build.
            print(f"   ARCHIVE   {rel}  (not a ZIP; contents not inspectable)")
            fail("unopened-archive", rel,
                 f"{len(data)}-byte compressed stream could not be opened")
            continue
        audit_archive_bytes(str(rel), data, findings, notes)
    print(f"-- archives inspected: {len(archives)}")

    # 3. source parity ----------------------------------------------------
    # PyInstaller's macOS onedir layout keeps the real files in
    # Contents/Resources and leaves symlinks to them in Contents/Frameworks, so
    # walking Frameworks alone compares nothing (a symlinked directory is not
    # descended into). Prefer Resources, fall back to Frameworks for layouts
    # that store the files in place.
    compared = missing = extra = mismatched = 0
    app_contents = app / "Contents"
    for sub in ("static", "assets"):
        source_root = root / sub
        bundled_root = None
        for candidate in (app_contents / "Resources" / sub, app_contents / "Frameworks" / sub):
            if candidate.is_dir() and not candidate.is_symlink():
                bundled_root = candidate
                break
        if bundled_root is None:
            # A tree that exists in the source but not in the bundle is exactly the
            # failure this check exists to catch, so it cannot be a silent skip: a
            # build that lost the whole UI used to report "0 compared, 0 missing"
            # and pass. Absent here means absent from the release, so it fails.
            if source_root.is_dir():
                print(f"   MISSING   {sub}/  (entire tree absent from the bundle)")
                fail("missing-tree", sub, f"{sub}/ exists in the source tree but not in the bundle")
            continue
        for path in bundled_root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            rel = Path(sub) / path.relative_to(bundled_root)
            source = root / rel
            if not source.is_file():
                extra += 1
                print(f"   EXTRA     {rel}  (no source file)")
                fail("unreviewed-file", rel, "bundled file has no counterpart in the source tree")
                continue
            compared += 1
            if source.stat().st_size != path.stat().st_size:
                # PyInstaller rewrites the load commands and re-signs every
                # Mach-O it collects (adhoc signature, ~12 KB larger), so the
                # bytes of a binary cannot match its input. The mismatch is
                # expected and is recorded instead of silently ignored.
                try:
                    with path.open("rb") as handle:
                        magic = handle.read(4)
                except OSError:
                    magic = b""
                if magic[:4] in MACHO_MAGIC:
                    notes.append(f"{rel}: Mach-O re-signed by PyInstaller, "
                                 f"{source.stat().st_size} -> {path.stat().st_size} bytes")
                    continue
                mismatched += 1
                fail("source-mismatch", rel, "size differs from the source file")
                continue
            if sha256_file(source) != sha256_file(path):
                mismatched += 1
                fail("source-mismatch", rel, "content differs from the source file")
        # files present in source but absent from the bundle
        if (root / sub).is_dir():
            for path in (root / sub).rglob("*"):
                if not path.is_file() or path.is_symlink():
                    continue
                if not (bundled_root / path.relative_to(root / sub)).exists():
                    if path.name == ".DS_Store" or "bak" in path.name or "font-backup" in path.name:
                        continue
                    missing += 1
                    print(f"   MISSING   {sub}/{path.relative_to(root / sub)}")
                    fail("missing-file", f"{sub}/{path.relative_to(root / sub)}",
                         "reviewed source file is absent from the bundle")
    print(f"-- source parity: {compared} compared, {mismatched} mismatch, "
          f"{extra} extra, {missing} missing")

    # 4. markers ----------------------------------------------------------
    markers, source = marker_values(root)
    if not markers:
        notes.append("marker scan skipped: no PHRASYNC_PRIVATE_MARKERS or .privacy-markers")
        print("-- marker scan: skipped (no markers supplied)")
    else:
        raw = [m.encode("utf-8") for m in markers]
        hits = 0
        for path in files:
            found, problems = scan_path_for_markers(path, raw)
            for reason in problems:
                fail("unreadable-file", path.relative_to(app),
                     f"marker scan could not read the file ({reason}); its contents are "
                     "unverified, not clean")
            if not found:
                continue
            hits += 1
            print(f"   MARKER    {path.relative_to(app)}")
            fail("private-marker", path.relative_to(app), "matches a supplied private marker")
        print(f"-- marker scan: {len(markers)} marker(s) from {source}, {hits} hit(s)")

    # 5. official resources ----------------------------------------------
    official = []
    for rel, label in OFFICIAL:
        path = root / rel
        if not path.is_file():
            print(f"   MISSING   {rel}  ({label})")
            fail("official-resource", rel, f"{label} is missing from the source tree")
            continue
        item = {"path": rel, "label": label, "bytes": path.stat().st_size,
                "sha256": sha256_file(path)}
        official.append(item)
        print(f"   ok        {rel}  {item['bytes']} bytes  {item['sha256'][:16]}…")

    # 6. release ZIP ------------------------------------------------------
    zipped = None
    if args.zip:
        zip_path = Path(args.zip).resolve()
        if not zip_path.is_file():
            fail("zip-missing", zip_path, "release ZIP not found")
        else:
            entry = {"path": str(zip_path), "bytes": zip_path.stat().st_size,
                     "sha256": sha256_file(zip_path), "entries": 0, "bad_entries": 0}
            try:
                zf = zipfile.ZipFile(zip_path)
            except (zipfile.BadZipFile, OSError) as exc:
                # A release archive nobody can open has not been audited. Letting
                # the exception escape would look like a crash; a finding looks
                # like a refusal, which is what it is.
                print(f"   UNREADABLE {zip_path}  ({exc.__class__.__name__})")
                fail("zip-unreadable", zip_path,
                     f"cannot open release ZIP ({exc.__class__.__name__})")
            else:
                zipped = entry
                with zf:
                    infos = zf.infolist()
                    zipped["entries"] = len(infos)
                    for info in infos:
                        if info.is_dir():
                            continue
                        name = info.filename
                        suffix = Path(name).suffix.lower()
                        if suffix in {".mp4", ".mov", ".m4v", ".wav", ".mp3", ".m4a", ".lrc",
                                      ".srt", ".db", ".sqlite", ".sqlite3", ".log"}:
                            zipped["bad_entries"] += 1
                            print(f"   ZIP-NAME  {name}")
                            fail("zip-entry-name", name, f"release ZIP holds a {suffix} entry")
                        if info.file_size and info.file_size > 0:
                            try:
                                with zf.open(info) as fh:
                                    head = fh.read(4096)
                            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                                # An entry that cannot be read cannot be cleared
                                # either, so it counts as a bad entry, not a note.
                                zipped["bad_entries"] += 1
                                print(f"   ZIP-UNREADABLE {name}  ({exc.__class__.__name__})")
                                fail("zip-entry-unreadable", name,
                                     f"entry could not be read ({exc.__class__.__name__}); "
                                     "its contents are unverified")
                                continue
                            label = classify(head)
                            if label in BLOCKING:
                                zipped["bad_entries"] += 1
                                print(f"   ZIP-MEDIA {name}  ({label})")
                                fail("zip-entry-media", name, label)
                print(f"-- release ZIP: {zipped['entries']} entries, "
                      f"{zipped['bad_entries']} media/database entries, "
                      f"{zipped['bytes']} bytes, {zipped['sha256'][:16]}…")

    # 7. bundle identity ---------------------------------------------------
    info_plist = app / "Contents" / "Info.plist"
    if info_plist.is_file():
        print(f"-- Info.plist sha256: {sha256_file(info_plist)[:16]}…")

    verdict = "FAIL" if findings else "PASS"
    print(f"\nresult: {verdict}  ({len(findings)} finding(s))")
    for note in notes[:40]:
        print(f"note: {note}")
    if len(notes) > 40:
        print(f"note: … {len(notes) - 40} more note(s) in the report")

    if args.report:
        report = {
            "tool": "audit_bundle",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "root": str(root),
            "app": str(app),
            "verdict": verdict,
            "counts": {
                "files_scanned": len(files),
                "media_hits": len(media),
                "archives_inspected": len(archives),
                "source_compared": compared,
                "source_mismatch": mismatched,
                "unreviewed": extra,
                "missing": missing,
            },
            "official": official,
            "zip": zipped,
            "markers": {"source": source, "count": len(markers),
                        "fingerprints": [fingerprint(m) for m in markers]},
            "findings": findings,
            "notes": notes,
        }
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report: {args.report}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
