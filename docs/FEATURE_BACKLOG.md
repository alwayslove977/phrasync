# Phrasync — Community feature backlog

Collected on 20 October 2026, while 0.4.8 is being tested locally.

This is a planning document, not a release announcement. None of the items below
is promised for a particular version. Check the current implementation before
starting: an existing effect or control does not necessarily cover the requested
workflow. Keep preview, export and saved projects consistent, and retain the
free, local-first experience.

## At a glance

| ID | Request | Suggested by | Status |
| --- | --- | --- | --- |
| F01 | Particle dissolve / text disintegration | alwayslove977 | Proposed |
| F02 | Transparent lyric-video export | alwayslove977 | Pipeline investigation needed |
| F03 | Song-structure-aware effect intensity | impaler | Analysis and interaction design needed |
| F04 | Independent effects for each clip | impaler | Proposed |
| F05 | Adjustable, bottom-anchored spectrum placement | impaler | Proposed |
| F06 | Drag-and-drop timeline transitions | impaler | Proposed |
| F07 | Magnetic clip-edge snapping enabled by default | impaler | Existing behavior needs review |
| F08 | Optional stock-footage search and import | impaler | Provider/terms investigation needed |

## alwayslove977

Source: [GitHub issue #3](https://github.com/jaydemks/phrasync/issues/3),
sections 4 and 5. The issue describes use on macOS.

### F01 — Particle dissolve / text disintegration

Lyric text breaks into particles and gradually disperses, rather than merely
fading. This is a **text effect**, not the existing background particle overlay.

Requested controls:

- Particle size and density.
- Dispersion direction and speed.
- Dissolve duration.
- Randomness and particle distribution.
- When the dissolve happens relative to the lyric animation.

Acceptance checks: deterministic playback when seeking; matching preview/export;
readable text before dissolution; correct CJK/custom-font glyph shapes; sensible
particle limits and resource cleanup. Decide explicitly whether the first version
supports 2D text, 3D text, or both; label any limitation.

### F02 — Transparent lyric-video export

Export animated lyrics with an alpha channel so they can be composited over
footage in another editor, without a baked-in solid background.

The user suggested **QuickTime MOV / ProRes 4444**, subject to pipeline support.
Treat this as a candidate to investigate, not an already supported format or a
guarantee about every downstream editor.

Acceptance checks: real transparency, not a black background; preserved soft
edges, shadows and glows; correct alpha handling throughout 2D/WebGL composition
and encoding; documented codec/format and editor compatibility; correct IN/OUT,
frame rate and destination behavior. Existing opaque MP4 export must not change.

## impaler — Producer and editor workflow

Source: producer feedback supplied by Giò in this chat on 20 October 2026.
These requests extend the existing beat/transient effects and timeline tools;
they do not imply those tools are absent.

### F03 — Song-structure-aware effect intensity

Full-length music videos need a different intensity during an intro, quiet verse,
buildup, chorus and drop. A constant BPM-triggered shake is useful for a short
reel, but should not hit equally hard throughout a three- or four-minute song.

Explore section detection and/or an audio-energy envelope to scale shake,
pendulum, flashes, pulses and related effects. **Energy estimation is not the
same as reliably identifying a verse or drop.** Keep that distinction clear in
the UI and provide manual overrides when analysis is uncertain.

Acceptance checks: quiet/loud section contrast, smooth transitions, repeatable
seeking and IN/OUT export, cached local analysis, intensity limits, and no new
preview stalls. Preserve the existing simple beat/transient mode as an option.

Dependency: define clip-local effect controls (F04) first, so automatic intensity
can be adjusted or overridden without affecting unrelated clips.

### F04 — Independent effects for each clip

Changing effect settings for one footage clip should not unintentionally change
every other clip. Let creators build tension manually with different settings
across an edit, including stacked clips.

Design the relationship between project-wide defaults and clip-local overrides.
Make the inspector's editing scope explicit; do not silently reinterpret old
projects that currently use shared settings.

Acceptance checks: two clips retain different values in preview and export;
trim/split/duplicate behavior is defined; settings survive save/load; existing
projects keep their previous appearance. This is not a claim that keyframes or
full automation lanes have already been requested or implemented.

### F05 — Spectrum vertical position and stable bottom anchoring

Add a vertical-position slider for the reactive spectrum, including placement
at the very bottom edge. Audio intensity should animate the spectrum's shape
without unexpectedly lifting its baseline into the picture.

Acceptance checks: stable baseline at quiet and loud moments; intuitive units or
normalized positioning; correct placement for landscape, portrait and square
canvases; intentional edge clipping/margins; save/load and preview/export parity.

### F06 — Drag-and-drop transitions

Provide visible transition presets that can be dragged onto the overlap/join
between two footage clips. Make the target and transition duration clear to a
beginner instead of relying only on numeric clip settings.

Acceptance checks: visible drop feedback, adjustable duration, removal/replacement,
and defined behavior for gaps, short clips and stacked tracks. Do not silently
overwrite source frames or break existing fade/transition settings. Test seeking,
split/trim, save/load and export through transition boundaries.

### F07 — Magnetic clip-edge snapping on by default

Footage clip edges should naturally snap together during dragging and trimming,
helping users avoid unintended gaps or overlaps.

Review current snapping first: beat/onset snapping alone is not the requested
clip-to-clip behavior. Define target priority and a zoom-aware snap tolerance.
Provide a clear toggle or temporary bypass for deliberate gaps and overlaps.

Acceptance checks: adjacent clips, multiple tracks, zoom levels, trim handles and
existing modifier shortcuts. Intentional overlaps must remain possible for F06;
snapping must not silently modify unrelated clips or existing project timing.

### F08 — Optional stock-footage search and import

Explore an optional media-bin search for **Pexels and/or Pixabay**. A creator could
search for a topic such as “rainy city”, preview a result, download it into the
local media bin, and place it on the timeline.

Before implementation, verify the chosen provider's current API access, key
requirements, rate limits, licensing, attribution and redistribution terms.
Do not assume that a free API or downloadable clip grants unrestricted reuse.

Acceptance checks: explicit network/download actions, no upload of the user's
media, provider/source and license information, download progress/cancel/retry,
disk-space handling, duplicate handling and selectable source quality. Downloaded
assets must remain usable in saved projects offline. Existing local workflows
must not require an account or an internet connection because of this feature.

Decide whether results enter the bin first or are placed on a user-selected track;
do not overwrite a timeline clip simply because a download finished.

## Suggested planning order — not a commitment

1. Review F07 snapping and scope F05 spectrum placement as focused workflow work.
2. Define F04 clip-local effects and backward-compatible project storage.
3. Design F06 transitions and their interaction with intentional overlaps.
4. Prototype F03 energy/structure-aware automation on top of explicit controls.
5. Investigate F01 particle typography and F02 alpha export separately; both need
   rendering/performance validation before release commitments.
6. Evaluate F08 as an optional online add-on after provider and licensing review.

For each accepted feature, record an owner, target version, implementation status,
tests and user acceptance here. Start with a local build; publishing remains a
separate decision by Giò.

## Scope boundaries

- LRC parsing, font handling and CJK export failures are maintenance work for
  0.4.8, not future features in this backlog. See [local validation](LOCAL_048_TEST_REPORT.md).
- Issue #3 section 6 also asks for clearer subtitle-import/edit/export scope.
  The 0.4.8 work clarifies replacement of the English demo and adds Clear all
  lyrics. Revisit clarity with the reporter if needed; do not infer a request
  for a new multi-language subtitle-track engine from that question alone.
- Credit Crawl is a separate contribution awaiting its author's PR:
  [issue #4](https://github.com/jaydemks/phrasync/issues/4). It is not part of the
  requests above and should be reviewed independently.
