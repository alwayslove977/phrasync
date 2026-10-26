# macOS maintenance build (fork)

> **简体中文读者请先看这里**：本页是英文的 macOS 修复记录，面向需要审计改动细节的读者。
> 安装、系统要求、签名风险、故障排查与已知限制的完整中文说明在
> [`README_zh.md`](../README_zh.md)；发布包下载见
> [Releases — v0.4.7-macos.3](https://github.com/alwayslove977/phrasync/releases/tag/v0.4.7-macos.3)。
> 本页暂无完整中文译本，文中所有结论都以中文 README 和包内实测为准。
>
> **中文文档入口**：[`README_zh.md`](../README_zh.md) · **English**（本页）

This document describes the `macos-fixes` branch of
[alwayslove977/phrasync](https://github.com/alwayslove977/phrasync), a personal
maintenance fork of [jaydemks/phrasync](https://github.com/jaydemks/phrasync).

It records only work that was actually done. Anything that was not executed or
not verified is listed under [Known limitations](#known-limitations), or marked
as historical in [Verification](#verification), instead of being implied.

- **Base version:** upstream tag `v0.4.7` (`172ea8e`); this branch starts one
  docs-only commit later, at `65fd20e`. Upstream has since published `v0.4.8`,
  `v0.4.9` and `v0.5.0`; those changes are **not** included here.
- **Maintained artefact:** `Phrasync.app` 0.4.7, x86_64, ad-hoc signed, not
  notarised. The latest published bundle is `v0.4.7-macos.3` (2026-10-26), a
  rebuild of the same application sources as `v0.4.7-macos.2` (2026-10-25,
  commit `2a28684`) with the hardened packaging pipeline; the earlier
  `v0.4.7-macos.1` (2026-10-19) was withdrawn and its release and tag were
  deleted. Measurements below are marked as historical wherever they cannot be
  reproduced without rebuilding.
- **Licence:** unchanged from upstream, Apache-2.0 (see `LICENSE`, `NOTICE`,
  `THIRD_PARTY_NOTICES.md`).

## Relationship to upstream

| | Upstream `jaydemks/phrasync` | This fork |
| --- | --- | --- |
| Role | Original project, official Windows/Store releases | Personal macOS packaging and fixes |
| Branches | `main` | `main` mirrors upstream, `macos-fixes` carries the work |
| Version line | 0.4.7 → 0.5.0 | 0.4.7 only; no separate macOS version tag exists in this repository |
| Binary distribution | Microsoft Store (Windows) | GitHub Releases, macOS only |
| Code signing | Store pipeline | none (ad-hoc) |

Nothing in this branch is claimed as original work by the fork maintainer. The
editor, renderer, WebGL pipeline, AI integration and every feature listed in the
upstream README were written by jaydemks. The changes below are fixes and
packaging; they are listed individually so the difference stays auditable.

## Download and install

1. Download `Phrasync-0.4.7-macos.3-x86_64.zip` from
   [Releases](https://github.com/alwayslove977/phrasync/releases/tag/v0.4.7-macos.3).
2. Unzip and drag `Phrasync.app` into `/Applications`.
3. First launch: right-click the app → **Open** → **Open**.
   If macOS still refuses to start it, clear the quarantine flag once:

   ```bash
   xattr -dr com.apple.quarantine /Applications/Phrasync.app
   ```

**This is required because the bundle is not signed with an Apple Developer ID
and is not notarised.** No Apple certificate was available on the build machine
(`security find-identity -v -p codesigning` → 0 valid identities), so Gatekeeper
treats the download as unidentified software. That is a distribution limitation,
not a bug in the app.

**Requirements**

- **macOS 12.0 or later, with OCR requiring 13.4.** The spec declares 12.0 from
  the measured floor instead of the hard-coded `11.0` it used to ship: `vtool
  -show-build` over the 225 Mach-O files in the `v0.4.7-macos.2` bundle finds
  158 that carry a build version — 150 at 12.0 (`av`, numpy and most extension
  modules), 2 at 13.4 (`onnxruntime` 1.23.2, used only by OCR), 4 at 11.0
  (FFmpeg) and 2 at 10.x; the other 67 are static archives without one. dyld
  refuses a library whose minimum is newer than the running system, so 11.x
  cannot even import the core extensions. The 13.4
  objects are reached only through `phrasync/ocr.py`, which imports them lazily
  and turns a failed import into `OCRUnavailable`, so the declared floor stays at
  12.0 for both build flavours and **OCR is not guaranteed on 12.0-13.3**;
  everything else runs there. `PHRASYNC_BUILD_AI=0` removes the ONNX Runtime
  payload and declares the same 12.0. The published `v0.4.7-macos.3` bundle
  declares 12.0; the withdrawn `v0.4.7-macos.1` zip declared 11.0. These
  figures come from the load commands; no 12.x or 13.x machine was available to
  run the bundle on.
- **Intel (x86_64).** The published bundle contains only x86_64 code. On Apple
  Silicon it runs under Rosetta 2; that path was **not** tested on arm64 hardware.
- ~2.5 GB free disk space (906 MB / 864 MiB unpacked, plus the 391.6 MB zip;
  measured on the `v0.4.7-macos.2` bundle).
- No Python, Homebrew, Chrome or Edge installation is needed — the bundle carries
  its own runtime, FFmpeg, Chromium and Whisper `tiny` model.

User data lives outside the bundle, in
`~/Library/Application Support/Phrasync/fonts` (custom fonts) and `~/.phrasync`
(uploads, projects, renders, logs). Replacing the app does not touch them.

## What was fixed

All paths are relative to the repository root. Everything here is a change on
top of upstream `v0.4.7`.

### Running from a bundle instead of a checkout

- `phrasync/config.py` — `resource_root()` resolves `static/` and `assets/`
  through `sys._MEIPASS` when frozen, so the app no longer assumes it is started
  from the repository. `writable_data_dir()` sends writable state to
  `~/Library/Application Support/Phrasync` instead of writing inside the bundle.
- `phrasync/config.py` — `scratch_dir()` falls back to the workspace `tmp/`
  folder when `tempfile.gettempdir()` is unusable, and `discard()` makes cleanup
  a best-effort operation so a refused delete cannot fail a finished export.
- `phrasync/{media,audio_spectrum,renderer,webgl_renderer}.py` — replaced
  `tempfile.TemporaryFile()` with named log files in the scratch directory.
  Anonymous temporary files are unlinked at creation time, which locked-down
  accounts refuse.
- `phrasync/render_utils.py` — new `install_output()`: atomic rename first, then
  unlink-and-rename, then streamed copy. A destination that refuses replacement
  (managed folder, network volume, security software) no longer destroys a
  completed encode.

### Fonts and CJK text

- `phrasync/font_utils.py` — `CUSTOM_FONTS_DIR`, `list_custom_fonts()` (reads the
  embedded family name), `resolve_custom_font_path()` (rejects path separators,
  non-font extensions and anything resolving outside the font directory).
- `phrasync/font_utils.py` — Japanese/CJK fallback now always tries the bundled
  `NotoSansJP-VF.ttf` and then every indexed font, instead of only the `jgothic`
  preset list; failure raises an error naming the offending text.
- `app.py` — `GET /api/fonts` and `GET /api/fonts/file/{filename}` serve the
  list and the font files to the editor.
- `static/app-fonts.js`, `static/app-ui.js` — custom fonts appear in the font
  selector as a `Custom fonts` group, previewed through `FontFace`; the selection
  is stored as `style.fontPath`. The loading half lives in `app-fonts.js` so
  `static/app.js` stays under the 400-line limit; `loadCustomFonts()` keeps its
  name and global reachability.
- `phrasync/render_typography.py` — the Pillow renderer resolves `style.fontPath`
  for custom fonts, so preview and export use the same file.
- `phrasync/kinetic.py`, `static/kinetic.js` — tokenisation splits Han, Kana and
  Hangul per character while keeping Latin words and internal apostrophes
  together. Previously `split()` collapsed a Chinese line into one token, which
  made per-word animation meaningless for CJK lyrics.

### Subtitles

- `phrasync/subtitles.py` — `parse_lrc()` now reads enhanced (word-level) LRC,
  where one line carries several `[mm:ss.xx]` stamps followed by their text, and
  produces per-word cues. Plain line-level LRC still parses through the previous
  code path.

### Whisper model inside the bundle

- `phrasync/model_download.py` — `bundled_model()` probes the short alias, the
  Hugging Face repository name and a `whisper-` prefix;
  `ensure_model(..., bundled_root=...)` uses the bundled copy and only falls back
  to downloading when it is absent.
- `phrasync/transcribe.py` — passes `BUNDLED_MODELS_DIR`, which is what makes a
  first transcription work offline on a fresh Mac.

### Export browser

- `phrasync/webgl_renderer.py` — discovers a bundled Chromium at
  `assets/browser/chrome-headless-shell-mac-<arch>/` before falling back to a
  system Chrome/Edge; the folder carries the architecture so an x86_64 build can
  never pick up an arm64 runtime. `PHRASYNC_BROWSER` still overrides, and
  `PHRASYNC_REQUIRE_BUNDLED_BROWSER=1` fails instead of falling back (used by the
  acceptance tests).
- `phrasync/webgl_renderer.py` — `chrome-headless-shell` rejects `--headless=new`
  and ships without the helper-app sandbox profile, so it is started with
  `--no-sandbox --disable-gpu-sandbox`; a full Chrome/Chromium keeps the default
  sandbox. Added `--no-first-run`, `--disable-background-networking`,
  `--disable-sync`.
- `app.py` — `/api/health` reports which browser will be used
  (`browser.bundled`), making "did it really use the bundled runtime?" checkable.

### Clean shutdown

- `phrasync/jobs.py` — `cancel_all()` flags unfinished jobs at shutdown,
  `wait_idle()` bounds the wait, `shutdown()` retires the worker pool so no idle
  thread keeps the process alive.
- `phrasync/processes.py` — `track()` / `terminate_tracked()` register long-lived
  FFmpeg and Chromium children so closing the window cannot orphan them.
- `app.py` — `/api/shutdown` asks unfinished jobs to stop before stopping the
  server.

### Dependencies on macOS x86_64

`requirements-ai.txt` — platform-conditional pins, because the upstream
unconditional ranges cannot resolve, or resolve to something that no longer
builds, on Intel macOS:

| Package | Pin | Reason |
| --- | --- | --- |
| `onnxruntime` | `<=1.23.2` on Darwin/x86_64 | 1.24+ publishes no macOS x86_64 wheel |
| `opencv-python` | `4.10.0.84` on Darwin/x86_64 | newest release with a `macosx_12_0_x86_64` wheel; later ones trigger a ~40 min CMake build |
| `av` | `>=11,<15` | faster-whisper 1.2.1 calls `av.open(metadata_errors=…)`, removed in PyAV 15 |
| `Pillow` | `>=10.4,<13` | restated so the combined AI environment stays resolvable |

### Interface localisation

- `static/i18n.js` — rewritten around the English source string as the key.
  Every localisation registers `translated → English source` and keeps a reverse
  dictionary plus pattern handling for dynamic sentences (version numbers,
  remaining time, frame counters), so switching back to English restores the
  original text. Upstream wrote the translation into the DOM and lost the English
  source.
- `static/i18n-dom.js` — the DOM half, split out of `i18n.js` so each fragment
  stays under the 400-line limit: tree walking, the attribute `source +
  rendered` state, the MutationObserver, the language controls and the boot
  sequence. It never assigns `currentLanguage`; `setCurrentLanguage()` in
  `i18n.js` is the only writer of that state.
- `static/i18n-zh.js` — new Simplified Chinese dictionary. The literal holds
  **670 entries**; **12 keys appear twice** and every duplicate repeats the same
  value, so the object the code looks up has **658 unique keys**. The duplicates
  are redundant, not conflicting: nothing renders differently because of them.
- `static/app.js` is 399 lines and every fragment in `APP_SCRIPTS` fits the
  restored uniform 400-line limit, which `tests/test_frontend.py` asserts. The
  450-line exemption on `static/i18n.js` is gone: the engine is 331 lines, the
  DOM half (`static/i18n-dom.js`) 255, and the custom font loader
  (`static/app-fonts.js`) 70.
- `static/app-editor-tools.js`, `app-export-range.js`, `app-footage.js`,
  `app-media-bin.js`, `app-visual-tracks.js` — removed the per-module
  `Object.assign(ITALIAN, …)` blocks; strings now go through `t()`.
- `static/app-cues.js`, `app-modes.js`, `app-workflows.js` — replaced
  `document.documentElement.lang === "it" ? … : …` ternaries with `t()`.
- `static/index.html`, `static/styles.css` — language selector in
  **Settings & about**, plus the styles for it.

**This replaces the Italian interface with Simplified Chinese.** Upstream ships
English and Italian; this branch ships English and Simplified Chinese. Lyrics,
subtitle text, project files and exported videos are never translated.

### Packaging

New, macOS-only, does not affect the upstream Windows/Store build:

- `packaging/macos/Phrasync.spec` — PyInstaller onedir bundle with `BUNDLE`. It
  also drops the four editor backups that sit in `static/` plus any `.DS_Store`
  from the collected data table: `.gitignore` has no effect on what PyInstaller
  copies, so the exclusion has to live in the spec.
- `packaging/macos/build_app.sh` — one-command build; refuses a cross-architecture
  request (`PHRASYNC_TARGET_ARCH`), verifies the arch-matched browser runtime and
  every required bundle member after building.
- `packaging/macos/build_app.py` — the same build without shell built-ins, for
  accounts whose shell cannot write to `/var/tmp`. Both drivers verify the
  bundle after building (entry page, model, arch-matched browser, FFmpeg matched
  by `ffmpeg-*`) and exit non-zero when one is absent, so a hollow `.app` can no
  longer be reported as a successful build. The shell driver additionally
  requires `static/app.js`; the Python driver does not — see
  `packaging/macos/README.md` for that known difference.
- `packaging/macos/launcher.py` — reuses a running instance, starts uvicorn on the
  first free loopback port from 5500, waits for `/api/instance`, opens a native
  Cocoa/WKWebView window, stops only the server it started.
- `packaging/macos/install_wheels.py`, `make_icns.py` — helpers; the first
  extracts wheels when pip's unlink step is refused, the second builds the icon
  set.
- `packaging/macos/README.md` — build instructions, layout, and the two build
  inputs that are downloaded rather than committed.
- `tests/test_build_scripts.py` — new; drives both build drivers against stubbed
  pipelines and executes the spec with PyInstaller stubbed, so the exit codes and
  the data exclusions are checked without a 900 MB build.
- `docs/PHASE2_DELIVERY.md` — the verification report for the published bundle;
  it is a historical build record, not an acceptance report for this tree.

## Build from source

```bash
git clone https://github.com/alwayslove977/phrasync.git
cd phrasync
git checkout macos-fixes
packaging/macos/build_app.sh        # or --fast to reuse the build venv
```

`assets/browser/` and `assets/models/whisper-tiny/` are **not** in the
repository (size and, for the browser, redistribution). `build_app.sh` reports
them as missing rather than failing silently; `packaging/macos/README.md`
documents how to obtain both, with the exact versions used for the published
bundle.

## Verification

Two kinds of evidence are kept apart: what can be re-run from this source tree
today, and what was measured on the published bundle when it was built.

### Re-run from this source tree (2026-10-25)

| Check | Command | Result |
| --- | --- | --- |
| Localisation round-trip, dictionary priority, DOM/attribute paths | `pytest tests/test_i18n_ui.py` | 8 passed |
| Fragment order, uniform 400-line limit, one shared script scope | `pytest tests/test_frontend.py` | 9 passed |
| Cue pagination in the Node harness with and without `window.t` | `pytest tests/test_cue_pagination.py` | 1 passed |
| Build drivers' exit codes, FFmpeg check, spec data exclusions | `pytest tests/test_build_scripts.py` | 12 passed |

30 cases, all passing, no bundle involved. The cue-pagination harness passes
because `static/app-cues.js` guards the call with
`typeof window !== "undefined" && typeof window.t === "function"`; without that
guard the harness throws `ReferenceError: window is not defined` while the
browser path stays fine.

The rest of `tests/` **cannot be collected in this environment**: importing
`phrasync` runs `config.workspace_root()`, which creates `uploads/`, `renders/`,
`jobs/`, `projects/` and `tmp/` under `~/.phrasync`, and the sandboxed shell
refuses those `mkdir` calls (`PermissionError` during collection, 26 files
affected). That is an environment limit, not a test outcome, and it is the only
reason the numbers below are not re-measured.

### Recorded against the published bundle (historical, not re-run)

Produced on the build machine when the 0.4.7 bundle was packaged. The logs live
in `.buildtest/*.log` and were **not** committed; no bundle is present in this
repository, so none of these rows were re-verified for this document and none of
them describe a build of the current source tree.

| Check | Result |
| --- | --- |
| Launch from a directory outside the source tree | pass |
| Offline (network disabled) operation, 8 checks | 8/8 pass |
| Acceptance suite against the built `.app`, 23 checks | 23/23 pass |
| Interface language switch and restore, both directions | pass, 0 residual Chinese strings after switching back |
| Chinese/Japanese frame render + OCR of the output frame | 6/6 characters |
| MP4 export, Pillow path and WebGL path | H.264 + AAC, `major_brand: isom` |
| Offline Whisper transcription | pass |
| Offline RapidOCR | pass |
| Exit leaves no service or helper process | pass |

The upstream Python suite (`tests/`, 130 cases at the time) was run then against
this source tree with an isolated `PHRASYNC_HOME`; 22 cases failed. That run was
not repeated, and its per-test list was only partly recorded: ten failures were
environmental (seven missing optional AI packages — `huggingface_hub`,
`faster_whisper`, `av`, `tqdm`; two a temporary directory the sandbox refused;
one a Windows-only path), and twelve were behaviour. Two of those twelve have
since been fixed in this branch — the cue-pagination guard above and the
front-end assertions (Italian toggle, 450-line exemption removed) — and both
pass today. The other ten were never itemised and have not been re-checked.

## Known limitations

- **Not signed, not notarised.** Gatekeeper blocks a plain double-click on another
  Mac; see the install steps above.
- **x86_64 only.** No arm64 or universal2 build. PyInstaller cannot cross-compile,
  and NumPy/OpenCV/ONNX Runtime/CTranslate2 publish no universal2 macOS wheels.
  Running under Rosetta 2 on Apple Silicon was not tested on real hardware.
- **Larger Whisper models are not bundled.** `small`/`medium` still download on
  demand from Hugging Face.
- **GPU inference is unavailable** on macOS; transcription is CPU-only.
- **The bundled Chromium is Chrome for Testing**, which carries Google branding.
  Redistribution on a public download page may require Google's permission;
  Chromium itself is BSD-3-Clause and its licence text ships next to the binary at
  `assets/browser/chrome-headless-shell-mac-x64/LICENSE.headless_shell`. The
  archive is published for personal use with that limitation stated.
- **Fonts are not redistributed.** The two Chinese fonts used while developing
  this build have no redistribution grant and are not in the repository or the
  app. Add your own through the font selector after installing.
