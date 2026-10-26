#!/usr/bin/env python3
# -*- mode: python ; coding: utf-8 -*-
"""Pre-build privacy gate for the macOS bundle.

Runs before PyInstaller and refuses to build when the inputs contain something
nobody has reviewed. It is deliberately blunt: a build that stops for a minute
is cheaper than a release that carries a user's file.

What it checks, in order:

1. ``bundle_manifest`` violations -- files outside the reviewed allowlist, user
   media, databases, logs or nested archives inside ``static/`` or ``assets/``.
2. Credential shapes anywhere in the inputs (``.env``, private keys, cloud
   tokens) plus the usual secret-looking literals in bundled text.
3. Absolute home-directory paths inside bundled text files: those leak the
   developer's account name into a resource the app serves verbatim.
4. Caller-supplied markers -- the private file names or asset ids that must
   never appear again. They are read from ``PHRASYNC_PRIVATE_MARKERS`` (comma
   separated) or a ``.privacy-markers`` file in the repo root, never from this
   script: hard-coding them here would republish them in the source tree. When
   no marker is supplied the scan is skipped and the report says so.

Exit code 0 means "safe to build", 1 means "stop".

Usage:
    python3 packaging/macos/privacy_gate.py --root . [--report out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bundle_manifest  # noqa: E402

TEXT_SUFFIXES = {
    ".js", ".css", ".html", ".htm", ".svg", ".json", ".txt", ".md",
    ".py", ".sh", ".spec", ".toml", ".cfg", ".ini", ".yml", ".yaml", ".webmanifest",
}

SECRET_NAME_PATTERNS = (
    re.compile(r"^\.env($|\.)"),
    re.compile(r"\.(key|p12|pfx|mobileprovision|keystore)$", re.I),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)$"),
    re.compile(r"^(credentials|secrets)\.(json|ya?ml|txt)$", re.I),
)

# ``.pem``/``.crt`` are decided by content: a public CA bundle is fine, a private
# key is not. Matching on the extension alone refuses certifi's cacert.pem.
PEM_NAME_PATTERN = re.compile(r"\.(pem|crt|cer)$", re.I)

SECRET_CONTENT_PATTERNS = (
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("github-token", re.compile(r"\b(ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
)

HOME_PATH = re.compile(r"/Users/[A-Za-z0-9._\-]+/")
MAX_TEXT_BYTES = 4 * 1024 * 1024


def marker_values(root: Path) -> tuple[list[str], str]:
    """Markers to hunt for, and where they came from (for the report)."""
    env = os.environ.get("PHRASYNC_PRIVATE_MARKERS", "").strip()
    if env:
        values = [v.strip() for v in env.split(",") if v.strip()]
        return values, "env:PHRASYNC_PRIVATE_MARKERS"
    path = root / ".privacy-markers"
    if path.is_file():
        values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.startswith("#")]
        return values, ".privacy-markers"
    return [], "none"


def fingerprint(value: str) -> str:
    """Stable short id so a report can name a marker without printing it."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def scan_path_for_markers(path: Path, markers: list[bytes],
                          chunk: int = 8 * 1024 * 1024) -> tuple[bool, list[str]]:
    """Search a whole file for byte markers, streaming so no size is a blind spot.

    Reading only the head of a large file would report "0 hits" for content that
    was never looked at. The overlap keeps a marker that straddles two chunks
    from being missed. Returns ``(found, problems)``; a non-empty ``problems``
    means the file could not be read and the caller must not treat it as clean.
    """
    if not markers:
        return False, []
    overlap = max(len(marker) for marker in markers) - 1
    tail = b""
    try:
        with path.open("rb") as handle:
            while True:
                block = handle.read(chunk)
                if not block:
                    return False, []
                window = tail + block
                if any(marker in window for marker in markers):
                    return True, []
                tail = window[-overlap:] if overlap > 0 else b""
    except OSError as exc:
        return False, [exc.__class__.__name__]


def main() -> int:
    parser = argparse.ArgumentParser(description="Refuse to build on unreviewed inputs.")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--report", default="", help="write a JSON report here")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings: list[dict] = []
    notes: list[str] = []

    def fail(kind: str, subject: str, detail: str) -> None:
        findings.append({"severity": "fail", "kind": kind, "subject": str(subject), "detail": detail})

    print("== privacy gate ==")
    print(f"root: {root}")

    # 1. allowlist ---------------------------------------------------------
    datas, exclusions, violations = bundle_manifest.collect(root)
    print(f"-- bundle inputs: {len(datas)} admitted, {len(exclusions)} held out, "
          f"{len(violations)} refused")
    for shown, reason in exclusions:
        print(f"   held out  {shown}  ({reason})")
    for shown, reason in violations:
        print(f"   REFUSED   {shown}  ({reason})")
        fail("bundle-input", shown, reason)

    # 2. credentials -------------------------------------------------------
    inputs = [root / "static", root / "assets"]
    for base in inputs:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(p.match(path.name) for p in SECRET_NAME_PATTERNS):
                print(f"   SECRET    {path.relative_to(root)}")
                fail("credential-file", path.relative_to(root), "credential-shaped file name")
            elif PEM_NAME_PATTERN.search(path.name) and bundle_manifest.carries_private_key(path):
                print(f"   SECRET    {path.relative_to(root)}  (private key)")
                fail("credential-file", path.relative_to(root), "PEM container holds a private key")

    scanned_text = 0
    for source, _dest in datas:
        path = Path(source)
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            size = path.stat().st_size
            if size > MAX_TEXT_BYTES:
                print(f"   UNSCANNED {path.relative_to(root)}  ({size} bytes)")
                fail("unscannable-text", path.relative_to(root),
                     f"{size} bytes exceeds the {MAX_TEXT_BYTES}-byte secret scan limit; "
                     "raise MAX_TEXT_BYTES deliberately or split the file")
                continue
            text = path.read_bytes().decode("utf-8", "replace")
        except OSError as exc:
            print(f"   UNREADABLE {path.relative_to(root)}  ({exc.__class__.__name__})")
            fail("unreadable-file", path.relative_to(root),
                 f"cannot read bundled text file ({exc.__class__.__name__}); "
                 "secrets and home paths unverified")
            continue
        scanned_text += 1
        for label, pattern in SECRET_CONTENT_PATTERNS:
            if pattern.search(text):
                print(f"   SECRET    {path.relative_to(root)}  ({label})")
                fail("credential-literal", path.relative_to(root), label)

        for match in HOME_PATH.finditer(text):
            print(f"   HOME-PATH {path.relative_to(root)}  {match.group(0)}")
            fail("absolute-home-path", path.relative_to(root),
                 f"bundled text names a home directory: {match.group(0)}")
            break

    # 3. nested archives ---------------------------------------------------
    for base in inputs:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in bundle_manifest.ARCHIVE_SUFFIXES:
                print(f"   ARCHIVE   {path.relative_to(root)}")
                fail("nested-archive", path.relative_to(root),
                     f"{path.suffix} inside the bundle inputs")

    # 4. caller-supplied markers ------------------------------------------
    markers, source = marker_values(root)
    if not markers:
        notes.append("marker scan skipped: no PHRASYNC_PRIVATE_MARKERS or .privacy-markers")
        print("-- marker scan: skipped (no markers supplied)")
    else:
        raw = [m.encode("utf-8") for m in markers]
        print(f"-- marker scan: {len(markers)} marker(s) from {source}")
        hits = []
        for base in inputs:
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                if any(m.decode("utf-8") in path.name for m in raw):
                    hits.append(path)
                    continue
                found, problems = scan_path_for_markers(path, raw)
                if found:
                    hits.append(path)
                for reason in problems:
                    print(f"   UNREADABLE {path.relative_to(root)}  (marker scan, {reason})")
                    fail("unreadable-file", path.relative_to(root),
                         f"marker scan could not read the file ({reason}); "
                         "its contents are unverified, not clean")
        for path in sorted(set(hits)):
            print(f"   MARKER    {path.relative_to(root)}")
            fail("private-marker", path.relative_to(root), "matches a supplied private marker")
        print(f"   markers checked: {', '.join(fingerprint(m) for m in markers)}")

    print(f"-- text files inspected for secrets/home paths: {scanned_text}")

    verdict = "FAIL" if findings else "PASS"
    print(f"\nresult: {verdict}  ({len(findings)} finding(s))")
    for note in notes:
        print(f"note: {note}")

    if args.report:
        report = {
            "tool": "privacy_gate",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "root": str(root),
            "verdict": verdict,
            "counts": {
                "admitted": len(datas),
                "held_out": len(exclusions),
                "refused": len(violations),
                "text_scanned": scanned_text,
            },
            "markers": {"source": source, "count": len(markers),
                        "fingerprints": [fingerprint(m) for m in markers]},
            "held_out": [{"path": p, "reason": r} for p, r in exclusions],
            "findings": findings,
            "notes": notes,
        }
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report: {args.report}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
