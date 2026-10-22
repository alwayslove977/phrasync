# Phrasync v0.4.9

This maintenance release improves in-app Microsoft Store updates. GitHub v0.4.9 is published. The matching 0.4.9.0 Microsoft Store package was submitted for certification on October 22, 2026, with automatic publication after approval. The previous approved Store version remains available until rollout completes.

Individual package results and Store queue states are checked before reporting completion. A failed package no longer produces a misleading success or restart message. Original HRESULT error codes remain visible in Diagnostics.

For the observed Windows Update download fault 0x80244007, refresh the Store query and retry once. Cancellation is never retried automatically, and persistent failures offer the official Store fallback.

Show real Store download and installation progress, with an indeterminate indicator when Microsoft has not supplied a percentage. Check at startup and offer an update notification without installing automatically or covering an existing welcome dialog.

Record update attempts locally and verify the running package after relaunch. Register the packaged executable for Windows-managed restart during patching, without relaunching an old WindowsApps path or registering a source Python interpreter.

Improve spacing around the welcome dialog's optional Buy me a coffee button. Existing editing and export features remain unchanged.

246 automated Windows tests passed. The original Store failure was reproduced and that installation was successfully updated from 0.4.7 to 0.4.8 through Microsoft Store without uninstalling. The new 0.4.9 recovery and restart flow still needs confirmation with a subsequent Store-distributed update. Persistent Microsoft service failures cannot be guaranteed away by app code.

If your older in-app updater cannot install this release, update through Microsoft Store directly. A routine uninstall is not required for this fix. Full notes: [docs/RELEASE_v0.4.9.md](docs/RELEASE_v0.4.9.md).

---

# Phrasync v0.4.8

This maintenance update improves timed lyric imports, custom fonts and CJK exports. GitHub v0.4.8 is published. The matching 0.4.8.0 Microsoft Store package was submitted for certification on October 20, 2026. Store availability follows approval and rollout.

- Import Enhanced LRC word timestamps in angle or inline square brackets, including millisecond precision, repeated line timestamps, offsets, and explicit end boundaries. Standard LRC, SRT, VTT, JSON and plain-text imports remain supported.
- Preserve supplied timing when importing timed lyrics. Auto-align remains available explicitly; plain-text imports still align automatically.
- Preserve word/syllable boundaries for unspaced CJK lyrics in both preview and offline rendering. Enhanced LRC export retains real word timing and final word boundaries, without inventing word tags for untimed lines.
- Validate uploaded fonts, preserve Unicode display filenames, and reuse identical new font uploads instead of storing another copy. Existing assets are not deleted or migrated.
- Load custom TTF/OTF fonts into preview as well as export, restore them with projects, offer saved/local font selection and an explicit return to preset fonts. Unsupported browser font formats produce a visible preview warning.
- Search installed, bundled, local and uploaded fonts for Chinese, Japanese and Korean fallback coverage. Report missing coverage during preflight with required characters and font-check counts instead of a misleading Japanese-only export error.
- Clarify that importing lyrics replaces the current cues, including the English demo. Add an explicit, confirmed Clear all lyrics action.
- The local browser edition now offers a native Choose folder dialog for MP4 exports, with cancellation preserving the previous destination, duplicate-dialog protection, and manual-path fallback. The desktop window retains its existing native bridge. No browser directory-upload trick, intermediate video copy or external service is required.

Particle-dissolve animation and alpha/transparent video export are separate feature requests and are not included here. Credit Crawl is awaiting its author's PR. macOS fixes require confirmation on a real Mac; local runtime tests were performed on Windows.

---

# Phrasync v0.4.7 — Microsoft Store update fixes

GitHub source release. The matching 0.4.7.0 Store package was submitted for certification on October 18, 2026. Availability follows approval and rollout. This maintenance update focuses on the in-app Microsoft Store update flow.

- Replaced browser-native update confirmation (which displayed the localhost origin) with an accessible, branded Phrasync dialog, with English/Italian text and a safe default cancel action.
- Initiate Store update installation on the desktop STA/UI thread and bind StoreContext to the actual Phrasync HWND before requesting Store consent. The asynchronous operation is awaited off the UI thread so the desktop stays responsive.
- Decode numeric WinRT update states correctly; distinguish completion, cancellation, pending deployment, low battery and Wi-Fi requirements.
- Retain original exception details and HRESULT codes in Diagnostics, rather than replacing everything with a generic error.
- Prevent overlapping install requests and provide an explicit Microsoft Store fallback button. Local/GitHub builds still cannot install Store updates over source.

Local tests can verify window ownership, thread dispatch, consent and error/state handling without installing updates. A complete Store installation still requires verification with a real Store-distributed upgrade. Older installed clients do not acquire this fix until updated through Microsoft Store.

---

# Phrasync v0.4.6 — Export reliability and speed

GitHub source release. The matching 0.4.6.0 Microsoft Store package was submitted for certification on October 17, 2026; the previous Store build remains available until approval and rollout.

- Fixed preflight incorrectly rejecting valid image/video base types when background footage tracks are enabled. Unknown types, missing footage and invalid clip ranges still fail validation.
- Export lets Chromium choose hardware graphics with software fallback, rather than forcing SwiftShader for every project.
- The FFmpeg compatibility path streams bounded raw frames over an authenticated loopback bridge instead of PNG/base64 encoding and decoding every frame. Small deterministic batches reduce browser-control overhead; no frames are skipped.
- Flat lyrics are composited before encoding, eliminating a second video encode while preserving the existing font and typography renderer.
- The intermediate video retains frame timestamps before MP4/audio muxing, including B-frames and nonzero IN/OUT ranges.
- Support logs include the selected graphics renderer and encoding throughput.

Measured locally: the same two-second 1080p30 effects export decreased from 36.7 seconds to approximately 9 seconds. A ten-second sample took 22.4 seconds. These are test-project measurements, not a guarantee of real-time rendering for every project or computer.

---

# Phrasync v0.4.5

GitHub source release; the matching 0.4.5.0 Microsoft Store package was submitted for certification on October 6, 2026. Store availability follows Microsoft's certification and rollout; the previous build remains available until then.

- Mark an MP4 export interval on the timeline with I/O, editable seconds or draggable IN/OUT markers. Export only that interval with original audio, footage, 2D/3D lyrics and effect timing; clear it to render the full timeline.
- Timeline duration follows loaded media and footage automatically, or can be set manually and saved with the project.

- Adding cues keeps the lyric list at its current scroll position.
- Pan the timeline with the middle mouse button or its horizontal scrollbar.
- Duplicate a cue with its copy button or Ctrl+D, preserving and shifting word timings.
- Save and load projects through native Windows file dialogs.
- Choose where to save SRT, VTT, ASS and LRC exports; cancelling no longer reports success.
- WebGL 4K exports can use a bounded-memory FFmpeg compatibility encoder when browser H.264 encoding is unavailable.
- Custom video bitrate in Mbps, including 150 Mbps, is honoured across the export engines without the previous 28 Mbps ceiling. Automatic CRF quality remains available.
- An export folder must be explicitly selected before rendering. Each job saves one project-named MP4 there; the result button shows that existing file instead of making a second copy. Repeated exports use readable numbered names without overwriting previous videos.
- Added a background-footage timeline: combine images and MP4/WebM video, move, trim, split and duplicate clips, change source-in and speed, and animate pan/zoom without altering the original media.
- Import footage into a reusable media bin and drag it onto the timeline. Clip actions appear beside the selected track; numeric editing retains precise inputs with quick sliders. Large imports show individual progress and checking status without automatically changing the edit.
- Added adjustable black-and-white, pendulum movement, beat shake/flash, a two-color gradient, particles and an audio-frequency spectrum overlay. Effects are shared between preview and export, with streamed audio analysis for the offline spectrum.
- Existing single backgrounds and 2D/3D lyrics remain available. Footage video sound is muted; the song/source audio remains the master track. Bright flash effects are disabled by default and include a photosensitivity warning.

- Integrated 2D/3D visuals can be added to the media bin as editable clips, then combined with images/video on up to four background tracks. Per-clip opacity, fades, wipe and slide transitions use the same compositor in preview and export.
- Background tracks can be removed, with confirmation for occupied tracks. Remaining clips are reindexed correctly; original media stays in the bin, including when the last track is removed.
- Extremely dense repeated-token transcription loops are retried in isolation, without conditioning on earlier text. Unreliable loops cannot stretch the following lyrics out of time; normal repeated vocals and requested language settings retain their existing decoding path.
- Added Spiral Flight and Word Constellation typography in both flat and spatial modes, with matching offline timing math. Existing timing and styles are unchanged.
- Added beat-drop zoom and light pulses, with a beat-grid or detected-transient trigger alongside the existing shake, pendulum, flash, gradient, particles and spectrum controls.
- The welcome popup includes optional coffee support and an explicit Don't show this again checkbox.

- Timeline zoom buttons center on the playhead. Background clips have a right-click menu with split, duplicate, move, speed, zoom and reset controls.
- New/load/save project commands are under File at the top left, with keyboard shortcuts. Projects retain footage library, clip edits and effects.
- Settings includes the running software version, author contacts and optional external Buy Me a Coffee support.

---

# Phrasync v0.4.4 — GitHub source release

- Manually added lyric cues remain visible during playback and MP4 export even when they overlap transcribed cues. Existing projects with untimed manual cues are also handled.
- New manual cues use the playhead's lyric timing offset correctly, and editing an active cue refreshes its preview immediately.
- The Microsoft Store package is separate from this GitHub source release. Store v0.4.3 is published, and v0.4.4 has been submitted for certification with updated release notes and the demo trailer.

---

# Phrasync v0.4.3 — Microsoft Store submission

This release makes updates and troubleshooting more reliable.

- Fixed a WebView2 cache mismatch that could leave controls unresponsive after an in-place Store update. The desktop document and static resources now use versioned URLs and fresh-cache rules.
- Added Settings → App updates. Store-installed copies can check for future releases and request installation directly from Phrasync, with the user's consent. Portable preview copies explain why Store updates are unavailable.
- Added a Diagnostics panel with recent errors and relevant Windows, CPU, GPU, RAM, app-version, and disk information. Reports can be copied or downloaded for support; users should review them before sharing.
- Kept the 0.4.2 export fixes: choose an output folder before rendering, open selected or default render folders, save MP4 through the native Windows dialog, and render Japanese lyrics with a suitable fallback font.

**One-time transition for existing users:** If an earlier Phrasync version is installed, manually uninstall it and install v0.4.3 from Microsoft Store. This is recommended once to clear any stale WebView2 data from the previous installation. Back up important projects before uninstalling. Future Store updates can be checked and installed from Settings → App updates without manually visiting the Store listing.

The Store's in-app installation path cannot be exercised end-to-end in this portable preview; it must be verified with a Store-installed package when a subsequent release becomes available.

---

# Phrasync v0.4.2

This update fixes Windows desktop video export.

- Choose the output folder before starting an MP4 render. The rendered file is written directly there.
- Open the renders folder from the export window, including the folder containing a completed video.
- Download MP4 now opens a native Save As dialog in the Windows app; the browser version keeps a normal download link.
- Export controls are available in English and Italian.
- The built-in Phrasync renders folder has a dedicated button even when a different export folder is selected.
- Japanese lyrics now use a Japanese-capable font only where the selected font lacks glyphs; a freely licensed fallback font is bundled for PCs without Japanese system fonts.

---

# Phrasync v0.3.0

Released 2026-09-08.

This release makes the Store desktop experience substantially lighter and fixes live model-download reporting.

## Highlights

- Whisper model progress now counts Hugging Face's active `.incomplete` payload, so percentage, transferred size, speed, and ETA advance throughout the first download.
- The Windows WebView2 host explicitly enables GPU compositing and GPU canvas rasterization.
- Expensive preview canvases are capped at 30 FPS during playback and 12 FPS while idle, independently from full-quality video export.
- High-DPI preview and timeline buffers are constrained inside the desktop host, eliminating unnecessary multi-million-pixel redraws.
- The timeline no longer repaints continuously while playback is stopped, and hidden windows pause preview work.
- Costly translucent backdrop blurs are replaced with opaque desktop surfaces while preserving the same visual hierarchy.
- The Phrasync logo is now embedded in the Windows executable for the window, taskbar, and application switcher.

## Verified for this release

- The active Hugging Face cache layout is covered by an automated progress-counting regression test.
- The packaged executable and Microsoft Store MSIX are tested separately from the browser development build.
- The Windows package uses the existing Store identity and version **0.3.0.0**.

---

# Phrasync v0.2.0

Released 2026-09-08.

This release turns the Store build into a native Windows experience and makes first-run AI setup transparent.

## Highlights

- Phrasync now opens in its own Windows WebView2 application window, with no Command Prompt and no browser tab.
- The first-run overlay explains that each Whisper model is downloaded once and stored locally.
- Model downloads now show percentage, transferred size, and estimated time remaining before transcription begins.
- English is the default interface language; users can switch between English and Italian from the onboarding overlay or the main toolbar.
- NVIDIA CUDA acceleration is detected automatically, with an explicit GPU/CPU status shown in the interface.
- CUDA 12 cuBLAS and cuDNN 9 runtime libraries are included in the Windows Store package so compatible NVIDIA systems do not require a separate CUDA Toolkit installation.

## Verified for this release

- The packaged GUI executable opens a native window titled **Phrasync** and does not create a console window.
- The packaged health check reports Phrasync 0.2.0, Faster-Whisper available, CUDA available, and one NVIDIA device on an RTX 3090 test system.
- English and Italian onboarding layouts were visually verified at 1440 × 1000.
- The complete suite reports **56 passing tests**.
- The Microsoft Store MSIX uses the existing product identity and version **0.2.0.0**.

---

# Phrasync v0.1.1

Released 2026-08-27.

This patch removes the final-export limitation for Odyssey and world-space typography.

## Highlights

- Odyssey 3D MP4 export now uses the same Three.js/WebGL scene engine as the live preview instead of being blocked by preflight.
- World-space 3D typography exports as real volumetric WebGL geometry over Odyssey, built-in dynamic visuals, images, and videos.
- Flat kinetic typography over Odyssey keeps the WebGL environment and is composited during the final H.264 pass.
- Chrome or Edge runs headlessly for deterministic frame generation; WebCodecs produces H.264 and FFmpeg muxes the original audio into the final MP4.
- Odyssey Flat retains a deterministic CPU raster export path for systems and projects that do not need the WebGL scene.
- The critic now reports the selected WebGL export path as an informational note instead of raising the former preview-only blocking errors.
- Added an explicit `websockets` runtime dependency for the local Chrome DevTools connection.

## Verified for this release

- Real MP4 smoke renders pass for Odyssey 3D with 3D text, Odyssey 3D with flat text, and Aurora with 3D text.
- Every smoke output decodes successfully through FFmpeg.
- The complete suite reports **52 passing tests**.
- The updated server was verified on Windows 11 with OCR, Faster-Whisper, and CUDA still available after restart.

## Current limits

- WebGL MP4 export requires a local Chrome or Edge installation with WebCodecs support.
- Long high-resolution WebGL exports can use substantial browser memory while the encoded H.264 stream is assembled.
- Odyssey Flat is a CPU raster interpretation; choose Odyssey 3D when preview-faithful lighting and geometry are required.
- Linux and macOS launchers remain source-level supported but were not physically verified for this patch.

---

# Phrasync v0.1.0

This is the first public release: useful today, intentionally honest about what still needs engineering.

## Highlights

- Two first-class project modes: **Lyric Video** for music and **Subtitles** for spoken audio or video.
- A video selected in Subtitles mode becomes the transcription source, preview footage, render background, and final audio source without duplicate setup.
- Hierarchical local Faster-Whisper transcription: ten-second language mapping, confidence and silence filtering, stable span smoothing, quiet-boundary snapping, language-locked span decoding, phrase-level language verification, selective corrective re-reading, adaptive fallback, and persisted gauntlet diagnostics.
- Auto follows language changes across a track; one code locks a language, comma-separated codes restrict the candidate set, and `single` keeps one automatically detected language.
- Language metadata is preserved on cues and returned as a dominant language, ordered language list, editable API-level span map, confidence, and diagnostics.
- Seven kinetic 2D typography presets with browser/Python timing parity.
- Seven separately named and tuned 3D typography personalities with independent world-space X/Y offsets.
- Grounded world-space 3D text: phrases are planted on the scene floor and the camera travels past them like other meshes.
- Odyssey 3D environments for Japan, Italy, China, and the USA.
- Manual rain, snow, fog, storms, falling leaves, dawn, day, sunset, night, and four seasons.
- **Automatic journey** mode crossfades daytime and seasonal colour while selecting deterministic weather from the playback clock.
- Image, video, and dynamic backgrounds; local project save/load; critic preflight; cancellable render jobs; H.264 MP4 download and postflight decoding.

## Verified for this release

- 50 automated tests pass in the current release environment.
- A real short MP4 render passes with one video file used for both picture and audio in Subtitles mode.
- Chrome smoke coverage passes for every 2D/3D text composition state over Odyssey 3D, a 2D dynamic visual, image, and video modes; actual MP4 decoding is covered by the integration render above.
- 3D text remains world-planted and completes its fly-past at scene speeds of 20%, 100%, and 260%.
- Weather, daytime, seasons, automatic state changes, project-mode copy, and the 3D preset catalogue pass in the live browser with zero captured exceptions.
- Repeated 244.9-second `large-v3` Auto runs map Italian, Portuguese, French, Spanish, English, and Japanese; recover the opening lyrics; preserve Japanese writing; follow late line-level switches; and produce no false outro after the final vocal.
- Development and physical testing were performed on Windows 11, Ryzen 9 3900X, 32 GB RAM, and RTX 3090 24 GB. Linux and macOS launchers are included but not physically release-tested yet.

## Known limits

- Odyssey Flat, Odyssey 3D, and 3D typography are preview-only in v0.1.0. MP4 preflight blocks them explicitly because the Python renderer does not yet reproduce WebGL output faithfully.
- Full song-length output has not yet been rendered. Current verification uses short engineering renders; complete music videos will be added after publication.
- Projects reference media in the local Phrasync workspace rather than embedding it into a portable archive.
- Browser video preview is intentionally limited to MP4 and WebM; convert MOV, MKV, AVI, and unusual codecs before import.
- The transcription workflow performs strongly on the tested songs, but expressive singing, unusual pronunciation, effects, and closely related languages can still need human review.
- There is no signed installer, automatic updater, or hosted web version.

## Evaluated next-step technology

- Troika Three Text for SDF-quality, multilingual 3D typography.
- JASSUB/libass for professional ASS subtitle parity in browser preview.
- Three.js Sky for physically based atmosphere when deterministic export parity is ready.
- three.quarks only if future VFX outgrow the lightweight deterministic weather system.

Phrasync is created by jaydemks and distributed under Apache-2.0 with attribution preserved through `NOTICE`. Output belongs to its creator, subject to the rights they hold in the source music, text, footage, images, and fonts.
