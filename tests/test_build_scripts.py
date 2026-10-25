"""Both macOS build drivers must fail when the bundle is missing required assets.

A hollow ``Phrasync.app`` installs and launches, then dies on export (no bundled
browser) or on transcription (no model). The build scripts used to print
``MISSING`` and still exit 0, so nothing downstream could notice. These tests
pin the exit status instead of the message, without running PyInstaller: the
Python driver runs against a stubbed build pipeline, and the shell driver is
executed in a throwaway repo whose build venv is a stub interpreter.

The last group executes ``packaging/macos/Phrasync.spec`` itself, also with
PyInstaller stubbed, to check which data files it hands to ``COLLECT`` and that
it refuses to build when one of the seven AI packages is importable but ships
none of the resource the bundle needs from it.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import platform
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD_PY = ROOT / "packaging" / "macos" / "build_app.py"
BUILD_SH = ROOT / "packaging" / "macos" / "build_app.sh"
SPEC = ROOT / "packaging" / "macos" / "Phrasync.spec"
INSTALL_WHEELS = ROOT / "packaging" / "macos" / "install_wheels.py"

# Mirrors the path the shell driver reports for the arch it is building.
BROWSER_ARCH = "arm64" if platform.machine() == "arm64" else "x64"

# Every path build_app.sh verifies, relative to Phrasync.app.
SHELL_REQUIRED = [
    "Contents/Info.plist",
    "Contents/MacOS/Phrasync",
    "Contents/Frameworks/static/index.html",
    "Contents/Frameworks/static/app.js",
    "Contents/Frameworks/assets/NotoSansJP-VF.ttf",
    f"Contents/Frameworks/assets/browser/chrome-headless-shell-mac-{BROWSER_ARCH}/chrome-headless-shell",
    "Contents/Frameworks/assets/models/whisper-tiny/model.bin",
]

# The FFmpeg binary is matched by pattern, never by exact name: imageio_ffmpeg
# encodes the platform, architecture and release into it. This is what a real
# macOS bundle carries today, so the stubs below use the same shape.
FFMPEG_PATTERN = "Contents/Frameworks/imageio_ffmpeg/binaries/ffmpeg-*"
FFMPEG_REL = "Contents/Frameworks/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"


@pytest.fixture()
def workspace():
    """A throwaway tree under the system temp dir (pytest's own basetemp is not
    always writable in managed environments)."""
    path = Path(tempfile.mkdtemp(prefix="phrasync-build-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def load_build_py() -> types.ModuleType:
    """Load the driver without importing it, so no __pycache__ lands in packaging/."""
    module = types.ModuleType("phrasync_build_app")
    module.__file__ = str(BUILD_PY)
    source = BUILD_PY.read_text(encoding="utf-8")
    exec(compile(source, str(BUILD_PY), "exec"), module.__dict__)
    return module


def make_bundle(path: Path, layout: list[str], *, omit: tuple[str, ...] = ()) -> Path:
    for rel in layout:
        if rel in omit:
            continue
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stub", encoding="utf-8")
    return path


def make_source_tree(workspace: Path, module: types.ModuleType, *, browser: str = "executable") -> Path:
    """A throwaway source checkout holding what the pre-build check reads.

    ``assets/browser`` is git-ignored (a downloaded runtime), so no test may rely
    on the working tree carrying it. ``ARCH`` comes from the driver itself, which
    keeps the fixture pointed at exactly the path the driver computes.
    """
    repo = workspace / "repo"
    target = (repo / "assets" / "browser" / f"chrome-headless-shell-mac-{module.ARCH}"
              / "chrome-headless-shell")
    target.parent.mkdir(parents=True)
    if browser != "missing":
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if browser == "executable":
        target.chmod(0o755)
    elif browser == "not-executable":
        target.chmod(0o644)
    return repo


def run_build_py_main(monkeypatch, workspace: Path, *, omit: tuple[str, ...] = (),
                      omit_ffmpeg: bool = False, browser: str = "executable") -> tuple[int, str, str]:
    """Run main() with the actual build steps stubbed out; returns (code, stdout, stderr)."""
    module = load_build_py()
    bundle = make_bundle(workspace / "Phrasync.app", module.required_layout(), omit=omit)
    if not omit_ffmpeg:
        make_bundle(bundle, [FFMPEG_REL])
    module.ROOT = make_source_tree(workspace, module, browser=browser)
    module.APP = bundle
    module.DIST = workspace / "dist"
    module.BUILD_DIR = workspace / "build"
    module.LOG_DIR = workspace / "build" / "logs"
    module.build_environment = lambda: {}
    module.ensure_venv = lambda env: Path(sys.executable)
    module.pip_install = lambda *args, **kwargs: None
    module.run = lambda *args, **kwargs: None
    monkeypatch.setattr(sys, "argv", ["build_app.py", "--fast"])

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main()
    return code, out.getvalue(), err.getvalue()


def run_build_py_prebuild(monkeypatch, workspace: Path, *, browser: str) -> tuple[int, str, str]:
    """Run main() with every build step replaced by a tripwire.

    A refusal has to happen before the venv exists, so reaching any step raises
    instead of being silently stubbed away: the assertion then covers the control
    flow and not just the wording of the message.
    """
    module = load_build_py()
    module.ROOT = make_source_tree(workspace, module, browser=browser)
    module.APP = workspace / "dist" / "Phrasync.app"
    module.DIST = workspace / "dist"
    module.BUILD_DIR = workspace / "build"
    module.LOG_DIR = workspace / "build" / "logs"

    def tripwire(name):
        def step(*args, **kwargs):
            raise AssertionError(f"{name} ran before the export browser was validated")
        return step

    module.build_environment = tripwire("build_environment")
    module.ensure_venv = tripwire("ensure_venv")
    module.pip_install = tripwire("pip_install")
    module.run = tripwire("run")
    monkeypatch.setattr(sys, "argv", ["build_app.py", "--fast"])

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main()
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------- Python


def test_python_driver_fails_when_a_required_asset_is_missing(monkeypatch, workspace):
    missing = "Contents/Frameworks/assets/models/whisper-tiny/model.bin"
    code, out, err = run_build_py_main(monkeypatch, workspace, omit=(missing,))
    assert code == 1, "a bundle without the model must not report success"
    assert f"MISSING: {missing}" in out
    assert "the bundle is incomplete: 1 required path(s) missing" in err
    assert missing in err, "the error must name the absent path"


def test_python_driver_fails_when_app_js_is_missing(monkeypatch, workspace):
    """The shell driver always required static/app.js while this one did not.

    ``index.html`` alone loads nothing: without ``static/app.js`` the window
    opens to a blank UI, so the Python driver has to fail the same way instead of
    reporting a successful build for a bundle only it considers complete.
    """
    missing = "Contents/Frameworks/static/app.js"
    code, out, err = run_build_py_main(monkeypatch, workspace, omit=(missing,))
    assert code == 1, "a bundle without static/app.js must not report success"
    assert f"MISSING: {missing}" in out
    assert "the bundle is incomplete: 1 required path(s) missing" in err
    assert missing in err, "the error must name the absent script"


def test_python_and_shell_drivers_require_the_same_assets():
    """Both drivers claim to produce the same .app, so their lists must match.

    ``SHELL_REQUIRED`` is what the shell driver verifies — the shell end-to-end
    tests build a bundle from it and assert both the exit status and the count of
    missing paths, so it cannot drift from ``build_app.sh`` unnoticed.
    """
    module = load_build_py()
    assert module.required_layout() == SHELL_REQUIRED
    assert module.required_globs() == [FFMPEG_PATTERN]


def test_python_driver_stops_before_building_when_the_browser_is_missing(monkeypatch, workspace):
    """No browser in the source tree means every export fails; say so up front.

    The build used to run to completion first, because the only check lived after
    PyInstaller. ``run_build_py_prebuild`` raises if any build step is reached, so
    this pins the control flow as well as the message.
    """
    code, out, err = run_build_py_prebuild(monkeypatch, workspace, browser="missing")
    browser = (workspace / "repo" / "assets" / "browser"
               / f"chrome-headless-shell-mac-{BROWSER_ARCH}" / "chrome-headless-shell")
    assert code == 1, "a build with no export browser must not report success"
    assert "the bundled export browser for" in err
    assert str(browser) in err, "the error must name the path it looked for"
    assert "playwright install chromium-headless-shell" in err
    assert "MISSING" not in out, "the bundle was never reached"


def test_python_driver_stops_before_building_when_the_browser_is_not_executable(monkeypatch, workspace):
    """PyInstaller keeps the executable bit only if the source has it.

    A 0644 browser therefore ships as a 0644 browser, and the app only looks for
    ``is_file()`` before spawning it — the failure would land on the user's first
    export. The driver has to refuse before spending a full build.
    """
    code, out, err = run_build_py_prebuild(monkeypatch, workspace, browser="not-executable")
    browser = (workspace / "repo" / "assets" / "browser"
               / f"chrome-headless-shell-mac-{BROWSER_ARCH}" / "chrome-headless-shell")
    assert code == 1, "a non-executable export browser must not report success"
    assert "not executable" in err
    assert str(browser) in err, "the error must name the file to fix"
    assert "chmod +x" in err


def test_python_driver_succeeds_when_the_layout_is_complete(monkeypatch, workspace):
    code, out, err = run_build_py_main(monkeypatch, workspace)
    assert code == 0, f"a complete bundle must still build, stderr was: {err}"
    assert "MISSING" not in out
    assert "!!" not in err


def test_python_driver_fails_when_ffmpeg_is_missing(monkeypatch, workspace):
    """No FFmpeg in the bundle means every MP4 export fails; the build must say so."""
    code, out, err = run_build_py_main(monkeypatch, workspace, omit_ffmpeg=True)
    assert code == 1, "a bundle without FFmpeg must not report success"
    assert f"MISSING: {FFMPEG_PATTERN}" in out
    assert "the bundle is incomplete: 1 required path(s) missing" in err
    assert FFMPEG_PATTERN in err, "the error must name the absent encoder"


def test_python_driver_accepts_a_bundled_ffmpeg_of_any_name(monkeypatch, workspace):
    """The check is the directory plus ffmpeg-*, not one release or architecture."""
    module = load_build_py()
    bundle = make_bundle(workspace / "other-arch.app", module.required_layout())
    make_bundle(bundle, ["Contents/Frameworks/imageio_ffmpeg/binaries/ffmpeg-macos-x86_64-v7.1"])
    assert module.verify_bundle_layout(bundle) == []


def test_verify_bundle_layout_reports_exactly_the_absent_paths(workspace):
    module = load_build_py()
    layout = module.required_layout()
    bundle = make_bundle(workspace / "partial.app", layout, omit=(layout[0], layout[-1]))
    make_bundle(bundle, [FFMPEG_REL])
    assert module.verify_bundle_layout(bundle) == [layout[0], layout[-1]]

    complete = make_bundle(workspace / "complete.app", layout)
    make_bundle(complete, [FFMPEG_REL])
    assert module.verify_bundle_layout(complete) == []


def test_verify_bundle_layout_flags_a_missing_ffmpeg(workspace):
    """The glob lives in its own list; it must never be compared literally."""
    module = load_build_py()
    bundle = make_bundle(workspace / "no-ffmpeg.app", module.required_layout())
    assert module.verify_bundle_layout(bundle) == [FFMPEG_PATTERN]

    # An empty binaries directory is the case a literal exists() would miss.
    (bundle / "Contents/Frameworks/imageio_ffmpeg/binaries").mkdir(parents=True)
    assert module.verify_bundle_layout(bundle) == [FFMPEG_PATTERN]


def test_verify_bundle_layout_rejects_a_directory_on_a_required_path(workspace):
    """exists() would accept a directory here; the shell driver never has.

    An entry point that is a directory is not a script, and a directory named
    ``static/app.js`` would leave the window with nothing to load while the build
    reported success.
    """
    module = load_build_py()
    bundle = make_bundle(workspace / "dir.app", module.required_layout())
    make_bundle(bundle, [FFMPEG_REL])

    target = bundle / "Contents/Frameworks/static/app.js"
    target.unlink()
    target.mkdir()
    assert module.verify_bundle_layout(bundle) == ["Contents/Frameworks/static/app.js"]

    # The stricter rule applies to every exact path, not just the script.
    plist = bundle / "Contents/Info.plist"
    plist.unlink()
    plist.mkdir()
    assert module.verify_bundle_layout(bundle) == [
        "Contents/Info.plist",
        "Contents/Frameworks/static/app.js",
    ]

    # A symlink to a real file is still a file for both drivers.
    (bundle / "Contents/Info.plist").rmdir()
    (bundle / "Contents/Info.plist").symlink_to(bundle / "Contents/MacOS/Phrasync")
    assert module.verify_bundle_layout(bundle) == ["Contents/Frameworks/static/app.js"]


def test_python_driver_required_list_covers_the_browser_and_the_model():
    """Guard against a future edit that trims the list back to the easy paths."""
    required = load_build_py().required_layout()
    assert any("chrome-headless-shell" in item for item in required)
    assert any(item.endswith("whisper-tiny/model.bin") for item in required)
    assert "Contents/Frameworks/static/index.html" in required
    assert "Contents/Frameworks/static/app.js" in required


# ---------------------------------------------------------------------- shell


def _fake_repo(workspace: Path) -> tuple[Path, Path]:
    """A disposable repo the shell driver can run end to end without PyInstaller."""
    repo = workspace / "repo"
    (repo / "packaging" / "macos").mkdir(parents=True)
    script = repo / "packaging" / "macos" / "build_app.sh"
    script.write_text(BUILD_SH.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o755)
    for name in ("requirements.txt", "requirements-ai.txt"):
        (repo / name).write_text("", encoding="utf-8")

    browser = repo / "assets" / "browser" / f"chrome-headless-shell-mac-{BROWSER_ARCH}" / "chrome-headless-shell"
    browser.parent.mkdir(parents=True)
    browser.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    browser.chmod(0o755)

    # Stands in for the build venv: answers -V and swallows pip/PyInstaller.
    venv = workspace / "venv"
    (venv / "bin").mkdir(parents=True)
    stub = venv / "bin" / "python"
    stub.write_text('#!/bin/sh\nif [ "$1" = "-V" ]; then echo "Python 3.13.0"; fi\nexit 0\n', encoding="utf-8")
    stub.chmod(0o755)
    return repo, venv


def _run_shell(workspace: Path, *, complete: bool) -> tuple[subprocess.CompletedProcess, str]:
    repo, venv = _fake_repo(workspace)
    app = repo / "dist" / "Phrasync.app"
    layout = list(SHELL_REQUIRED)
    if complete:
        make_bundle(app, layout + [FFMPEG_REL])
    else:
        # Only the plist exists: the classic "build succeeded, app is hollow" case.
        make_bundle(app, layout[:1])

    result = subprocess.run(
        ["bash", str(repo / "packaging" / "macos" / "build_app.sh"), "--fast", "--no-ai"],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "PHRASYNC_BUILD_VENV": str(venv)},
    )
    return result, _read_log(repo / "build" / "macos" / "logs", result.stdout + result.stderr)


def _read_log(logs_dir: Path, already: str, timeout: float = 5.0) -> str:
    """The driver pipes through tee, so wait briefly for the log to be flushed."""
    deadline = time.time() + timeout
    text = already
    while time.time() < deadline:
        files = sorted(logs_dir.glob("build-*.log")) if logs_dir.is_dir() else []
        if files:
            text = files[-1].read_text(encoding="utf-8", errors="replace")
            if "built:" in text or "incomplete" in text:
                return text
        time.sleep(0.05)
    return text


def test_shell_build_exits_nonzero_when_the_bundle_is_incomplete(workspace):
    result, log = _run_shell(workspace, complete=False)
    assert result.returncode != 0, f"the build reported success on a hollow bundle:\n{log}"
    assert "MISSING: Contents/Frameworks/static/index.html" in log
    assert "MISSING: Contents/Frameworks/assets/models/whisper-tiny/model.bin" in log
    expected = (len(SHELL_REQUIRED) - 1) + 1  # every path but the plist, plus FFmpeg
    assert f"the bundle is incomplete: {expected} required path(s) missing" in log
    assert "built:" not in log


def test_shell_build_still_succeeds_when_the_bundle_is_complete(workspace):
    result, log = _run_shell(workspace, complete=True)
    assert result.returncode == 0, f"a complete bundle must still build:\n{log}"
    assert "MISSING" not in log
    assert "built:" in log


# ----------------------------------------------------------------------- spec

# Editor backups that a working tree carries next to the runtime files. They are
# git-ignored, but PyInstaller copies a collected directory file by file.
SPEC_BACKUPS = [
    "static/app.js.bak",
    "static/app-ui.js.bak",
    "static/app.js.font-backup",
    "static/i18n.js.before_source_tracking.bak",
]

# Runtime files the filter must not touch, including one nested in vendor/.
SPEC_RUNTIME_STATIC = [
    "static/index.html",
    "static/app.js",
    "static/app-ui.js",
    "static/app-fonts.js",
    "static/i18n.js",
    "static/i18n-dom.js",
    "static/i18n-zh.js",
    "static/styles.css",
    "static/vendor/three.module.min.js",
]


def _spec_repo(workspace: Path) -> Path:
    """A disposable repo holding only what the spec reads, plus sample data."""
    repo = workspace / "spec-repo"
    spec = repo / "packaging" / "macos" / "Phrasync.spec"
    spec.parent.mkdir(parents=True)
    spec.write_text(SPEC.read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname = \"phrasync\"\nversion = \"0.4.7\"\n",
                                         encoding="utf-8")
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        (repo / name).write_text("stub\n", encoding="utf-8")
    for rel in SPEC_RUNTIME_STATIC + SPEC_BACKUPS + [
        "static/.DS_Store",
        "assets/NotoSansJP-VF.ttf",
        "assets/style_reference.png",
        "assets/.DS_Store",
    ]:
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stub\n", encoding="utf-8")
    return repo


# The seven packages the AI switch installs and the single resource each one
# must contribute. Mirrors packaging/macos/Phrasync.spec; the first test of the
# next group fails if the two ever drift apart. Binary-only packages are the
# ones whose payload is a native library, data-only ones ship models, and
# tokenizers ships a compiled module that PyInstaller only finds as a hidden
# import (tokenizers.abi3.so does not match PY_DYLIB_PATTERNS).
AI_RESOURCE_MINIMUMS = {
    "faster_whisper": "datas",
    "ctranslate2": "binaries",
    "onnxruntime": "binaries",
    "rapidocr_onnxruntime": "datas",
    "cv2": "binaries",
    "av": "binaries",
    "tokenizers": "hiddenimports",
}

AI_RESOURCE_LABELS = {
    "datas": "data files",
    "binaries": "native libraries",
    "hiddenimports": "hidden imports",
}


def _run_spec(monkeypatch, repo: Path, *, absent_ai: tuple[str, ...] = (),
              empty_resources: dict[str, tuple[str, ...]] | None = None,
              with_ai: bool = True, patch_find_spec: bool = True,
              expect_no_probe: bool = False, report: dict | None = None):
    """Execute the spec with PyInstaller stubbed; return (datas at COLLECT, namespace, report).

    Nothing is built: ``Analysis``/``PYZ``/``EXE``/``COLLECT``/``BUNDLE`` are
    stand-ins, and the real spec file is compiled as is, so the assertions below
    test the shipping rules rather than a copy of them. ``_expand`` mirrors
    PyInstaller 6.22 ``format_binaries_and_datas``: a file entry becomes one
    target, a directory entry one target per file below it.

    ``absent_ai`` names packages the simulated build interpreter cannot import.
    ``empty_resources`` maps a package to the categories its ``collect_all()``
    returns empty, so a test can silence exactly the category a package owes the
    bundle while the other two still yield something -- a check that only asked
    "did this package collect anything" would keep passing there. ``with_ai``
    drives the spec's own ``PHRASYNC_BUILD_AI`` switch, and ``expect_no_probe``
    turns either kind of AI access -- import resolution, ``collect_all`` or
    ``collect_dynamic_libs`` -- into a failure instead of a silent no-op. The
    ``report`` records what the spec did to the build: which packages it probed,
    collected and asked for dynamic libraries, what it handed to ``Analysis``,
    and whether it reached ``Analysis`` at all, so a test can assert an early
    abort instead of matching a message.
    """
    report = {} if report is None else report
    report.setdefault("probed", [])
    report.setdefault("collected", [])
    report.setdefault("dynamic_libs", [])
    report.setdefault("binaries", [])
    report.setdefault("hiddenimports", [])
    report.setdefault("analysis", 0)
    report.setdefault("datas", None)
    empty_resources = empty_resources or {}

    def _find_spec(name, package=None):
        if expect_no_probe:
            raise AssertionError(f"AI package {name!r} was probed although the pack is disabled")
        report["probed"].append(name)
        return None if name in absent_ai else object()

    if patch_find_spec:
        monkeypatch.setattr(importlib.util, "find_spec", _find_spec)
    if with_ai:
        monkeypatch.delenv("PHRASYNC_BUILD_AI", raising=False)
    else:
        monkeypatch.setenv("PHRASYNC_BUILD_AI", "0")

    def _stub_file(package: str, suffix: str) -> Path:
        stub = repo / "ai-stub" / package / f"{package}.{suffix}"
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("stub\n", encoding="utf-8")
        return stub

    def _collect_all(name):
        if expect_no_probe:
            raise AssertionError(f"AI package {name!r} was collected although the pack is disabled")
        report["collected"].append(name)
        empty = set(empty_resources.get(name, ()))
        package_datas = [] if "datas" in empty else [(str(_stub_file(name, "dat")), f"ai/{name}")]
        package_binaries = [] if "binaries" in empty else [(str(_stub_file(name, "dylib")), f"ai/{name}")]
        package_hidden = [] if "hiddenimports" in empty else [f"{name}._stub"]
        return package_datas, package_binaries, package_hidden

    def _collect_dynamic_libs(name):
        if expect_no_probe:
            raise AssertionError(
                f"collect_dynamic_libs({name!r}) ran although the pack is disabled"
            )
        report["dynamic_libs"].append(name)
        return []

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_all = _collect_all
    hooks.collect_data_files = lambda name: []
    hooks.collect_dynamic_libs = _collect_dynamic_libs
    hooks.collect_submodules = lambda name: []
    utils = types.ModuleType("PyInstaller.utils")
    utils.hooks = hooks
    package = types.ModuleType("PyInstaller")
    package.utils = utils
    for name, module in (
        ("PyInstaller", package),
        ("PyInstaller.utils", utils),
        ("PyInstaller.utils.hooks", hooks),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    def _expand(datas):
        entries = []
        for source, dest_dir in datas:
            source_path = Path(source)
            if source_path.is_file():
                dest = posixpath.normpath(f"{dest_dir}/{source_path.name}")
                entries.append((dest, str(source_path), "DATA"))
            elif source_path.is_dir():
                for item in sorted(source_path.rglob("*")):
                    if item.is_file():
                        rel = item.relative_to(source_path).as_posix()
                        entries.append((posixpath.normpath(f"{dest_dir}/{rel}"), str(item), "DATA"))
        return entries

    class _Analysis:
        def __init__(self, scripts, binaries=(), datas=(), hiddenimports=(), **kwargs):
            report["analysis"] += 1
            report["binaries"] = list(binaries)
            report["hiddenimports"] = list(hiddenimports)
            self.pure, self.scripts = [], []
            self.binaries = list(binaries)
            self.datas = _expand(datas)

    class _Target:
        def __init__(self, *args, **kwargs):
            pass

    class _Collect(_Target):
        def __init__(self, *args, **kwargs):
            report["datas"] = list(args[2])
            super().__init__(*args, **kwargs)

    class _Bundle(_Target):
        def __init__(self, *args, **kwargs):
            report["info_plist"] = dict(kwargs.get("info_plist") or {})
            super().__init__(*args, **kwargs)

    namespace = {
        "SPECPATH": str(repo / "packaging" / "macos"),
        "__file__": str(repo / "packaging" / "macos" / "Phrasync.spec"),
        "__name__": "__main__",
        "Analysis": _Analysis,
        "PYZ": _Target,
        "EXE": _Target,
        "COLLECT": _Collect,
        "BUNDLE": _Bundle,
    }
    exec(compile(SPEC.read_text(encoding="utf-8"), str(SPEC), "exec"), namespace)
    return report["datas"], namespace, report


def test_spec_keeps_editor_backups_out_of_the_bundle(monkeypatch, workspace):
    datas, _namespace, _report = _run_spec(monkeypatch, _spec_repo(workspace))
    dests = {dest for dest, _source, _typecode in datas}
    for backup in SPEC_BACKUPS:
        assert backup not in dests, f"{backup} would ship inside the bundle"
    assert "static/.DS_Store" not in dests
    assert "assets/.DS_Store" not in dests


def test_spec_still_bundles_every_runtime_static_file(monkeypatch, workspace):
    repo = _spec_repo(workspace)
    datas, _namespace, _report = _run_spec(monkeypatch, repo)
    dests = {dest for dest, _source, _typecode in datas}
    assert {dest for dest in dests if dest.startswith("static/")} == {
        f"static/{path.relative_to(repo / 'static').as_posix()}"
        for path in (repo / "static").rglob("*")
        if path.is_file()
    } - set(SPEC_BACKUPS) - {"static/.DS_Store"}
    for rel in SPEC_RUNTIME_STATIC:
        assert rel in dests
    # A documented reference image rather than a backup, so it stays bundled.
    assert "assets/style_reference.png" in dests
    assert "assets/NotoSansJP-VF.ttf" in dests


def test_spec_exclusion_matches_only_the_named_files(monkeypatch, workspace):
    _datas, namespace, _report = _run_spec(monkeypatch, _spec_repo(workspace))
    is_excluded = namespace["is_excluded_data"]
    assert all(is_excluded(backup) for backup in SPEC_BACKUPS)
    assert not is_excluded("static/app.js")
    assert not is_excluded("static/vendor/three.module.min.js")
    assert is_excluded("assets/.DS_Store")


def test_spec_requires_a_resource_minimum_for_every_ai_package(monkeypatch, workspace):
    """The rule table and the package list must cover each other exactly."""
    _datas, namespace, _report = _run_spec(monkeypatch, _spec_repo(workspace))
    assert namespace["AI_PACKAGES"] == list(AI_RESOURCE_MINIMUMS)
    assert namespace["AI_RESOURCE_MINIMUMS"] == AI_RESOURCE_MINIMUMS
    assert namespace["AI_RESOURCE_LABELS"] == AI_RESOURCE_LABELS


def test_spec_bundles_the_whole_ai_pack_on_a_complete_install(monkeypatch, workspace, capsys):
    """The control case: seven importable packages, each with its payload."""
    datas, _namespace, report = _run_spec(monkeypatch, _spec_repo(workspace))
    out = capsys.readouterr().out

    assert report["probed"] == list(AI_RESOURCE_MINIMUMS)
    assert report["collected"] == list(AI_RESOURCE_MINIMUMS)
    success = [line for line in out.splitlines() if line.startswith("AI pack collected:")]
    assert success == ["AI pack collected: " + ", ".join(AI_RESOURCE_MINIMUMS)]
    assert report["analysis"] == 1

    dests = {dest for dest, _source, _typecode in datas}
    for package in AI_RESOURCE_MINIMUMS:
        assert f"ai/{package}/{package}.dat" in dests

    # Binaries and hidden imports reach Analysis as well, not just datas.
    binary_sources = {Path(source).name for source, _dest in report["binaries"]}
    assert {"ctranslate2.dylib", "onnxruntime.dylib", "cv2.dylib", "av.dylib"} <= binary_sources
    assert {f"{package}._stub" for package in AI_RESOURCE_MINIMUMS} <= set(report["hiddenimports"])

    # ctranslate2's native library is also collected explicitly, inside the switch.
    assert report["dynamic_libs"] == ["ctranslate2"]


def test_spec_accepts_packages_that_leave_a_non_required_category_empty(
    monkeypatch, workspace, capsys
):
    """Only the kind in AI_RESOURCE_MINIMUMS is a minimum.

    faster_whisper ships no native library of its own, cv2 no data files, and
    tokenizers neither -- its payload is the compiled module that only shows up
    as a hidden import. A "all three categories non-empty" rule would fail this
    entirely healthy build.
    """
    empty = {
        "faster_whisper": ("binaries", "hiddenimports"),
        "cv2": ("datas", "hiddenimports"),
        "tokenizers": ("datas", "binaries"),
    }
    datas, _namespace, report = _run_spec(
        monkeypatch, _spec_repo(workspace), empty_resources=empty
    )
    out = capsys.readouterr().out

    assert report["analysis"] == 1
    assert "AI pack collected: " + ", ".join(AI_RESOURCE_MINIMUMS) in out
    assert "did not provide the resources" not in out
    dests = {dest for dest, _source, _typecode in datas}
    assert "ai/faster_whisper/faster_whisper.dat" in dests
    assert "ai/cv2/cv2.dat" not in dests
    assert "ai/tokenizers/tokenizers.dat" not in dests


@pytest.mark.parametrize("package", list(AI_RESOURCE_MINIMUMS))
def test_spec_aborts_before_building_when_a_package_ships_none_of_its_resource(
    monkeypatch, workspace, package
):
    """Each of the seven is verified against its own category.

    Only the required category is emptied, so this fails a check that merely
    asked "did the package collect anything" -- the other two still yield a file.
    The abort has to land before ``Analysis``: collection ran to completion and
    no bundle was assembled.
    """
    kind = AI_RESOURCE_MINIMUMS[package]
    report: dict = {}
    with pytest.raises(SystemExit) as excinfo:
        _run_spec(
            monkeypatch,
            _spec_repo(workspace),
            empty_resources={package: (kind,)},
            report=report,
        )

    message = str(excinfo.value.code)
    gap_lines = [line.strip() for line in message.splitlines() if ": no " in line]
    assert gap_lines == [f"{package}: no {AI_RESOURCE_LABELS[kind]} ({kind}) collected"]
    assert "requirements-ai.txt" in message
    assert "--no-ai" in message
    # Collection finished for all seven; verification is what stopped the build.
    assert report["collected"] == list(AI_RESOURCE_MINIMUMS)
    assert report["analysis"] == 0
    assert report["datas"] is None


def test_spec_aborts_when_a_package_collects_nothing_at_all(monkeypatch, workspace):
    """The old "collected nothing" log line is now fatal instead of a note."""
    package = "rapidocr_onnxruntime"
    kind = AI_RESOURCE_MINIMUMS[package]
    report: dict = {}
    with pytest.raises(SystemExit) as excinfo:
        _run_spec(
            monkeypatch,
            _spec_repo(workspace),
            empty_resources={package: tuple(AI_RESOURCE_LABELS)},
            report=report,
        )

    gap_lines = [line.strip() for line in str(excinfo.value.code).splitlines() if ": no " in line]
    assert gap_lines == [f"{package}: no {AI_RESOURCE_LABELS[kind]} ({kind}) collected"]
    assert report["analysis"] == 0
    assert report["datas"] is None


def test_spec_reports_every_incomplete_package_in_one_abort(monkeypatch, workspace):
    """One build stops once, and names each broken package and its gap."""
    report: dict = {}
    with pytest.raises(SystemExit) as excinfo:
        _run_spec(
            monkeypatch,
            _spec_repo(workspace),
            empty_resources={"cv2": ("binaries",), "faster_whisper": ("datas",)},
            report=report,
        )

    gap_lines = [line.strip() for line in str(excinfo.value.code).splitlines() if ": no " in line]
    assert gap_lines == [
        "faster_whisper: no data files (datas) collected",
        "cv2: no native libraries (binaries) collected",
    ]
    assert report["analysis"] == 0


@pytest.mark.parametrize("package", list(AI_RESOURCE_MINIMUMS))
def test_resource_minimum_check_names_the_package_and_the_kind(monkeypatch, workspace, package):
    """The rule itself, called directly: no build, no message, just the gap.

    A message-only assertion cannot tell whether the spec checked ``av``'s
    binaries or its datas; this one pins the exact (package, kind) pair.
    """
    _datas, namespace, _report = _run_spec(
        monkeypatch, _spec_repo(workspace), with_ai=False, patch_find_spec=False
    )
    incomplete = namespace["incomplete_ai_packages"]
    full = {
        name: {kind: [f"{name}-{kind}"] for kind in AI_RESOURCE_LABELS}
        for name in AI_RESOURCE_MINIMUMS
    }
    assert incomplete(full) == []

    short = {name: dict(resources) for name, resources in full.items()}
    short[package][AI_RESOURCE_MINIMUMS[package]] = []
    assert incomplete(short) == [(package, AI_RESOURCE_MINIMUMS[package])]

    # A package that was never collected is the presence gate's business, not this.
    assert incomplete({package: full[package]}) == []


def test_spec_aborts_before_building_when_a_required_ai_package_is_missing(
    monkeypatch, workspace, capsys
):
    report: dict = {}
    with pytest.raises(SystemExit) as excinfo:
        _run_spec(monkeypatch, _spec_repo(workspace), absent_ai=("onnxruntime",), report=report)

    message = str(excinfo.value.code)
    assert "onnxruntime" in message
    assert "requirements-ai.txt" in message
    assert "--no-ai" in message
    # The build never started: no collection, no Analysis, no COLLECT.
    assert report["collected"] == []
    assert report["dynamic_libs"] == []
    assert report["analysis"] == 0
    assert report["datas"] is None
    assert "AI pack collected" not in capsys.readouterr().out

    # A SystemExit carrying a message is a non-zero exit status with that message
    # on stderr, which is how PyInstaller lets a spec file abort a build.
    probe = subprocess.run(
        [sys.executable, "-c", f"raise SystemExit({message!r})"],
        capture_output=True, text=True,
    )
    assert probe.returncode == 1
    assert "onnxruntime" in probe.stderr


def test_spec_skips_every_ai_check_when_the_pack_is_disabled(monkeypatch, workspace, capsys):
    datas, _namespace, report = _run_spec(
        monkeypatch, _spec_repo(workspace), with_ai=False, expect_no_probe=True
    )
    assert "AI pack disabled for this build" in capsys.readouterr().out
    assert report["probed"] == [] and report["collected"] == []
    # No AI native library either: the ctranslate2 call used to run outside the
    # switch, so --no-ai still shipped the dylib it was meant to leave behind.
    assert report["dynamic_libs"] == []
    assert report["binaries"] == []
    assert report["analysis"] == 1
    dests = {dest for dest, _source, _typecode in datas}
    assert not [dest for dest in dests if dest.startswith("ai/")]
    # The rest of the bundle is unaffected by the switch.
    assert "static/app.js" in dests
    assert "assets/NotoSansJP-VF.ttf" in dests


# ---------------------------------------------------------------------------
# Info.plist must not promise a macOS the bundle cannot load
#
# 0.4.7 shipped with ``LSMinimumSystemVersion`` hard-coded to 11.0 while 371 of
# its 550 Mach-O files needed 12.0 and the four ONNX Runtime objects needed 13.4.
# dyld refuses a library newer than the running system, so the old value did not
# widen support: it only let LaunchServices start an app that then failed to
# import its own core modules.
#
# The declared floor is the non-OCR dependency floor (12.0). ONNX Runtime's 13.4
# is reached only through ``phrasync/ocr.py``, whose import is lazy and whose
# failure degrades to Tesseract before raising ``OCRUnavailable``, so declaring
# 13.4 for the whole bundle would lock out systems that can run every feature
# except OCR. That 13.4 is still recorded -- as ``OCR_SYSTEM_VERSION`` and as the
# newest row of the measured table -- is what these tests keep honest.
# ---------------------------------------------------------------------------

MEASURED_TABLE = ROOT / "packaging" / "macos" / "README.md"


def _declared_minimum(report: dict) -> str:
    return report["info_plist"]["LSMinimumSystemVersion"]


def _measured_minos(table_path: Path) -> list[str]:
    """The ``minos`` column of the load-command table in the packaging README."""
    floors = []
    for line in table_path.read_text(encoding="utf-8").splitlines():
        # Rows look like "  | 13.4 | 4 | `onnxruntime/...` |"; the "<= 10.16"
        # row deliberately does not match, because a range is not a floor.
        match = re.match(r"\s*\|\s*(\d+\.\d+)\s*\|\s*\d+\s*\|", line)
        if match:
            floors.append(match.group(1))
    return floors


def _newest(floors: list[str]) -> str:
    return max(floors, key=lambda value: tuple(int(part) for part in value.split(".")))


def test_spec_declares_the_floor_of_the_shipped_bundle(monkeypatch, workspace):
    _datas, namespace, report = _run_spec(monkeypatch, _spec_repo(workspace))

    # 12.0 is what the bundle's non-OCR natives require; the 13.4 objects are
    # ONNX Runtime, reachable only through the lazily imported OCR module.
    assert _declared_minimum(report) == "12.0"
    assert _declared_minimum(report) != "11.0"
    # The AI switch must not move the declared floor in either direction.
    assert namespace["MIN_SYSTEM_VERSION_AI"] == "12.0"
    assert namespace["MIN_SYSTEM_VERSION_BASE"] == "12.0"


def test_spec_declares_the_lower_floor_when_the_ai_pack_is_off(monkeypatch, workspace):
    _datas, _namespace, report = _run_spec(
        monkeypatch, _spec_repo(workspace), with_ai=False, expect_no_probe=True
    )

    # Without ONNX Runtime the bundle carries nothing above 12.0, and claiming
    # 13.4 there would lock out systems that can run every feature it has.
    assert _declared_minimum(report) == "12.0"


def test_ocr_floor_is_the_newest_requirement_in_the_measured_table(monkeypatch, workspace):
    _datas, namespace, _report = _run_spec(monkeypatch, _spec_repo(workspace))

    measured = _measured_minos(MEASURED_TABLE)
    assert measured, f"no minos table found in {MEASURED_TABLE}"
    newest = _newest(measured)

    # 13.4 is ONNX Runtime's floor. It is no longer declared bundle-wide, so it
    # has to be pinned somewhere the build reads: OCR_SYSTEM_VERSION. If a future
    # onnxruntime bump raises the table, this fails until the constant follows.
    assert namespace["OCR_SYSTEM_VERSION"] == newest
    # Everything else in the bundle tops out at 12.0, which is what gets declared.
    assert namespace["MIN_SYSTEM_VERSION_AI"] == _newest(
        [value for value in measured if value != newest]
    )


def test_disabled_pack_tripwire_rejects_any_ai_collection(monkeypatch, workspace):
    """The --no-ai test above is only meaningful if the tripwire really fires.

    This simulates the regression that test exists to catch: a spec that reaches
    for an AI package or its native library despite the switch.
    """
    _run_spec(monkeypatch, _spec_repo(workspace), with_ai=False, expect_no_probe=True)
    hooks = sys.modules["PyInstaller.utils.hooks"]
    with pytest.raises(AssertionError, match="collect_dynamic_libs"):
        hooks.collect_dynamic_libs("ctranslate2")
    with pytest.raises(AssertionError, match="collected although the pack is disabled"):
        hooks.collect_all("ctranslate2")


def test_spec_presence_check_uses_real_import_resolution(monkeypatch, workspace):
    # No stub here: the helper must answer from the interpreter itself.
    _datas, namespace, _report = _run_spec(
        monkeypatch, _spec_repo(workspace), with_ai=False, patch_find_spec=False
    )
    missing_ai_packages = namespace["missing_ai_packages"]
    assert missing_ai_packages(["json", "pathlib"]) == []
    absent = "phrasync_ai_package_that_is_not_installed"
    assert missing_ai_packages(["json", absent]) == [absent]


# ---------------------------------------------------------------------------
# The wheel extractor must never write outside site-packages
#
# A wheel is an untrusted archive: member names come from whoever built it. The
# extractor used to join them straight onto site-packages, and ``Path.__truediv__``
# replaces the left side for an absolute name, so ``/x`` and ``../x`` both escaped.
# These tests pin the refusal for every shape of escape, and pin the ordinary
# extraction that has to keep working.
# ---------------------------------------------------------------------------


def load_install_wheels() -> types.ModuleType:
    """Load the extractor without importing it, so no __pycache__ lands in packaging/."""
    module = types.ModuleType("phrasync_install_wheels")
    module.__file__ = str(INSTALL_WHEELS)
    source = INSTALL_WHEELS.read_text(encoding="utf-8")
    exec(compile(source, str(INSTALL_WHEELS), "exec"), module.__dict__)
    return module


def make_wheel(path: Path, members: dict[str, bytes]) -> Path:
    """A zip with exactly these members; extraction needs no wheel metadata."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(zipfile.ZipInfo(name), payload)
    return path


def make_site(workspace: Path) -> Path:
    site = (workspace / "venv" / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")
    site.mkdir(parents=True)
    return site


def test_install_wheels_extracts_regular_members(workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    wheel = make_wheel(workspace / "demo-1.0-py3-none-any.whl", {
        "demo/__init__.py": b"VERSION = 1\n",
        "demo/core/mod.py": b"import os\n",
        "./demo/dotted.py": b"x = 1\n",
        "demo-1.0.data/purelib/demo/extra.py": b"y = 2\n",
        "demo-1.0.data/scripts/demo-cli": b"#!/bin/sh\n",
    })

    written = module.install(wheel, site)

    assert written == 4
    assert (site / "demo" / "__init__.py").read_bytes() == b"VERSION = 1\n"
    assert (site / "demo" / "core" / "mod.py").read_bytes() == b"import os\n"
    # A leading "./" is normal in older wheels and must still land correctly.
    assert (site / "demo" / "dotted.py").read_bytes() == b"x = 1\n"
    # .data/purelib is remapped onto site-packages; .data/scripts is not importable.
    assert (site / "demo" / "extra.py").read_bytes() == b"y = 2\n"
    assert not (site / "demo-cli").exists()


def test_install_wheels_refuses_parent_traversal(workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    wheel = make_wheel(workspace / "evil-1.0-py3-none-any.whl", {"../escaped.py": b"pwned\n"})

    with pytest.raises(module.UnsafeWheelMember) as excinfo:
        module.install(wheel, site)

    message = str(excinfo.value)
    assert "evil-1.0-py3-none-any.whl" in message
    assert "../escaped.py" in message
    assert not (workspace / "venv" / "lib" / "escaped.py").exists()
    assert not (site.parent.parent / "escaped.py").exists()
    # Nothing was written at all: the archive is refused before its first file.
    assert list(site.rglob("*")) == []


def test_install_wheels_refuses_absolute_member(workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    outside = workspace / "absolute-target.py"
    wheel = make_wheel(workspace / "evil-1.0-py3-none-any.whl", {str(outside): b"pwned\n"})

    with pytest.raises(module.UnsafeWheelMember) as excinfo:
        module.install(wheel, site)

    # The name of the temp file below also contains "absolute", so match the
    # diagnosis rather than the substring: otherwise removing the check passes.
    assert "absolute member path" in str(excinfo.value)
    assert not outside.exists()


@pytest.mark.skipif(os.name == "nt", reason="creating a symlink needs a privilege on Windows")
def test_install_wheels_refuses_members_that_leave_through_a_symlink(workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    outside = workspace / "elsewhere"
    outside.mkdir()
    # A name can look perfectly relative and still resolve outside if a directory
    # inside site-packages is a symlink. Only the resolved-path check catches that.
    (site / "shared").symlink_to(outside, target_is_directory=True)
    wheel = make_wheel(workspace / "evil-1.0-py3-none-any.whl", {"shared/escaped.py": b"pwned\n"})

    with pytest.raises(module.UnsafeWheelMember) as excinfo:
        module.install(wheel, site)

    assert "outside" in str(excinfo.value)
    assert not (outside / "escaped.py").exists()


def test_install_wheels_refuses_nested_traversal(workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    wheel = make_wheel(workspace / "evil-1.0-py3-none-any.whl", {"pkg/../../escaped.py": b"pwned\n"})

    with pytest.raises(module.UnsafeWheelMember) as excinfo:
        module.install(wheel, site)

    assert "escapes the target directory" in str(excinfo.value)
    assert not (workspace / "venv" / "lib" / "escaped.py").exists()


def test_install_wheels_refuses_traversal_hidden_in_a_data_dir(workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    # The .data/purelib prefix is stripped before the join, so the walk upwards
    # starts from site-packages, not from the archive root.
    member = "demo-1.0.data/purelib/../../../escaped.py"
    wheel = make_wheel(workspace / "evil-1.0-py3-none-any.whl", {member: b"pwned\n"})

    with pytest.raises(module.UnsafeWheelMember) as excinfo:
        module.install(wheel, site)

    assert "escapes the target directory" in str(excinfo.value)
    assert not (workspace / "venv" / "escaped.py").exists()


@pytest.mark.parametrize("name", [
    "../x.py",
    "/x.py",
    "a/../../x.py",
    "a\\..\\x.py",
    "nul\x00byte.py",
])
def test_install_wheels_safe_relative_refuses_unsafe_names(name):
    module = load_install_wheels()
    with pytest.raises(module.UnsafeWheelMember):
        module.safe_relative(name)


@pytest.mark.parametrize(("name", "expected"), [
    ("./a/b.py", "a/b.py"),
    ("a//b.py", "a/b.py"),
    ("a/./b.py", "a/b.py"),
    ("", None),
    (".", None),
])
def test_install_wheels_safe_relative_keeps_ordinary_names(name, expected):
    module = load_install_wheels()
    assert module.safe_relative(name) == expected


def test_install_wheels_main_stops_and_reports_the_unsafe_archive(monkeypatch, workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    wheels = workspace / "wheels"
    wheels.mkdir()
    make_wheel(wheels / "aaa-good-1.0-py3-none-any.whl", {"good/__init__.py": b"ok\n"})
    make_wheel(wheels / "zzz-evil-1.0-py3-none-any.whl", {"../../../escaped.py": b"pwned\n"})
    monkeypatch.setattr(sys, "argv", ["install_wheels.py", str(wheels), str(site.parents[2])])

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main()

    assert code == 3
    assert "zzz-evil-1.0-py3-none-any.whl" in err.getvalue()
    assert "escaped.py" in err.getvalue()
    assert not (workspace / "escaped.py").exists()
    assert not (site.parent / "escaped.py").exists()
    # The safe wheel sorted before the hostile one was extracted, then the run stopped.
    assert (site / "good" / "__init__.py").exists()
    assert "extracted" not in out.getvalue()


def test_install_wheels_main_extracts_a_clean_set(monkeypatch, workspace):
    module = load_install_wheels()
    site = make_site(workspace)
    wheels = workspace / "wheels"
    wheels.mkdir()
    make_wheel(wheels / "demo-1.0-py3-none-any.whl", {"demo/__init__.py": b"ok\n"})
    monkeypatch.setattr(sys, "argv", ["install_wheels.py", str(wheels), str(site.parents[2])])

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main()

    assert code == 0
    assert err.getvalue() == ""
    assert (site / "demo" / "__init__.py").read_bytes() == b"ok\n"
    assert "demo-1.0-py3-none-any.whl: 1 files" in out.getvalue()

