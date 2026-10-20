# Phrasync 0.4.8 release verification

Verified on Windows on 20 October 2026. The user approved the local desktop build before publication.

## Automated and interactive checks

The complete regression suite passed: 232 tests. Coverage includes standard and Enhanced LRC, CJK syllable timing shared by Python and browser playback, custom-font validation and reuse, native folder selection, cancellation, manual fallback, existing desktop dialogs, and real 2D/3D WebGL exports with IN/OUT ranges.

Interactive checks confirmed font changes in preview, repeated upload without a new duplicate, saved-font selection, and a completed MP4 containing the Chinese character 词. Browser folder selection opened the real Windows folder dialog; cancellation retained the previous folder. A subsequent export wrote its file into the selected destination.

## Compiled Windows candidate

The standalone executable reported version 0.4.8. Its served typography, import, font and export scripts matched the source files by hash. Enhanced LRC import retained Chinese syllable timestamps, and repeated Unicode-named font uploads returned the same asset ID.

Four real MP4 exports passed postflight checks with a custom Latin font and system/bundled CJK fallbacks: Simplified Chinese, Traditional Chinese, Japanese and Korean.

The Windows SDK package builder validated the 0.4.8.0 x64 MSIX successfully. Package SHA-256:

`6585DDE13A1AD107BFE029AA2EA10635A9EF0DDAD76395A8A22B9FE5B84D9204`

## Limits

No real Mac was available. Shared source fixes include macOS discovery/fallback paths, but macOS runtime behavior still needs confirmation from a user on that platform. Fonts must cover the requested glyphs; not every CJK font covers every script or character.

The 0.4.7 updater changes remain included. A real Microsoft Store 0.4.7 to 0.4.8 installation can only be checked after Store approval and rollout; this report does not claim that test has happened.

The new creative suggestions and transparent export remain in the separate feature backlog. Credit Crawl is not integrated in this release.
