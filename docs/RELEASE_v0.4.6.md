# Phrasync 0.4.6 — Export reliability and speed

This maintenance update focuses on unblocking mixed-footage exports and removing unnecessary rendering work.

- Fixed **Unknown background type: video** (and the corresponding image case) when footage tracks are enabled. Invalid or missing sources still fail validation.
- Hardware graphics can now be selected by the export browser, instead of forcing software graphics. Software fallback remains available.
- Removed the per-frame PNG/base64 round trip from the FFmpeg compatibility path. Frames stream locally with bounded memory; no frames are skipped.
- Flat lyrics are composited before video encoding, avoiding a second decode/encode pass while retaining the existing typography and font handling.
- Preserved intermediate frame timestamps for audio muxing and IN/OUT exports.
- Added export graphics and encoding-throughput information to local support logs.

**Local benchmark:** the same two-second 1080p30 effects project fell from **36.7 to 8.7 seconds** in the Windows candidate (about **4.2× faster**). A ten-second sample took 22.4 seconds. Performance depends on the project and hardware; this is not a promise of realtime export.

Verification includes 183 automated tests, source and packaged mixed-track export matrices with flat/spatial text and full/ranged exports, real frame-count checks at 12/23/24/25/30/50/60 fps, 4K codec fallback, custom bitrate and software-graphics fallback.

Still free, with local media processing. The [Microsoft Store](https://apps.microsoft.com/detail/9NF9JBG2PKHX) is the Windows installer channel. This GitHub release contains source code, not a separate installer; see the [README](https://github.com/jaydemks/phrasync/blob/main/README.md) for browser and desktop launch instructions.

GitHub and Store use the same version line. The matching 0.4.6.0 Store package was submitted for certification on October 17, 2026; the previous Store build remains available until certification and rollout complete.

Full history: [RELEASE_NOTES.md](https://github.com/jaydemks/phrasync/blob/main/RELEASE_NOTES.md).
