# macOS application bundle

Builds a double-clickable `Phrasync.app` from this repository. No Terminal, no
virtualenv, no source checkout required at runtime.

```bash
packaging/macos/build_app.sh        # full, clean build
packaging/macos/build_app.sh --fast # reuse the build venv, skip --clean
```

Output: `dist/Phrasync.app`. Logs: `build/macos/logs/build-<timestamp>.log`.

Runtime flags (mostly for diagnostics and CI):

| Flag | Effect |
| --- | --- |
| `--port N` | first port to try (falls through to the next free one) |
| `--browser` | open the editor in the default browser instead of a window |
| `--no-browser` | headless server only, until `/api/shutdown` |
| `--smoke` | open the real window, evaluate a DOM probe after 3 s, log it as `SMOKE {...}`, then close |

```bash
dist/Phrasync.app/Contents/MacOS/Phrasync --smoke   # verifies the packaged GUI
```

## Installing the bundle

```bash
cp -Rc dist/Phrasync.app ~/Desktop/Phrasync.app   # -c clones on APFS (≈922 MiB)
```

Use `cp -Rc` rather than `ditto`: `ditto` expands PyInstaller's shared-library
symlinks into real copies, roughly doubling the size on disk. The clone keeps
the ad-hoc signature valid (`codesign -v` passes), so the copy launches exactly
like the original — verified from an independent directory, not just from the
build tree.

## Architecture

The app is a local web application, so the bundle is a thin desktop shell around
the existing server:

```
Phrasync.app/Contents/MacOS/Phrasync      PyInstaller bootloader (launcher.py)
Phrasync.app/Contents/Frameworks/         frozen Python runtime + dependencies
  static/                                 editor HTML, CSS and JavaScript
  assets/                                 Noto Sans JP, app icon (symlinks into Resources)
  assets/browser/                         bundled Chromium for effects export
  assets/models/whisper-tiny/             bundled Whisper model (symlink into Resources)
  imageio_ffmpeg/binaries/ffmpeg-…        bundled FFmpeg encoder
  ctranslate2/, onnxruntime/, cv2/, av/   native AI and vision runtimes
Phrasync.app/Contents/Resources/          real files behind the Frameworks symlinks
```

`BUNDLE` moves `assets/**` into `Contents/Resources` and leaves symlinks in
`Contents/Frameworks`, which is why `du` reports the two areas inconsistently.
Both paths resolve through `sys._MEIPASS`, so the application reads them without
caring which side it lands on.

`packaging/macos/launcher.py` is the entry point:

1. Reuses an already running Phrasync instance when one answers on the port, so
   double-clicking twice never starts a second server.
2. Otherwise starts uvicorn on the first free loopback port from 5500, using the
   frozen application object (so `/api/shutdown` remains wired to it).
3. Polls `GET /api/instance` until the API truly answers, then opens a native
   Cocoa/WKWebView window (`webview.start(gui="cocoa")`).
4. Stops the server thread it started when the window closes, and nothing else.
   `daemon=True` guarantees the server cannot outlive the process.

If the native window cannot be created the launcher writes a native alert, opens
the editor in the default browser and keeps serving; the editor's own Quit button
stops it.

## Build inputs

* `Phrasync.spec` — PyInstaller onedir build plus `BUNDLE`; collects `static/`,
  `assets/`, `imageio_ffmpeg`, `webview` JS bridge, uvicorn's dynamically named
  loop/protocol modules and every `phrasync` submodule. It also drops the four
  editor backups that sit in `static/` and any `.DS_Store` from the collected
  data table — see [What Git ignores is not what ships](#what-git-ignores-is-not-what-ships).
* `make_icns.py` — turns `assets/Phrasync.png` into a full `.icns` icon set.
* `build_app.sh` — creates an isolated `.venv-build`, installs
  `requirements.txt` + PyInstaller, generates the icon, runs the spec, then
  asserts that the critical resources exist in the bundle.
* `build_app.py` — the same pipeline without shell built-ins, for accounts whose
  shell cannot write to `/var/tmp`; `build_app.sh` is the canonical entry point
  and the two produce the same `dist/Phrasync.app`.
* `install_wheels.py` — fallback for pip's refused unlink step: extracts already
  downloaded wheels into the build venv without deleting anything.

`build_app.sh` unsets `PYTHONPATH` so a caller's shims can never leak into the
frozen runtime.

Both drivers end with a layout check and return a non-zero exit status when a
required member is absent: the bootloader, `Info.plist`, `static/index.html`,
the Noto font, the arch-matched export browser, the Whisper model, and an FFmpeg
binary matched by `imageio_ffmpeg/binaries/ffmpeg-*` — never by an exact name,
because the version and the architecture are part of the filename. A bundle that
installs and then fails on export cannot be reported as a successful build.

One difference is known and deliberate for now: `build_app.sh` also requires
`static/app.js`, while `build_app.py` does not. Both lists already fail on the
missing entry page, so a bundle cannot pass with an empty `static/`, but the
Python driver is one file less strict.

`tests/test_build_scripts.py` covers this without building anything: it runs
both drivers against stubbed pipelines and executes `Phrasync.spec` with
PyInstaller stubbed, so the exit codes, the FFmpeg check and the data-file
exclusions are asserted in seconds.

## Build inputs that are not in the repository

Two inputs are downloaded rather than committed: both are large binaries, and the
browser additionally carries a redistribution restriction. `build_app.sh` checks
for them before building and prints exactly what is missing.

### `assets/browser/` — the export browser (~195 MB)

```bash
python3 -m venv .venv-tools && .venv-tools/bin/pip install playwright
.venv-tools/bin/playwright install chromium-headless-shell

# Playwright unpacks it under ~/Library/Caches/ms-playwright/; copy the whole
# runtime folder, not just the executable, and keep the architecture suffix:
mkdir -p assets/browser/chrome-headless-shell-mac-x64
cp -R ~/Library/Caches/ms-playwright/chromium_headless_shell-*/. \
      assets/browser/chrome-headless-shell-mac-x64/
```

The published bundle used Playwright 1.64, runtime build
`chromium_headless_shell-1223`, reporting itself as
`Google Chrome for Testing 148.0.7778.96`. Licence details and the branding
caveat are in `assets/browser/README.md`.

### `assets/models/whisper-tiny/` — the bundled transcription model (~75.5 MB)

```bash
.venv-tools/bin/pip install huggingface_hub
.venv-tools/bin/hf download Systran/faster-whisper-tiny \
  --revision d90ca5fe260221311c53c58e660288d3deb8d356 \
  --include "config.json" "model.bin" "tokenizer.json" "vocabulary.txt" \
  --local-dir assets/models/whisper-tiny
```

Expected sizes, used for the published bundle: `model.bin` 75,538,270 B,
`tokenizer.json` 2,203,239 B, `vocabulary.txt` 459,861 B, `config.json` 2,249 B.
The repository is MIT-licensed (`Systran/faster-whisper-tiny` is an MIT
conversion of `openai/whisper-tiny`); attribution is in
`THIRD_PARTY_NOTICES.md`.

The app downloads this model by itself when it is missing, so the source tree
works without it — only a bundle that must transcribe on a fresh, offline Mac
needs it at build time. Models larger than `tiny` are never bundled.

## Writable data

The bundle is read-only. Everything the app writes lives outside it:

| Data | Location |
| --- | --- |
| Custom fonts | `~/Library/Application Support/Phrasync/fonts` |
| Workspace (uploads, projects, renders, jobs, logs) | `~/.phrasync` |
| Launcher log | `~/Library/Logs/Phrasync/launcher.log` |
| Support log | `~/.phrasync/logs/phrasync.log` |
| WKWebView storage | `~/Library/Application Support/Phrasync/WebKit` |

`phrasync.config.writable_data_dir()` returns the repository root when running
from source and the Application Support folder when frozen, so the source
workflow is unchanged.

On first launch the launcher copies any `*.ttf/.otf/.ttc` from
`~/phrasync/fonts` into the Application Support folder. It never overwrites or
deletes an existing file.

## What Git ignores is not what ships

`.gitignore` and the packaging filter answer different questions, and for this
repository they point in opposite directions:

| Rule | Lives in | Decides |
| --- | --- | --- |
| `*.bak`, `*.font-backup`, `*.before_*.bak`, `.DS_Store` | `.gitignore` | that Git does not track the file |
| the four `static/` backups below, plus any `.DS_Store` | `Phrasync.spec` (`EXCLUDED_DATA` / `is_excluded_data()`) | that the bundle does not contain the file |
| `assets/browser/`, `assets/models/` | `.gitignore` | that these inputs are not committed — although the bundle **requires** them |

Git plays no part in packaging. PyInstaller walks a collected directory and
copies every file below it, so an ignored file is copied unless the spec drops
it. The spec names the backups exactly, rather than by wildcard, so no runtime
file can be caught by a later edit:

| Path | Why it is not shipped |
| --- | --- |
| `static/app.js.bak` | earlier state of the editor module |
| `static/app-ui.js.bak` | earlier state of the UI module |
| `static/app.js.font-backup` | copy taken before the font wiring moved out |
| `static/i18n.js.before_source_tracking.bak` | dictionary from before the English-source tracking rewrite |

Everything else under `static/` and `assets/` is bundled unchanged, including
`assets/style_reference.png` (a documented reference image, not a backup). The
filter runs on the expanded data table immediately after `Analysis`, so it also
covers anything the `imageio_ffmpeg`, `webview` or AI collections contribute.

## Source changes required

Packaging touches these files. Earlier states were kept as `.bak` files while
the bundle was being built; they are excluded from Git and from the bundle for
the two different reasons above.

| File | Change |
| --- | --- |
| `phrasync/config.py` | `PROJECT_ROOT` resolves through `sys._MEIPASS`; `writable_data_dir()`, `CUSTOM_FONTS_DIR`, `scratch_dir()`, `discard()` |
| `phrasync/font_utils.py` | custom font folder from `config.CUSTOM_FONTS_DIR`; CJK/Japanese fallback logic untouched |
| `phrasync/processes.py` | tracks long-lived encoder/helper processes so they are reaped at exit |
| `phrasync/render_utils.py` | new: `install_output()` moves a finished MP4 into place without losing it when the OS refuses a rename |
| `phrasync/renderer.py`, `phrasync/webgl_renderer.py` | track encoder processes, install output through `install_output()` |
| `phrasync/media.py`, `phrasync/audio_spectrum.py` | no `tempfile` dependency; named scratch logs under `scratch_dir()` |
| `phrasync/jobs.py` | `cancel_all()`, `wait_idle()`, `shutdown()` so shutdown can drain work |
| `app.py` | `/api/shutdown` cancels unfinished jobs before stopping the server |
| `packaging/macos/launcher.py` | bounded exit (`os._exit`), `multiprocessing` helper detection, shutdown logging |
| `static/app.js`, `static/app-fonts.js` | custom font loader split out of `app.js` into `static/app-fonts.js` (`loadCustomFonts()`, `bindFontControls()`), keeping every fragment under the 400-line limit; `app.js` is 399 lines |
| `static/i18n.js`, `static/i18n-dom.js`, `static/i18n-zh.js`, `static/index.html` | Simplified Chinese interface, English source tracking for clean round-trips |

Localization is authored in English inside the templates and modules; the
dictionary in `static/i18n-zh.js` maps those exact strings, `static/i18n.js`
looks them up, and `static/i18n-dom.js` applies the result to the DOM,
dynamically created controls, attribute text and backend messages. It also
records the English source of every string the window code
localises, so switching back to English restores the original wording instead of
stranding the translation. Lyric text, imported subtitles, file names, font
names and exported subtitle content are explicitly excluded from translation.

## Bundled components

| Component | Bundled | Needs the internet | Notes |
| --- | --- | --- | --- |
| CPython 3.12 runtime | yes | no | `libpython3.12.dylib` in `Frameworks` |
| FFmpeg 7.1 CLI | yes | no | `imageio_ffmpeg/binaries/ffmpeg-macos-x86_64-v7.1`, used for MP4 muxing |
| Pillow, NumPy, OpenCV | yes | no | Pillow render path |
| Chromium (headless shell 148) | yes | no | `assets/browser/…/chrome-headless-shell`, see `assets/browser/README.md` |
| pywebview / WKWebView | yes | no | WKWebView is part of macOS |
| faster-whisper + CTranslate2 | yes | no | CPU inference; CUDA/MPS not available in this build |
| Whisper `tiny` model | yes | no | 78 MB in `Contents/Resources/assets/models/whisper-tiny` |
| ONNX Runtime + RapidOCR | yes | no | OCR models ship inside the package |
| UI fonts | yes | no | Noto Sans JP variable font, plus macOS CJK fallback |

Nothing is downloaded at startup. Whisper models other than `tiny` are still a
user-requested download through Hugging Face, which is why the settings panel
keeps an optional access-token field.

## Architectures and macOS versions

* The current bundle is **x86_64 only** (`Mach-O thin (x86_64)`), produced on an
  Intel Mac. It runs natively on Intel and under Rosetta 2 on Apple Silicon.
* `LSMinimumSystemVersion` is **11.0 (Big Sur)**.
* PyInstaller cannot cross-compile. The bootloader and every native extension come
  from the build interpreter, and Intel Macs cannot execute arm64 code at all
  (`hw.optional.arm64` is absent), so an arm64 bundle cannot be built or tested
  here. `build_app.sh` therefore refuses a mismatched target:

  ```bash
  $ PHRASYNC_TARGET_ARCH=arm64 packaging/macos/build_app.sh
  !! PyInstaller cannot build arm64 on a x86_64 host.
     Build on an Apple Silicon Mac (or an arm64 CI runner) instead.
  ```

### Building a native arm64 bundle on an Apple Silicon Mac

`build_app.sh` is architecture-neutral: it reads `uname -m`, checks that the
matching browser runtime is present and names the collected files accordingly.
`phrasync/webgl_renderer.py` resolves `assets/browser/chrome-headless-shell-mac-<arch>/`,
so an arm64 bundle never picks up the x86_64 runtime (and vice versa).

Run the following **on the Apple Silicon Mac**, from the repository root:

```bash
# 1. arm64 CPython 3.12 (python.org installer or `uv python install 3.12`)
/usr/bin/env python3 -c 'import platform; print(platform.machine())'   # must print arm64

# 2. the arm64 export browser (Playwright downloads the host build)
python3 -m venv .venv-tools && .venv-tools/bin/pip install playwright
.venv-tools/bin/playwright install chromium-headless-shell
cp -R ~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-mac/headless_shell \
      assets/browser/chrome-headless-shell-mac-arm64/chrome-headless-shell
#    (keep the folder shape: assets/browser/chrome-headless-shell-mac-arm64/)

# 3. build
packaging/macos/build_app.sh --fast

# 4. verify (the same suite used for x86_64)
dist/Phrasync.app/Contents/MacOS/Phrasync --smoke
PHRASYNC_APP=$PWD/dist/Phrasync.app python <test-suite>/test_phase2.py
```

Delete `assets/browser/chrome-headless-shell-mac-x64/` on that machine first, or
the 195 MB x86_64 runtime is copied into the arm64 bundle unused.

Checklist for the arm64 run (nothing here is verified yet):

1. `lipo -archs dist/Phrasync.app/Contents/MacOS/Phrasync` → `arm64`.
2. `lipo -archs` on `cv2`, `onnxruntime`, `ctranslate2`, `av`, `ffmpeg-*`,
   `chrome-headless-shell` → all `arm64`.
3. `--smoke` reports `locale":"zh-CN"` and `ready":"complete"`.
4. `test_phase2.py` → 23/23, including the effects export through the bundled
   browser (proves SwiftShader/WebGL2 works on Apple Silicon).
5. `verify_offline.py` → 8/8 with the network down.
6. `cp -Rc` to `~/Desktop` and repeat 3–5 from the copy.

> `test_phase2.py` and `verify_offline.py` are the acceptance scripts used on the
> x86_64 build machine (kept in `.buildtest/`, not committed). They are named here
> so an arm64 run reproduces the same checks rather than inventing new ones.

A `universal2` build is **not** claimed to work: NumPy, OpenCV, ONNX Runtime and
CTranslate2 publish separate x86_64 and arm64 wheels, so a universal binary
would need every wheel rebuilt as universal2.

## Signing and distribution

The bundle is **ad-hoc signed** by PyInstaller (`Signature=adhoc`,
`TeamIdentifier=not set`). It is **not notarized** and has no Developer ID.
Consequences when moving it to another Mac:

* Gatekeeper will refuse the first launch after download (quarantine bit).
  Right-click → Open, or `xattr -dr com.apple.quarantine Phrasync.app`, is
  required. Copying over a local network or with `cp -Rc` from a machine that
  never quarantined it avoids the prompt entirely.
* Hardened runtime, notarization and a DMG are out of scope for this build.

## Not included

* Developer ID signing and notarization (see above).
* Whisper models larger than `tiny`, and GPU inference. Asking for another model
  in the settings panel downloads it from Hugging Face on demand.
* Effects exported through the bundled Chromium run WebGL2 on SwiftShader
  (software), which is slower than a hardware-accelerated Chrome. The bundle has
  no H.264 encoder in the browser, so the exporter feeds a canvas to FFmpeg and
  still produces H.264 video with AAC audio.
* Exported videos are written to the folder chosen in the export dialog, never
  into the bundle or a PyInstaller temp directory.
