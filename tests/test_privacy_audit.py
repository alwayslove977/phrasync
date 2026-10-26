"""Regression tests for the build-time privacy controls.

Three scripts guard a release: ``bundle_manifest`` decides what may enter the
bundle, ``privacy_gate`` refuses to start a build from an unreviewed tree, and
``audit_bundle`` refuses to bless a finished bundle. They only work if their
failures are hard failures, so every test here asserts the *exit path* -- a
script that notices a problem and still passes is the failure mode these tests
exist to prevent.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parent.parent / "packaging" / "macos"
sys.path.insert(0, str(PACKAGING))

import audit_bundle  # noqa: E402
import bundle_manifest  # noqa: E402
import privacy_gate  # noqa: E402


def _run(script: Path, *args: str, markers: str = "") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("PHRASYNC_PRIVATE_MARKERS", None)
    env.pop("PHRASYNC_HOME", None)
    if markers:
        env["PHRASYNC_PRIVATE_MARKERS"] = markers
    return subprocess.run([sys.executable, "-B", str(script), *args],
                          env=env, capture_output=True, text=True)


def _fixture(root: Path, omit: tuple[str, ...] = (),
             mirror: tuple[str, ...] = ("static", "assets")) -> tuple[Path, Path]:
    """A minimal repository plus a bundle that mirrors it exactly.

    ``omit`` drops source paths (prefix match) and ``mirror`` decides which trees
    reach the bundle. Absence is built in from the start rather than created and
    then deleted: the tests must describe a bundle that never had the file, not
    one that lost it, and deleting would make the suite depend on the ability to
    remove files inside the temporary directory.

    Returns ``(repo, app)``. Both are clean: the audit must PASS on them before
    a test withholds something, otherwise a failure could not be attributed.
    """
    repo = root / "repo"
    files = {
        "static/index.html": b"<!doctype html><title>t</title>",
        "static/app.js": b"console.log('phrasync');\n",
        "assets/Phrasync.png": b"\x89PNG\r\n\x1a\n icon",
        "assets/style_reference.png": b"\x89PNG\r\n\x1a\n style",
        "assets/NotoSansJP-VF.ttf": b"\x00\x01\x00\x00 font",
        "assets/browser/chrome-headless-shell-mac-x64/chrome-headless-shell": b"#!bin",
        "assets/models/whisper-tiny/model.bin": b"model",
        "docs/media/phrasync-demo.mp4": b"demo",
    }
    for rel, payload in files.items():
        if any(rel.startswith(prefix) for prefix in omit):
            continue
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    app = root / "Phrasync.app"
    resources = app / "Contents" / "Resources"
    resources.mkdir(parents=True, exist_ok=True)
    for sub in mirror:
        source = repo / sub
        if not source.is_dir():
            continue
        for path in source.rglob("*"):
            if path.is_file():
                target = resources / sub / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
    (app / "Contents" / "Info.plist").write_bytes(b"<plist/>")
    return repo, app


def _audit(repo: Path, app: Path, *extra: str, markers: str = "") -> subprocess.CompletedProcess:
    return _run(PACKAGING / "audit_bundle.py", "--root", str(repo), "--app", str(app),
                *extra, markers=markers)


# --------------------------------------------------------------- manifest rules

def test_manifest_admits_the_reviewed_files(tmp_path):
    repo, _app = _fixture(tmp_path)
    datas, exclusions, violations = bundle_manifest.collect(repo)
    assert violations == []
    assert exclusions == []
    admitted = {Path(dest).as_posix() for _src, dest in datas}
    assert "static" in admitted
    assert "assets" in admitted


def test_manifest_refuses_a_media_file_in_static(tmp_path):
    repo, _app = _fixture(tmp_path)
    (repo / "static" / "field-notes.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    _datas, _exclusions, violations = bundle_manifest.collect(repo)
    shown = [path for path, _reason in violations]
    assert "static/field-notes.mp4" in shown


def test_manifest_refuses_an_unreviewed_suffix(tmp_path):
    repo, _app = _fixture(tmp_path)
    (repo / "static" / "notes.bin").write_bytes(b"x")
    _datas, _exclusions, violations = bundle_manifest.collect(repo)
    assert any("notes.bin" in path for path, _reason in violations)


def test_manifest_holds_out_editor_debris_instead_of_failing(tmp_path):
    repo, _app = _fixture(tmp_path)
    (repo / "static" / "app.js.bak").write_bytes(b"old")
    (repo / "static" / ".DS_Store").write_bytes(b"meta")
    _datas, exclusions, violations = bundle_manifest.collect(repo)
    held = {path for path, _reason in exclusions}
    assert "static/app.js.bak" in held
    assert "static/.DS_Store" in held
    assert violations == []


def test_manifest_refuses_an_unaudited_asset_directory(tmp_path):
    repo, _app = _fixture(tmp_path)
    (repo / "assets" / "scratch").mkdir()
    (repo / "assets" / "scratch" / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    _datas, _exclusions, violations = bundle_manifest.collect(repo)
    assert any("assets/scratch" in path for path, _reason in violations)


def test_manifest_refuses_when_an_audited_tree_is_missing(tmp_path):
    repo, _app = _fixture(tmp_path, omit=("assets/models/",))
    _datas, _exclusions, violations = bundle_manifest.collect(repo)
    assert any("assets/models" in path for path, _reason in violations)


def test_private_key_is_detected_by_content_not_extension(tmp_path):
    public = tmp_path / "cacert.pem"
    public.write_bytes(b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    private = tmp_path / "deploy.pem"
    private.write_bytes(b"-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----\n")
    assert bundle_manifest.carries_private_key(public) is False
    assert bundle_manifest.carries_private_key(private) is True


def test_private_key_check_is_fail_closed_on_an_unreadable_file(tmp_path):
    """'I could not look' must never be reported as 'there is nothing there'."""
    secret = tmp_path / "secret.pem"
    secret.write_bytes(b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    secret.chmod(0)
    try:
        if os.access(secret, os.R_OK):  # running as root: the bit means nothing
            pytest.skip("permissions are not enforced for this user")
        assert bundle_manifest.carries_private_key(secret) is True
    finally:
        secret.chmod(stat.S_IRUSR | stat.S_IWUSR)


# ------------------------------------------------------------- pre-build gate

def test_gate_passes_a_clean_tree(tmp_path):
    repo, _app = _fixture(tmp_path)
    result = _run(PACKAGING / "privacy_gate.py", "--root", str(repo))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "result: PASS" in result.stdout


def test_gate_fails_on_a_file_outside_the_allowlist(tmp_path):
    repo, _app = _fixture(tmp_path)
    (repo / "static" / "voiceover.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    result = _run(PACKAGING / "privacy_gate.py", "--root", str(repo))
    assert result.returncode == 1
    assert "voiceover.mp4" in result.stdout
    assert "result: FAIL" in result.stdout


def test_gate_fails_on_a_supplied_private_marker(tmp_path):
    repo, _app = _fixture(tmp_path)
    (repo / "static" / "app.js").write_bytes(b"const clip = 'holiday-2024-final';\n")
    result = _run(PACKAGING / "privacy_gate.py", "--root", str(repo),
                  markers="holiday-2024-final")
    assert result.returncode == 1
    assert "MARKER" in result.stdout
    assert "holiday-2024-final" not in result.stdout, "the gate must not echo the marker"


def test_gate_finds_a_marker_past_the_first_chunk(tmp_path):
    """A marker scan that only reads the head of a file reports false zeros."""
    repo, _app = _fixture(tmp_path)
    padding = b"A" * (9 * 1024 * 1024)
    (repo / "assets/models/whisper-tiny/model.bin").write_bytes(padding + b"NEEDLE-TOKEN")
    result = _run(PACKAGING / "privacy_gate.py", "--root", str(repo), markers="NEEDLE-TOKEN")
    assert result.returncode == 1
    assert "MARKER" in result.stdout


def test_gate_fails_on_bundled_text_it_cannot_scan(tmp_path):
    """A file too large for the secret scan is refused, not waved through."""
    repo, _app = _fixture(tmp_path)
    (repo / "static" / "app.js").write_bytes(b"x" * 64)
    result = subprocess.run(
        [sys.executable, "-B", "-c",
         "import sys; sys.path.insert(0, {path!r});"
         "import privacy_gate; privacy_gate.MAX_TEXT_BYTES = 16;"
         "sys.argv = ['privacy_gate.py', '--root', {root!r}];"
         "sys.exit(privacy_gate.main())".format(path=str(PACKAGING), root=str(repo))],
        capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "UNSCANNED" in result.stdout


# ------------------------------------------------------------ post-build audit

def test_audit_passes_a_clean_bundle(tmp_path):
    repo, app = _fixture(tmp_path)
    result = _audit(repo, app)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "result: PASS" in result.stdout


def _audit_with_report(repo: Path, app: Path, tmp_path: Path, *extra: str):
    """Run the audit with a report and return ``(result, findings kinds)``.

    The human-readable stdout and the machine-readable report are two views of
    one verdict; the kinds only exist in the report, so the tests assert there.
    """
    report = tmp_path / "audit-report.json"
    result = _audit(repo, app, "--report", str(report), *extra)
    if not report.is_file():
        return result, set()
    payload = json.loads(report.read_text(encoding="utf-8"))
    return result, {item["kind"] for item in payload["findings"]}


@pytest.mark.parametrize("tree", ["static", "assets"])
def test_audit_fails_when_a_whole_tree_is_absent_from_the_bundle(tmp_path, tree):
    """The regression that used to pass silently as "0 compared, 0 missing".

    A build that loses the entire UI reported no missing files because there was
    nothing to walk; the audit has to fail on the absence itself.
    """
    repo, app = _fixture(tmp_path, mirror=tuple(t for t in ("static", "assets") if t != tree))
    result, kinds = _audit_with_report(repo, app, tmp_path)
    assert result.returncode == 1
    assert "missing-tree" in kinds
    assert "entire tree absent" in result.stdout


def test_audit_fails_when_the_source_tree_exists_but_the_bundle_mirrors_nothing(tmp_path):
    """No Resources/static and no Frameworks/static at all -- the silent case."""
    repo, app = _fixture(tmp_path, mirror=())
    result, kinds = _audit_with_report(repo, app, tmp_path)
    assert result.returncode == 1
    assert "missing-tree" in kinds
    assert "entire tree absent" in result.stdout


def test_audit_fails_on_media_smuggled_into_the_bundle(tmp_path):
    repo, app = _fixture(tmp_path)
    smuggled = app / "Contents" / "Resources" / "static" / "clip.dat"
    smuggled.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    result, kinds = _audit_with_report(repo, app, tmp_path)
    assert result.returncode == 1
    assert "media-signature" in kinds


def test_audit_fails_on_a_bundled_file_with_no_source(tmp_path):
    repo, app = _fixture(tmp_path)
    (app / "Contents" / "Resources" / "static" / "extra.js").write_bytes(b"// nobody chose this")
    result, kinds = _audit_with_report(repo, app, tmp_path)
    assert result.returncode == 1
    assert "unreviewed-file" in kinds


def test_audit_fails_when_the_bundle_disagrees_with_the_source(tmp_path):
    repo, app = _fixture(tmp_path)
    (app / "Contents" / "Resources" / "static" / "app.js").write_bytes(b"// different bytes!\n")
    result, kinds = _audit_with_report(repo, app, tmp_path)
    assert result.returncode == 1
    assert "source-mismatch" in kinds


def test_audit_fails_on_an_archive_it_did_not_open(tmp_path):
    """gzip is recognised by magic but never opened, so it cannot be cleared."""
    repo, app = _fixture(tmp_path)
    (app / "Contents" / "Resources" / "static" / "payload.gz").write_bytes(
        b"\x1f\x8b\x08\x00" + b"\x00" * 64)
    result, kinds = _audit_with_report(repo, app, tmp_path)
    assert result.returncode == 1
    assert "unopened-archive" in kinds


def test_audit_fails_on_a_corrupt_release_zip(tmp_path):
    repo, app = _fixture(tmp_path)
    broken = tmp_path / "release.zip"
    broken.write_bytes(b"PK\x03\x04 definitely not a zip")
    result, kinds = _audit_with_report(repo, app, tmp_path, "--zip", str(broken))
    assert result.returncode == 1
    assert "zip-unreadable" in kinds


def test_audit_rejects_a_release_zip_holding_media_entries(tmp_path):
    import zipfile

    repo, app = _fixture(tmp_path)
    release = tmp_path / "release.zip"
    with zipfile.ZipFile(release, "w") as archive:
        archive.writestr("Phrasync.app/Contents/Resources/static/app.js", b"console.log(1)")
        archive.writestr("Phrasync.app/Contents/Resources/static/holiday.mp4",
                         b"\x00\x00\x00\x18ftypmp42")
    result, kinds = _audit_with_report(repo, app, tmp_path, "--zip", str(release))
    assert result.returncode == 1
    assert "zip-entry-name" in kinds


def test_audit_writes_a_report_whose_verdict_matches_the_exit_code(tmp_path):
    repo, app = _fixture(tmp_path)
    report = tmp_path / "audit.json"
    result = _audit(repo, app, "--report", str(report))
    assert result.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["findings"] == []
    assert payload["counts"]["source_compared"] > 0


def test_audit_failure_is_recorded_in_the_report(tmp_path):
    repo, app = _fixture(tmp_path, mirror=())
    report = tmp_path / "audit-fail.json"
    result = _audit(repo, app, "--report", str(report))
    assert result.returncode == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["verdict"] == "FAIL"
    assert any(item["kind"] == "missing-tree" for item in payload["findings"])
