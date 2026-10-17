# 0.4.6 local export checks — October 12, 2026

Local candidate only. No GitHub push, tag, release or Microsoft Store submission.

## Reproduction and fix

Preflight treated any non-dynamic base as unknown when footage was enabled. Image and video are now recognised in that mode; source/clip validation remains active.

The export browser previously forced SwiftShader. Effects/custom bitrate also transported PNG/base64 frames, and flat lyrics required decoding and encoding the video a second time. The candidate selects graphics normally, uses a bounded authenticated loopback raw-frame bridge, composites existing PIL typography before encoding and retains intermediate timestamps for final audio muxing. Batches contain at most eight frame instructions; each pixel frame is acknowledged before the next is produced.

## Results

- 183 automated tests pass, including preflight combinations, bitrate validation, 4K compatibility encoding, cancellation cleanup and loopback bridge rejection of wrong origins/tokens/sizes.
- Source and fresh Windows executable each passed a 13-case real-export matrix: one 1080p30 effects benchmark plus dynamic/image/video bases × flat/spatial lyrics × full/nonzero-IN/OUT export. Each mixed project contains video, image and ocean-3D tracks, transitions, particles, gradient, shake and spectrum, with source audio.
- Real exports at 12/23/24/25/30/50/60 fps decoded with the expected frame counts. Output frames and durations were checked, not just renderer return values.
- Real 3840×2160 ocean export passed with browser H.264 support disabled.
- Custom 150 Mbps export measured 142.5 Mbps over a short two-second sample (including VBV startup), retaining the existing bitrate controls.
- Explicit software-graphics fallback rendered and decoded successfully.
- Sampled frames were inspected for the 4K ocean scene; mixed exports were checked for nonblack pixels and dimensions.

## Performance and limits

On this machine (RTX 3090), the same 2-second 1080p30 effects project took 36.656 seconds before changes and 8.704 seconds in the fresh Windows candidate: about 4.2× faster. A final 10-second source benchmark took 22.390 seconds. Settings and visual effects were retained; no frames were skipped.

These figures include browser startup and are specific to the test project/hardware. Export is still slower than realtime on the measured 10-second sample; complex footage seeks, typography and quality encoding have costs. Do not advertise universally realtime export.

The newly reported user's slow-render log/project was not attached to the current request. The Downloads log is from 0.4.4; the user's exact complex project has not been reproduced.

Generated results and videos are under `qa_out/render-046`, which is not a release asset. The candidate executable is `release/v0.4.6/dist/Phrasync/Phrasync.exe`. User project/media files and the existing 0.4.5 release are retained.
