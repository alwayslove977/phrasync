# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the standalone macOS Phrasync.app bundle.

Build with ``packaging/macos/build_app.sh``. The result is a one-folder bundle
inside ``Phrasync.app/Contents/Frameworks`` (PyInstaller's onedir layout), which
starts far faster than a one-file bundle and keeps every resource inspectable.

Notes:
* ``static/`` and ``assets/`` are collected next to the frozen ``phrasync``
  package; ``phrasync.config.resource_root()`` resolves them through
  ``sys._MEIPASS`` so the app never depends on the source checkout.
* ``imageio_ffmpeg`` ships the FFmpeg executable used for MP4 encoding, so the
  bundle carries its own encoder instead of assuming Homebrew is installed.
"""

import importlib.util
import os
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parent.parent  # ~/phrasync
BUILD_DIR = ROOT / "build" / "macos"

with (ROOT / "pyproject.toml").open("rb") as handle:
    APP_VERSION = tomllib.load(handle)["project"]["version"]
APP_NAME = "Phrasync"
BUNDLE_ID = "com.phrasync.desktop"

ICON = BUILD_DIR / "Phrasync.icns"

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
# FFmpeg binary + the JavaScript bridge pywebview injects into the page.
datas += collect_data_files("imageio_ffmpeg")
datas += collect_data_files("webview")

# PyInstaller has no exclusion option for datas: a directory entry is walked and
# every file below it is copied, so .gitignore has no say over the bundle. These
# editor backups sit next to the runtime files and would ship inside static/.
# Named one by one so a future rewrite of app.js can never take a real file with
# it; anything not listed here is still collected.
EXCLUDED_DATA = {
    "static/app.js.bak",
    "static/app-ui.js.bak",
    "static/app.js.font-backup",
    "static/i18n.js.before_source_tracking.bak",
}


def is_excluded_data(dest):
    """True for a collected path that must stay out of the bundle.

    ``dest`` is the target path inside the bundle, e.g. ``static/app.js.bak``.
    Finder metadata carries nothing the app reads, so every .DS_Store goes too --
    ``assets/.DS_Store`` is the one that would otherwise be copied.
    """
    return dest.replace(os.sep, "/") in EXCLUDED_DATA or Path(dest).name == ".DS_Store"


hiddenimports = [
    # uvicorn resolves its loop, HTTP and WebSocket implementations by name.
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # pywebview's macOS backend is selected at runtime by name.
    "webview.platforms.cocoa",
]
hiddenimports += collect_submodules("phrasync")

# ---------------------------------------------------------------- AI pack
# faster-whisper ships a Silero VAD model, CTranslate2 ships its native library,
# ONNX Runtime ships its execution providers, and RapidOCR ships its detection
# and recognition models. None of them are found by static analysis alone.
# All seven are required whenever PHRASYNC_BUILD_AI is 1, because that single
# switch is what requirements-ai.txt installs: transcription needs
# faster_whisper plus its ctranslate2/av/tokenizers chain, OCR needs
# rapidocr_onnxruntime plus onnxruntime and cv2.
AI_PACKAGES = ["faster_whisper", "ctranslate2", "onnxruntime", "rapidocr_onnxruntime", "cv2", "av", "tokenizers"]

# Importable is not the same as shipping its payload. A wheel that unpacks
# without its models or native libraries imports fine and then dies on the
# user's first transcription or OCR, which is exactly the hollow-bundle failure
# the rest of this file exists to prevent. Each package therefore owes the
# bundle at least one of the resource only it can supply; nothing else is
# required. The categories left out are correct rather than broken --
# faster_whisper has no native library of its own and cv2 has no data files --
# so only the kind named here is inspected.
# ``collect_all`` is collect_data_files + collect_dynamic_libs +
# collect_submodules, so the binaries counted below already include the dynamic
# libraries collected explicitly further down.
AI_RESOURCE_MINIMUMS = {
    "faster_whisper": "datas",        # Silero VAD model
    "ctranslate2": "binaries",        # libctranslate2
    "onnxruntime": "binaries",        # execution providers
    "rapidocr_onnxruntime": "datas",  # detection + recognition models
    "cv2": "binaries",                # OpenCV native modules
    "av": "binaries",                 # bundled FFmpeg libraries
    "tokenizers": "hiddenimports",    # tokenizers.abi3.so escapes PY_DYLIB_PATTERNS
}

# Category names as they appear in a build log, so the failure names what the
# package should have shipped instead of an internal list name.
AI_RESOURCE_LABELS = {
    "datas": "data files",
    "binaries": "native libraries",
    "hiddenimports": "hidden imports",
}


def incomplete_ai_packages(collected_resources):
    """``[(package, kind)]`` for packages that fell short of their minimum.

    *collected_resources* maps a package name to the triple ``collect_all()``
    returned, keyed by ``datas``/``binaries``/``hiddenimports``. Only the kind
    listed in ``AI_RESOURCE_MINIMUMS`` is inspected, so a package may legitimately
    contribute nothing to the other two. Kept as a pure function beside the
    collection loop so the rule can be checked without running PyInstaller.
    """
    gaps = []
    for package, minimum in AI_RESOURCE_MINIMUMS.items():
        resources = collected_resources.get(package)
        if resources is None:
            continue
        if not resources[minimum]:
            gaps.append((package, minimum))
    return gaps


def missing_ai_packages(packages):
    """Names in *packages* that the build interpreter cannot import.

    ``collect_all()`` is not a presence check. Measured against PyInstaller
    6.22.3, a package that is not installed produces three empty lists plus a
    couple of log warnings -- it never raises, so an ``except`` around it never
    fires. The success line below used to list all seven names whether or not a
    single one had been collected. Import resolution answers the same question
    the frozen app asks at runtime, and ``find_spec`` only locates the package
    instead of importing it.
    """
    absent = []
    for package in packages:
        try:
            found = importlib.util.find_spec(package) is not None
        except (ImportError, ValueError):  # unresolvable, e.g. broken parent
            found = False
        if not found:
            absent.append(package)
    return absent


binaries = []
if os.environ.get("PHRASYNC_BUILD_AI", "1") == "1":
    absent = missing_ai_packages(AI_PACKAGES)
    if absent:
        raise SystemExit(
            "ERROR: the AI pack is enabled but these packages are not importable "
            f"in the build interpreter: {', '.join(absent)}\n"
            f"       install them with: pip install -r {ROOT / 'requirements-ai.txt'}\n"
            "       or leave the pack out on purpose with --no-ai"
        )
    # ``collect_all('ctranslate2')`` below already returns these, but the explicit
    # call stays so the dylib lands even if that loop is ever reordered. It lives
    # inside the switch now: with --no-ai this spec must not collect a single AI
    # native library, and the old unconditional call did.
    binaries += collect_dynamic_libs("ctranslate2")
    collected = []
    resources = {}
    for package in AI_PACKAGES:
        try:
            package_datas, package_binaries, package_hidden = collect_all(package)
        except Exception as exc:  # collecting a present package broke
            raise SystemExit(f"ERROR: collecting the AI package {package!r} failed: {exc}") from exc
        resources[package] = {
            "datas": package_datas,
            "binaries": package_binaries,
            "hiddenimports": package_hidden,
        }
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden
        collected.append(package)
    # Every package was importable, but that says nothing about what it carried.
    # Fail here, before Analysis, so a broken install costs seconds instead of a
    # full build that only breaks on the user's first export.
    gaps = incomplete_ai_packages(resources)
    if gaps:
        lines = [
            "ERROR: the AI pack is enabled but these packages did not provide the "
            "resources the bundle needs:"
        ]
        for package, kind in gaps:
            lines.append(f"       {package}: no {AI_RESOURCE_LABELS[kind]} ({kind}) collected")
        lines.append(
            "       reinstall them with: pip install --force-reinstall "
            f"-r {ROOT / 'requirements-ai.txt'}"
        )
        lines.append("       or leave the pack out on purpose with --no-ai")
        raise SystemExit("\n".join(lines))
    # Only printed when the whole pack actually arrived.
    if collected:
        print("AI pack collected:", ", ".join(collected))
else:
    print("AI pack disabled for this build")

excludes = [
    "tkinter",
    "pytest",
    "_pytest",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "gi",
    "winrt",
]

a = Analysis(
    [str(ROOT / "packaging" / "macos" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
# ``a.datas`` is a plain list of (dest, source, typecode) entries and COLLECT
# takes any TOC-like iterable, so dropping entries here is all it takes to keep
# them out of the bundle. Filtering after Analysis also covers the files that
# enter through the imageio_ffmpeg/webview/AI collections.
_collected = len(a.datas)
a.datas = [entry for entry in a.datas if not is_excluded_data(entry[0])]
print(f"data files held out of the bundle: {_collected - len(a.datas)}")

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ICON) if ICON.exists() else None,
    bundle_identifier=BUNDLE_ID,
    version=APP_VERSION,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": APP_NAME,
        "CFBundleIconFile": ICON.name if ICON.exists() else "",
        "LSApplicationCategoryType": "public.app-category.video",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "Apache-2.0",
        "LSEnvironment": {"PYTHONUTF8": "1"},
    },
)
