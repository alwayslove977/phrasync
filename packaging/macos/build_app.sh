#!/usr/bin/env bash
# Build a standalone macOS Phrasync.app bundle.
#
#   packaging/macos/build_app.sh              # full build into ./dist
#   packaging/macos/build_app.sh --fast       # reuse the build venv, skip --clean
#
# Environment overrides:
#   PHRASYNC_BUILD_VENV     build virtualenv path (default: <repo>/.venv-build)
#   PHRASYNC_BUILD_PYTHON   interpreter used to create that venv
#
# All output is tee'd to build/macos/logs/build-<timestamp>.log.
set -euo pipefail

# Never inherit a caller's PYTHONPATH: it can inject shims into the build.
unset PYTHONPATH

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$ROOT/build/macos"
LOG_DIR="$BUILD_DIR/logs"
VENV="${PHRASYNC_BUILD_VENV:-$ROOT/.venv-build}"
SPEC="$ROOT/packaging/macos/Phrasync.spec"
DIST="$ROOT/dist"
APP="$DIST/Phrasync.app"
FAST=0
WITH_AI=${PHRASYNC_WITH_AI:-1}

# PyInstaller cannot cross-compile: the bootloader and every native extension
# come from the build interpreter, so an arm64 bundle can only be produced on an
# arm64 Mac. Refuse a mismatched request instead of shipping an x86_64 app that
# claims to be Apple Silicon native.
HOST_ARCH="$(uname -m)"
TARGET_ARCH="${PHRASYNC_TARGET_ARCH:-$HOST_ARCH}"
if [[ "$TARGET_ARCH" != "$HOST_ARCH" ]]; then
  echo "!! PyInstaller cannot build $TARGET_ARCH on a $HOST_ARCH host." >&2
  echo "   Build on an Apple Silicon Mac (or an arm64 CI runner) instead." >&2
  exit 2
fi
BROWSER_ARCH=$([[ "$TARGET_ARCH" == "arm64" ]] && echo arm64 || echo x64)

for argument in "$@"; do
  case "$argument" in
    --fast) FAST=1 ;;
    --with-ai) WITH_AI=1 ;;
    --no-ai) WITH_AI=0 ;;
    *) echo "unknown argument: $argument" >&2; exit 2 ;;
  esac
done

mkdir -p "$BUILD_DIR" "$LOG_DIR"
LOG_FILE="$LOG_DIR/build-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "== Phrasync macOS build =="
echo "repo:     $ROOT"
echo "log:      $LOG_FILE"
echo "arch:     $TARGET_ARCH on $HOST_ARCH / macOS $(sw_vers -productVersion)"
echo ""

# ---------------------------------------------------------------- export browser
BROWSER_DIR="$ROOT/assets/browser/chrome-headless-shell-mac-$BROWSER_ARCH"
if [[ ! -x "$BROWSER_DIR/chrome-headless-shell" ]]; then
  echo "!! the bundled export browser for $TARGET_ARCH is missing:" >&2
  echo "   $BROWSER_DIR/chrome-headless-shell" >&2
  echo "   present: $(ls "$ROOT/assets/browser" | tr '\n' ' ')" >&2
  echo "   On $TARGET_ARCH run: playwright install chromium-headless-shell" >&2
  echo "   then copy chrome-headless-shell-mac-$BROWSER_ARCH into assets/browser/." >&2
  exit 1
fi
echo "-- export browser: $BROWSER_DIR"

# ---------------------------------------------------------------- interpreter
if [[ ! -x "$VENV/bin/python" ]]; then
  PYTHON="${PHRASYNC_BUILD_PYTHON:-}"
  if [[ -z "$PYTHON" ]]; then
    if [[ -x "$ROOT/.venv/bin/python" ]]; then
      PYTHON="$ROOT/.venv/bin/python"
    else
      PYTHON="$(command -v python3)"
    fi
  fi
  echo "-- creating build venv with $PYTHON"
  "$PYTHON" -m venv "$VENV"
fi
PY="$VENV/bin/python"
echo "-- build python: $("$PY" -V) at $PY"

# ---------------------------------------------------------------- dependencies
if [[ $FAST -eq 0 ]]; then
  "$PY" -m pip install --quiet --upgrade pip wheel
fi
echo "-- installing runtime requirements"
"$PY" -m pip install --quiet -r "$ROOT/requirements.txt"
if [[ $WITH_AI -eq 1 ]]; then
  echo "-- installing optional AI pack (faster-whisper + RapidOCR)"
  if ! "$PY" -m pip install --quiet -r "$ROOT/requirements-ai.txt"; then
    echo "!! the AI pack could not be installed; the bundle will not transcribe or OCR offline" >&2
    exit 1
  fi
fi
echo "-- installing pyinstaller"
"$PY" -m pip install --quiet "pyinstaller>=6,<7"

# ---------------------------------------------------------------- icon
echo "-- generating .icns"
"$PY" "$ROOT/packaging/macos/make_icns.py" "$ROOT/assets/Phrasync.png" "$BUILD_DIR/Phrasync.icns"

# ---------------------------------------------------------------- bundle
PYINSTALLER_ARGS=(--noconfirm --distpath "$DIST" --workpath "$BUILD_DIR/pyinstaller")
if [[ $FAST -eq 0 ]]; then
  PYINSTALLER_ARGS+=(--clean)
fi
echo "-- running pyinstaller"
export PHRASYNC_BUILD_AI="$WITH_AI"
"$PY" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$SPEC"

if [[ ! -d "$APP" ]]; then
  echo "!! build finished without $APP" >&2
  exit 1
fi

# ---------------------------------------------------------------- verification
echo ""
echo "-- bundle layout"
du -sh "$APP"
echo "   executable: $APP/Contents/MacOS/Phrasync"
echo "   frameworks: $(du -sh "$APP/Contents/Frameworks" | cut -f1)"

# A bundle missing any of these still installs and starts, then fails on export
# or transcription, so the build has to report the failure rather than succeed
# with a hollow .app. Kept as a counter plus a text list: bash 3.2 (the macOS
# default) treats an empty array as unbound under `set -u`.
MISSING_COUNT=0
MISSING_DETAIL=""
record_missing() {
  MISSING_COUNT=$((MISSING_COUNT + 1))
  MISSING_DETAIL="${MISSING_DETAIL}   $1"$'\n'
  echo "   MISSING: $1" >&2
}

for required in \
  "$APP/Contents/Info.plist" \
  "$APP/Contents/MacOS/Phrasync" \
  "$APP/Contents/Frameworks/static/index.html" \
  "$APP/Contents/Frameworks/static/app.js" \
  "$APP/Contents/Frameworks/assets/NotoSansJP-VF.ttf" \
  "$APP/Contents/Frameworks/assets/browser/chrome-headless-shell-mac-$BROWSER_ARCH/chrome-headless-shell" \
  "$APP/Contents/Frameworks/assets/models/whisper-tiny/model.bin"; do
  if [[ -f "$required" ]]; then
    echo "   ok: ${required#$APP/}"
  else
    record_missing "${required#$APP/}"
  fi
done
if find "$APP/Contents/Frameworks/imageio_ffmpeg/binaries" -maxdepth 1 -name 'ffmpeg-*' | grep -q .; then
  echo "   ok: bundled FFmpeg"
else
  record_missing "Contents/Frameworks/imageio_ffmpeg/binaries/ffmpeg-*"
fi

if [[ $MISSING_COUNT -gt 0 ]]; then
  echo "" >&2
  echo "!! the bundle is incomplete: $MISSING_COUNT required path(s) missing" >&2
  printf '%s' "$MISSING_DETAIL" >&2
  echo "   The app would install but fail on export or transcription; rebuild once the" >&2
  echo "   missing assets are in place." >&2
  exit 1
fi

echo ""
echo "built: $APP"
echo "log:   $LOG_FILE"
