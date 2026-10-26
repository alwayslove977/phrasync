# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the standalone macOS Phrasync.app bundle.

Build with ``packaging/macos/build_app.sh``. The result is a one-folder bundle
inside ``Phrasync.app/Contents/Frameworks`` (PyInstaller's onedir layout), which
starts far faster than a one-file bundle and keeps every resource inspectable.

Notes:
* ``static/`` and ``assets/`` reach the bundle through ``bundle_manifest``, which
  admits one reviewed file at a time; ``phrasync.config.resource_root()``
  resolves them through ``sys._MEIPASS`` so the app never depends on the source
  checkout.
* ``imageio_ffmpeg`` ships the FFmpeg executable used for MP4 encoding, so the
  bundle carries its own encoder instead of assuming Homebrew is installed.
"""

import importlib.util
import os
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parent.parent  # ~/phrasync
BUILD_DIR = ROOT / "build" / "macos"

# The allowlist lives beside this file so the pre-build gate and the packaging
# agree on one definition. Importing it by path (rather than relying on the
# working directory) keeps the spec runnable from anywhere.
sys.path.insert(0, str(ROOT / "packaging" / "macos"))
import bundle_manifest  # noqa: E402

with (ROOT / "pyproject.toml").open("rb") as handle:
    APP_VERSION = tomllib.load(handle)["project"]["version"]
APP_NAME = "Phrasync"
BUNDLE_ID = "com.phrasync.desktop"

# The floor this bundle declares is measured from the Mach-O load commands of the
# 0.4.7 app (table in packaging/macos/README.md): 371 files require 12.0 (``av``,
# numpy and most extension modules) and four ONNX Runtime objects require 13.4.
# dyld refuses to load a library whose minimum is newer than the running system,
# so a system below 12.0 cannot import the core modules at all -- which is what
# the old, unconditional 11.0 value pretended it could.
#
# 13.4 belongs to ONNX Runtime alone, and the only code that imports it is
# ``phrasync/ocr.py``: the import is lazy, wrapped in ``except Exception``, and
# falls back to Tesseract before raising ``OCRUnavailable``. Declaring 13.4 for
# the whole bundle therefore costs every 12.0-13.3 machine an app that would run
# fine apart from OCR. The declared floor stays at the non-OCR dependency floor
# and OCR is documented -- and reported through ``/api/health`` -- as unavailable
# below ``OCR_SYSTEM_VERSION`` instead.
#
# 12.0 is inferred from those load commands, not from a launch test on a 12.x
# machine. Re-measure all three values when numpy/``av``/onnxruntime move.
MIN_SYSTEM_VERSION_BASE = "12.0"
MIN_SYSTEM_VERSION_AI = "12.0"
OCR_SYSTEM_VERSION = "13.4"

ICON = BUILD_DIR / "Phrasync.icns"

# The bundle receives exactly the files ``bundle_manifest`` admits -- one entry
# per file, never a directory. A directory entry lets PyInstaller copy whatever
# happens to sit in ``static/`` or ``assets/``: an editor backup, a screenshot, a
# user video dropped there while testing. ``.gitignore`` does not apply to it.
manifest_datas, held_out, refused = bundle_manifest.collect(ROOT)
if refused:
    raise SystemExit(
        "ERROR: build inputs contain files outside the reviewed allowlist:\n"
        + "\n".join(f"       {path}  ({reason})" for path, reason in refused)
        + "\n       Move them out of static/ or assets/, or teach\n"
          "       packaging/macos/bundle_manifest.py about the new file. Nothing\n"
          "       unlisted is ever packaged."
    )
datas = list(manifest_datas)
print(f"bundle inputs: {len(datas)} reviewed file(s) admitted, {len(held_out)} held out")
for path, reason in held_out:
    print(f"  held out  {path}  ({reason})")

datas += [
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
# FFmpeg binary + the JavaScript bridge pywebview injects into the page.
datas += collect_data_files("imageio_ffmpeg")
datas += collect_data_files("webview")


def is_debris_data(dest):
    """True for Finder metadata and editor backups inside a package's data files.

    Third-party collections are walked by PyInstaller, so a stray ``.DS_Store``
    or a maintainer's ``.bak`` can ride along. Media and database payloads are
    *not* dropped here: if a package legitimately ships one, silently deleting it
    would break the app, so those are refused loudly by the check below instead.
    """
    return bundle_manifest.is_denied_name(Path(dest).name)


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


AI_ENABLED = os.environ.get("PHRASYNC_BUILD_AI", "1") == "1"

# Both builds declare 12.0 today; the switch is kept explicit so a future change
# to one side cannot silently move the other.
MIN_SYSTEM_VERSION = MIN_SYSTEM_VERSION_AI if AI_ENABLED else MIN_SYSTEM_VERSION_BASE

binaries = []
if AI_ENABLED:
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
a.datas = [entry for entry in a.datas if not is_debris_data(entry[0])]
print(f"data files held out of the bundle: {_collected - len(a.datas)}")

# A media or database payload contributed by a wheel would ship inside the app.
# Refuse it before COLLECT rather than discovering it in the 800 MB bundle.
# PEM containers are judged by their bytes: certifi's public CA bundle must pass,
# a private key must not.
_payload = []
for _dest, _source, _kind in a.datas:
    _suffix = Path(_dest).suffix.lower()
    if _suffix in bundle_manifest.DENY_SUFFIXES:
        _payload.append(_dest)
    elif _suffix in bundle_manifest.PEM_SUFFIXES and bundle_manifest.carries_private_key(_source):
        _payload.append(_dest + "  (private key)")
if _payload:
    raise SystemExit(
        "ERROR: collected data files include media, database or credential payloads:\n"
        + "\n".join(f"       {name}" for name in _payload[:20])
        + "\n       Identify the package that ships them before building again."
    )

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
        "LSMinimumSystemVersion": MIN_SYSTEM_VERSION,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "Apache-2.0",
        "LSEnvironment": {"PYTHONUTF8": "1"},
    },
)
