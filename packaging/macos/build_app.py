#!/usr/bin/env python3
"""Python build driver for the standalone macOS bundle.

``build_app.sh`` is the canonical entry point. This driver performs the same
steps without relying on shell built-ins, which matters on machines where the
shell's temporary files are restricted (some managed macOS setups deny writes to
/var/tmp). Both paths produce an identical ``dist/Phrasync.app``.

    python3 packaging/macos/build_app.py            # core + AI pack + browser
    python3 packaging/macos/build_app.py --no-ai    # core only
    python3 packaging/macos/build_app.py --fast     # reuse the build venv
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_DIR = ROOT / "build" / "macos"
LOG_DIR = BUILD_DIR / "logs"
DIST = ROOT / "dist"
APP = DIST / "Phrasync.app"
SPEC = ROOT / "packaging" / "macos" / "Phrasync.spec"
VENV = Path(os.environ.get("PHRASYNC_BUILD_VENV", ROOT / ".venv-build-ai")).expanduser()

# PyInstaller cannot cross-compile, so the bundle architecture is always the
# build host's architecture. Kept in one place so the layout checks below point
# at the runtime that was actually collected.
ARCH = "arm64" if platform.machine() == "arm64" else "x64"


def build_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # a stray shim must never leak into the build
    temp = BUILD_DIR / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(temp)
    env["PYTHONUTF8"] = "1"
    return env


def run(command: list[str], env: dict[str, str]) -> None:
    print("--", " ".join(str(item) for item in command))
    result = subprocess.run([str(item) for item in command], env=env, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"step failed with {result.returncode}: {command[0]}")


def ensure_venv(env: dict[str, str]) -> Path:
    python = VENV / "bin" / "python"
    if not python.exists():
        base = os.environ.get("PHRASYNC_BUILD_PYTHON") or sys.executable
        print("-- creating build venv with", base)
        run([base, "-m", "venv", str(VENV)], env)
    return python


def pip_install(python: Path, specs: list[str], env: dict[str, str]) -> None:
    """Install packages, falling back to pure wheel extraction.

    Some managed macOS accounts refuse the unlink step pip performs when it
    replaces files, which aborts the install halfway. Downloading the wheels and
    extracting them writes the same files without any delete step, so the build
    still produces a complete environment.

    ``--no-compile`` keeps pip from rewriting __pycache__ entries for the same
    reason; the bytecode is not needed, Python compiles on first import.
    """
    print("--", python, "-m pip install", " ".join(specs))
    result = subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--no-compile", *specs],
                            env=env, cwd=ROOT)
    if result.returncode == 0:
        return
    print("-- pip install was refused, extracting wheels directly")
    # A directory per requirement set: reusing one pool mixes wheel versions and
    # the last extraction wins, which is how a downgrade can silently undo itself.
    slug = "_".join(item.replace("/", "-").replace(".", "")[-16:] for item in specs if not item.startswith("-"))
    wheels = BUILD_DIR / f"wheels-{slug or 'pkgs'}"
    run([python, "-m", "pip", "download", "--only-binary=:all:", "--no-cache-dir",
         "-d", str(wheels), *specs], env)
    run([python, str(ROOT / "packaging/macos/install_wheels.py"), str(wheels), str(VENV)], env)


def export_browser_source() -> Path:
    """The export browser this build is expected to collect, resolved from the source tree.

    ``ARCH`` is the single architecture token the rest of this driver already
    uses, and ``required_layout()`` checks the collected copy at the same
    relative path, so the pre-build check and the post-build check always name
    the same runtime.
    """
    return ROOT / "assets" / "browser" / f"chrome-headless-shell-mac-{ARCH}" / "chrome-headless-shell"


def check_export_browser() -> list[str]:
    """Reasons the export browser cannot be collected, or an empty list.

    PyInstaller copies whatever ``assets/`` holds, so a missing binary would only
    be noticed after a full build -- and a non-executable one not even then:
    the bundler restores the executable bit only when the source has it, and the
    app checks nothing but ``is_file()`` before spawning the browser, so the
    failure would land on the first MP4 export inside the installed app.
    """
    browser = export_browser_source()
    if not browser.is_file():
        root = browser.parent.parent
        names = sorted(item.name for item in root.glob("*")) if root.is_dir() else []
        return [
            f"the bundled export browser for {ARCH} is missing:",
            str(browser),
            f"present: {', '.join(names) or 'nothing'}",
            f"On {ARCH} run: playwright install chromium-headless-shell",
            f"then copy chrome-headless-shell-mac-{ARCH} into assets/browser/.",
        ]
    if not os.access(browser, os.X_OK):
        return [
            "the bundled export browser is not executable:",
            str(browser),
            "the bundle would carry it without the executable bit, because only a",
            "source file that is already executable is chmodded on collection;",
            "the app would then fail at the first export instead of here.",
            f"chmod +x {browser}",
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="reuse the build venv, skip --clean")
    parser.add_argument("--no-ai", action="store_true", help="skip faster-whisper and RapidOCR")
    args = parser.parse_args()

    # Checked before anything is created or installed: PyInstaller would build a
    # complete-looking bundle around a missing browser, and a non-executable one
    # would survive the layout check too. Failing here costs a second instead of
    # a full build plus a broken export on the user's machine.
    problems = check_export_browser()
    if problems:
        print(file=sys.stderr)
        print(f"!! {problems[0]}", file=sys.stderr)
        for line in problems[1:]:
            print(f"   {line}", file=sys.stderr)
        return 1

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = build_environment()
    python = ensure_venv(env)

    started = time.time()
    print(f"-- arch: {os.uname().machine} | build python: {python}")

    # --no-compile keeps pip from rewriting __pycache__ entries inside the venv.
    # On managed macOS accounts those renames trip file policies, and the
    # bytecode is not needed: Python compiles on first import and PyInstaller
    # goes through the sources.
    if not args.fast:
        pip_install(python, ["--upgrade", "pip", "wheel"], env)
    pip_install(python, ["-r", str(ROOT / "requirements.txt")], env)
    with_ai = 0 if args.no_ai else 1
    if with_ai:
        print("-- installing optional AI pack")
        pip_install(python, ["-r", str(ROOT / "requirements-ai.txt")], env)
    pip_install(python, ["pyinstaller>=6,<7"], env)

    run([python, str(ROOT / "packaging/macos/make_icns.py"),
         str(ROOT / "assets/Phrasync.png"), str(BUILD_DIR / "Phrasync.icns")], env)

    env["PHRASYNC_BUILD_AI"] = str(with_ai)
    pyinstaller = [python, "-m", "PyInstaller", "--noconfirm",
                   "--distpath", str(DIST), "--workpath", str(BUILD_DIR / "pyinstaller")]
    if not args.fast:
        pyinstaller.append("--clean")
    run(pyinstaller + [str(SPEC)], env)

    if not APP.is_dir():
        print(f"!! build finished without {APP}", file=sys.stderr)
        return 1

    print("")
    print(f"-- bundle: {APP}")
    print(f"   total: {du(APP)}")
    missing = verify_bundle_layout(APP)
    print(f"   elapsed: {time.time() - started:.0f}s")
    if missing:
        print("", file=sys.stderr)
        print(f"!! the bundle is incomplete: {len(missing)} required path(s) missing", file=sys.stderr)
        for item in missing:
            print(f"   {item}", file=sys.stderr)
        print("   The app would install but fail on export or transcription; rebuild once the"
              " missing assets are in place.", file=sys.stderr)
        return 1
    return 0


def required_layout() -> list[str]:
    """Paths every bundle must contain, relative to ``Phrasync.app``.

    Each one backs a feature that only fails at runtime — export shells out to
    the bundled browser, transcription needs the model, the UI needs the static
    tree — so their absence has to fail the build instead of being reported as a
    successful one.
    """
    return [
        "Contents/Info.plist",
        "Contents/MacOS/Phrasync",
        "Contents/Frameworks/static/index.html",
        "Contents/Frameworks/static/app.js",
        "Contents/Frameworks/assets/NotoSansJP-VF.ttf",
        f"Contents/Frameworks/assets/browser/chrome-headless-shell-mac-{ARCH}/chrome-headless-shell",
        "Contents/Frameworks/assets/models/whisper-tiny/model.bin",
    ]


def required_globs() -> list[str]:
    """Required paths whose name is only known at pattern level, relative to ``Phrasync.app``.

    ``imageio_ffmpeg`` names its binary after the platform, architecture and
    FFmpeg release (``ffmpeg-macos-x86_64-v7.1`` today, something else after an
    upgrade or on another host), so neither the version nor the architecture can
    be pinned here. The directory is what the app resolves at runtime, and the
    ``ffmpeg-*`` entry inside it is the encoder every MP4 export shells out to.
    """
    return ["Contents/Frameworks/imageio_ffmpeg/binaries/ffmpeg-*"]


def verify_bundle_layout(app: Path) -> list[str]:
    """Print the layout report for *app* and return the required paths that are absent."""
    missing: list[str] = []
    for item in required_layout():
        # is_file(), not exists(): a directory parked on one of these paths (say
        # static/app.js/) says nothing about the script being there, and the
        # shell driver has always required a regular file. One entry point that
        # is a directory costs the whole window, so the stricter check is right.
        present = (app / item).is_file()
        print(f"   {'ok' if present else 'MISSING'}: {item}")
        if not present:
            missing.append(item)
    # Patterns are matched with glob(): passing an asterisk to Path.exists() would
    # compare it literally and report a present binary as missing.
    for pattern in required_globs():
        present = any(app.glob(pattern))
        print(f"   {'ok' if present else 'MISSING'}: {pattern}")
        if not present:
            missing.append(pattern)
    return missing


def du(path: Path) -> str:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return f"{total / 1e6:.0f} MB"


if __name__ == "__main__":
    sys.exit(main())
