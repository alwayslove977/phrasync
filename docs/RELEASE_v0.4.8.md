# Phrasync 0.4.8

This maintenance release focuses on reliable lyric imports, custom fonts and video exports with Chinese, Japanese and Korean text. Thank you to alwayslove977 for the detailed report and investigation in [issue #3](https://github.com/jaydemks/phrasync/issues/3).

## Timed lyrics

Enhanced LRC imports now understand word and syllable timestamps inside a line, using angle or square brackets. Millisecond timing, repeated line timestamps, offsets and explicit final boundaries are supported. Chinese and other unspaced lyrics retain their individual timed segments in both playback and export.

Importing a timed file no longer starts an unsolicited auto-alignment that could change its supplied timing. Plain-text imports still align automatically, and Auto-align remains available when you want it. Enhanced LRC export preserves real word boundaries without inventing word timestamps for untimed lines. Empty imports do not replace the current lyrics.

## Fonts and CJK export

Custom fonts are validated when uploaded. Unicode filenames are retained, repeated identical new uploads reuse the same asset, and saved or locally discovered fonts can be selected again. Compatible custom fonts now appear in the preview as well as the export. A dedicated control returns to the preset font.

The fallback search now checks installed, bundled, local and uploaded fonts rather than a short Japanese-only list. Preflight reports missing custom fonts or required CJK glyph coverage before rendering, with clearer errors. A suitable font must still be available on your machine. The existing bundled Japanese font is not a guarantee that every Chinese or Korean character is covered.

## Workflow

The local browser edition can open a native export-folder chooser through the running local app when supported. Cancellation keeps the previous destination, repeated clicks cannot open duplicate helper dialogs, and manual path entry remains available. The Windows desktop edition retains its existing native dialog.

The editor now explains that importing lyrics replaces the current cues, including the English demo, and offers a confirmed Clear all lyrics action.

## Verification and platform notes

232 automated tests passed on Windows. Validation includes real CJK MP4 exports, custom-font handling, Enhanced LRC preview/export timing parity, and real WebGL exports with 2D/3D text and IN/OUT ranges. Native folder selection and cancellation were also checked in the local browser, followed by an export into the selected folder.

These shared source changes also apply to the macOS code paths, including system font discovery and fallback. We do not have a Mac available to verify them. If a macOS problem remains, please open a new issue with the app version, a minimal reproduction and a reviewed Diagnostics report.

Particle text dissolution, transparent video export and the other proposed creative features are not part of this release. They are recorded in the [feature backlog](https://github.com/jaydemks/phrasync/blob/main/docs/FEATURE_BACKLOG.md). Credit Crawl remains a separate contribution awaiting its author's PR.

Phrasync remains free, with local media processing. [GitHub v0.4.8](https://github.com/jaydemks/phrasync/releases/tag/v0.4.8) provides source code. The [Microsoft Store](https://apps.microsoft.com/detail/9NF9JBG2PKHX) is the Windows installer channel; availability of 0.4.8 follows certification and rollout. The previous approved Store version remains available until then.

Full history: [RELEASE_NOTES.md](https://github.com/jaydemks/phrasync/blob/main/RELEASE_NOTES.md).
