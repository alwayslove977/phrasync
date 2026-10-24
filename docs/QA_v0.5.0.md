# Phrasync 0.5.0 local verification

This candidate is not published. The README and the existing public release notes have not been replaced.

## Confirmed findings

Issue #5 originally reported a generic missing-canvas-frame error. Its original project and media were not attached, so its exact failure cannot be asserted from the report alone.

A synthetic 270-second Spectrum/Particles project reproduced a real upload failure in the existing frame bridge. With browser network tracing enabled, the failed upload reported `net::ERR_CONNECTION_TIMED_OUT`. The earlier evaluator discarded the browser exception details.

The single-threaded frame server can wait on an idle browser preconnection while the real frame upload waits on a different connection. A negative-control test reproduces this stall with the original serial server. The corrected server handles preconnections concurrently and keeps frame uploads on persistent HTTP/1.1 connections. Consumption is locked and remains ordered. The corrected source export delivered and decoded all 8,100 frames without PNG fallback.

This behaviour is also described in the [Python HTTP server documentation](https://docs.python.org/3/library/http.server.html#http.server.ThreadingHTTPServer). The service is private loopback transport, not a public-facing web server. Per-session tokens, exact Origin checks, bounded payload sizes and PNG dimension checks remain enforced.

## Coverage

Final results: 285 automated tests passed with zero failures, errors or skips. The source matrix contains 70 passing cases, and the final Windows executable matrix contains 68 passing cases. Both completed the 270-second, 8,100-frame synthetic export. The PNG fault-injection cases were also repeated successfully after the connection fix.

The source matrix includes dynamic, image and video backgrounds with 2D or 3D text; effects enabled or disabled; full and IN/OUT export; four layered footage tracks; video trimming/rate/pan/zoom; integrated Ocean and Equalizer clips; cut/fade/wipe/slide transitions; the built-in visual families; 12/23/24/25/30/50/60 fps; landscape/portrait; no-audio export; 4K 2D/3D at 24/30/60 fps and 150 Mbps; browser WebCodecs and FFmpeg paths; single-frame selections; a 10-second 1080p export; and the synthetic 270-second project.

Two fault-injection cases verify PNG recovery with a normal image background and with layered footage plus 3D text. Raw transport remains the default in normal cases. Tests also verify that an encoder rejection is not retried as a duplicate frame.

Each successful matrix output is decoded completely. Frame count, actual stream frame rate, dimensions, duration and a nonblack frame are checked. Selected output frames have also been inspected visually, including Chinese/Japanese text.

The Windows executable is built separately under `release/v0.5.0-local`, with the standard desktop build dependencies. Its updated static resources match the source. A separate API matrix exercises the compiled renderer, preflight and postflight, rather than importing the source renderer.

## Spectrum and audio checks

An actual Chromium OfflineAudioContext analyser was compared with the FFT/window/normalisation/byte mapping used by the new source. The reference tone produced zero byte difference with smoothing set to 0 and 0.78. Timeline tests cover IN-range history, frame-rate-independent smoothing and absence of first-frame look-ahead. This verifies the analysis math, not identical live scheduling or device latency.

The test environment uses Python 3.11 and PyAV 18.1.0. PyAV 19 cannot be installed into that Python version. The signature incompatibility was reproduced against real audio decoding, and the FFmpeg compatibility path produced the expected 16 kHz samples. Fixed-language retry and unrelated-error propagation are tested separately. No claim is made that a real PyAV 19 binary or a new Whisper-model transcription was run locally.

## Local evidence

Final results are recorded under `qa_out/render-050`:

* `pytest-final.xml`
* `source-final-results.json`
* `packaged-final-results.json`
* `web-audio-parity.json`
* `png-final-results.json`
* `source-before-keepalive-fix-results.json`
* `packaged-before-short-range-fix-results.json`

The initial Windows matrix found valid 0.1-second exports incorrectly rejected by postflight. That guard was corrected to reject missing/nonfinite/zero duration instead, with real single-frame regression tests. The final executable is tested again after this correction and the connection fix.

Earlier candidate executable SHA-256, before the GPU/clock follow-up: `12AE0A63FA42535AD1FA5AD8C8AA284FC88A3872DDCCB16C12E50373097F530A`.

## Initial real-project comparison (24 October, before follow-up fixes)

A copy of the user's saved "I Still Wait" project was combined with an existing imported neon-alley video. Original project and media were preserved. The compiled candidate exported timeline seconds 13 to 29 at 1920 x 1080, 30 fps: 480 frames, complete decode, correct 16-second duration, and postflight passed. The composition includes two overlapping footage clips, pan/zoom, a crossfade, 3D lyrics, particles, spectrum and beat effects.

Three frames from the actual interactive playback pipeline were compared with MP4 frames, not with a second invocation of the export renderer. Text and composition are present, and the exported audio correlates 0.99945 with the original selected range. However, the test is **not a complete parity pass**: at timeline 26.500 seconds the preview footage element reported 6.834216 seconds where its clip requires 7.000 seconds. The visible footage differs accordingly. The current playing-preview sync tolerates 0.2 seconds of drift; the underlying scheduling cause has not yet been fully isolated. Do not describe the preview/export match as exact or this issue as fixed.

The measured render took 101.093 seconds for this 16-second complex excerpt while browser comparison work was also running. The export was initially retained because the user's parity condition was not satisfied. This is historical diagnostic evidence, not the final candidate result.

## GPU and preview-clock follow-up

Compatible H.264 footage now travels to the private export browser as original compressed packets, demuxed in small batches. WebCodecs decodes them sequentially, retaining a bounded look-ahead and releasing old VideoFrames. Rotation, anamorphic, non-H.264 and unsupported colour formats stay on the browser compatibility path. The complete 3D canvas can stream hardware-preferred encoded H.264 chunks instead of uploading raw RGBA. Explicit colour metadata avoids interpreting the GPU encoder's BT.709 matrix as BT.601. Flat PIL text remains on the complete lossless transport path; a successfully probed NVENC encoder may accelerate that path, with full-pass CPU restart on device failure.

Preview clocks now converge actively instead of leaving a fixed 200 ms tolerance uncorrected. Pre-rolling upcoming trimmed clips also covers reuse of the same asset in two separate clips. Tests cover convergence without seek storms, paused seeks, drawing/closing VideoFrames, trusted packet access, bounded batches and CPU restart after an NVENC failure. An injected browser encoder failure after a completed batch is checked against the original output frame count, preventing partial-stream duplication.

The real project comparison uses the same 16-second range at 1920 x 1080, 30 fps, 20 Mbps, two overlapping video clips, pan/zoom, crossfade, 3D lyrics, particles, spectrum and beat effects. Actual live playback frames are compared with decoded MP4 frames. The previously failing point now shows only a few milliseconds of media-clock error, rather than 166 ms; displayed video naturally remains quantised to its source frame rate. Image differences include H.264 encoding, resizing, live analyser scheduling and the small difference between capture time and the nearest output frame; pixel identity is not claimed.

Final follow-up evidence is in `qa_out/real-project-050/final-summary.json`, `comparison.json`, `audio-comparison.json`, `gpu-telemetry.json`, `preview-vs-export.jpg`, individual capture records and a complete static-resource hash manifest. The original saved project is checked against its initial SHA-256. The final isolated Windows-package export is timed with the other render/test jobs stopped, and GPU encoder/decoder activity is sampled. Intermediate timings recorded while developing the new frame path are not release benchmarks.

The final isolated package exported all 480 frames in 15.765 seconds, versus the initial diagnostic run's 101.093 seconds. Its video pass took 9.88 seconds. GPU telemetry recorded encoder activity up to 41% and decoder activity up to 29%. Maximum media-clock error across the sampled points was 3.275 ms. Final video matrix/primaries/transfer tags are BT.709 / BT.709 / sRGB. Audio correlation with the original selected range was 0.99945. These measurements describe this RTX 3090 composition, not a guarantee of real-time rendering for every scene or GPU.

The final automated suite passed 293 tests, with no failures, errors or skips. After verification, 152 generated QA videos (316.27 MiB) were deleted as requested. Original projects/media and screenshots, hashes, scripts and reports remain; the generated videos can be recreated. See `cleanup.json` for the exact cleanup scope. The deleted MP4 paths in retained render reports are historical evidence, not current downloadable files.

The structural matrices cover 70 source cases and 67 Windows-package cases. Representative footage, framerate, 4K and recovery cases are rerun after the final metadata-only colour adjustment. Updated automated results are in `qa_out/render-050/pytest-gpu-final.xml`; matrix results are `source-gpu-final-results.json` and `packaged-gpu-final-results.json`. Executable and bundled-static hashes are recorded in the final summary/manifest, rather than assuming an executable hash alone identifies all external resources.

## Limits

The original reporter must still retry the original project. Most cross-combination tests are short smoke exports; 4K smoke clips do not establish long-duration 4K stability on every GPU. The long synthetic test is 320 x 320, not a reproduction of the reporter's 1080p performance benchmark. Windows is tested; native macOS/Linux builds and Store installation are not tested in this task. No release, tag, push, issue comment or Store submission is performed.
