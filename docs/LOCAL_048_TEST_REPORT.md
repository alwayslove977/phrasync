# Phrasync 0.4.8 — local validation

Date: 2026-10-20. This records prepublication local validation. Giò approved release preparation after manual acceptance; final distribution status is recorded in the release notes.

## Result

The complete Python/Node regression suite passed: **232 tests**, including actual FFmpeg MP4 exports and two real Chromium/WebGL exports. One existing dependency deprecation warning remains (Starlette/httpx).

Test data was isolated under `qa_out/048-tests` and `qa_out/048-ui`, not the user's normal projects/uploads. Existing personal working-tree files were left unchanged.

## Coverage

- Standard and Enhanced LRC: angle and inline square word tags, unspaced Chinese syllables, millisecond and colon-fraction precision, UTF-8 BOM, metadata, positive/negative offsets, repeated line timestamps, blank boundaries, explicit final-word end, invalid backward timing, and enhanced export/import round trips.
- Python/browser kinetic parity for imported CJK syllables and word-fill values. Stored syllable timing no longer disappears because whitespace token counts differ.
- Timed imports no longer trigger an unsolicited realignment. Plain-text imports retain automatic alignment. Empty imports are rejected before replacing current lyrics.
- Font validation and SHA-256 reuse through stream, multipart and path-based ingestion; Unicode names retained. Corrupt files rejected without leaving temporary imports. Existing historical duplicate assets are not deleted.
- Saved/local font library discovery, opaque font selection IDs, file serving and project-bound font IDs. Fonts can be placed in the workspace's `fonts` folder, `~/phrasync/fonts`, or the repository's `fonts` folder.
- Real fallback glyph coverage and decodable MP4 exports for Simplified Chinese, Traditional Chinese, Japanese and Korean using fonts available on the Windows test machine.
- Fallback search beyond the Japanese preset shortlist; actionable missing-character errors. Preflight flags missing custom fonts and CJK coverage failures.
- Two real WebGL exports: custom uploaded font, Japanese per-character LRC, flat/3D text over a 3D background, and a nonzero IN/OUT range. Both generated the expected six frames and decoded successfully.
- Live UI: multilingual import replaces English demo, custom font applies in preview, persists across reload, can be selected from saved fonts or reset to a preset. Clear-all cancellation preserves cues; confirmation removes them. No browser console errors observed during these checks.
- Local browser export destination: Choose folder opens the native OS picker through a loopback/same-origin endpoint. Confirmed a real Windows folder selection and cancellation through the browser; cancellation retained the prior path. A one-second 1080p30 CJK MP4 was rendered directly into the selected test folder (5.0 seconds elapsed).
- Picker tests cover Unicode/spaced paths, invalid folders, timeout/error cleanup, unsupported environments, duplicate-dialog prevention, loopback/origin/Host checks, manual fallback, no-folder render guard, and the unchanged desktop bridge. The UI disables export while a picker is pending.

## Remaining verification / not included

- **No real macOS runtime was available.** The macOS font-discovery paths and broader fallback address the reported design problem, but must be verified on the reporter's Mac before closing the issue.
- No access to the reporter's exact failing project or custom font. Request those if their reproduction still fails.
- CJK fallback requires an installed, bundled or uploaded font covering the requested characters. Only the existing Japanese font is bundled; no new font downloads were added.
- A valid TTC/font file can still be unsupported by a particular browser. The UI reports this rather than claiming an exact preview; WebGL export requires a browser-compatible custom font. Pillow's 2D export remains able to use supported TTC fonts.
- Browser native folder selection uses the local Python/Tk helper when no desktop bridge is attached. If Tk/a graphical session is unavailable, manual path entry remains available. The frozen desktop edition continues to use pywebview; no subprocess interpreter mode is attempted for a frozen executable.
- Particle-dissolve animation and transparent/alpha video output are separate feature requests, not implemented in this maintenance work.
- Credit Crawl is excluded pending the author's pull request.

## Manual acceptance

1. Import the user's real standard/enhanced LRC and verify word highlighting without pressing Auto-align.
2. Upload the intended Chinese/custom font twice, select it from the saved-font list, save/reload the project and compare preview with MP4.
3. Test the original failing Chinese export on macOS, with and without the uploaded font.
4. Check Clear all lyrics (cancel and confirm), explicit preset reset, normal export and a short nonzero IN/OUT range.
5. Local release approval was given by Giò on 20 October 2026. The reporter's macOS result is still unconfirmed; do not present Windows validation as a real Mac test.
