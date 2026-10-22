<p align="center"><img src="docs/media/phrasync-mark.svg" alt="Phrasync" width="76"></p>

# Phrasync

Phrasync is a free, local studio for lyric videos and subtitles. Bring in a song or video, transcribe it on your computer, correct the words and their timing, choose how it looks, and export an MP4. Your media is not uploaded to a Phrasync service.

Created by [jaydemks](https://github.com/jaydemks).

## Watch Phrasync in action

https://github.com/user-attachments/assets/9ec2387b-2c79-4257-980f-3e578a12f39b

![Phrasync editor with preview, lyric cues and timeline](docs/media/editor-overview.png)

## What you can make

**Lyric videos:** Import a song, transcribe vocals locally or paste/import your own lyrics, then arrange phrases and individual words against the waveform. Choose kinetic 2D text or 3D text that moves through the scene. Use a still image, looping video, reactive background, or an Odyssey 3D world. The worlds include Japan, Italy, China, the United States, and **Lost in the Ocean**, with camera movement, time of day, weather, and art-direction controls.

**Subtitled videos:** Import video or audio, generate editable captions, and burn them into an MP4. A video can serve as the transcription source, preview picture, and final video/audio source in one workflow. The import and audio-analysis path supports long-form projects and files up to 16 GB; actual processing and export time depend on your hardware, codec, and available disk space. Browser preview works most reliably with MP4 (H.264/AAC) or WebM.

In both modes you can:

- Correct text, add or remove cues, and adjust word and phrase timing with dragging, snapping, nudging, tap sync, and auto-align. Manually added lines remain visible even when they overlap a transcription (fixed in 0.4.4).
- Build an edit from a media bin: drag images, videos and built-in 2D/3D visuals onto up to four background tracks. Move, trim, split or duplicate clips, adjust opacity and transitions, and animate pan/zoom. Right-click a clip for quick controls; unused tracks can be removed without deleting your source media.
- Add black-and-white, gradients, particles and an audio-reactive spectrum; trigger shake, pendulum motion, flashes, zoom drops and light pulses from beats or detected transients. Spiral Flight and Word Constellation work with both 2D and 3D text. Flash effects are optional and can affect photosensitive viewers.
- Set export IN/OUT with **I/O**, draggable timeline markers or exact seconds to render just a section. Timeline length follows your media automatically or can be set manually. Zoom stays at the playhead; middle-mouse dragging and the scrollbar let you move around.
- Use local Faster-Whisper transcription, automatic language detection, and optional NVIDIA CUDA acceleration. The interface is in English by default, with an Italian toggle.
- Import lyrics or captions, including Enhanced LRC with word or syllable timestamps, extract text from an image with OCR, and export SRT, WebVTT, LRC, word-level LRC, and ASS karaoke. Timed imports keep their supplied timing unless you explicitly choose Auto-align.
- Upload and reuse custom fonts, see compatible fonts in preview as well as export, and use installed or uploaded fonts as fallbacks for Chinese, Japanese and Korean characters. Missing coverage is reported before rendering.
- Preview your work, save and reload a local project, run the preflight check, and export H.264 MP4. The Windows app provides native render-folder selection; the local browser edition can also open a native folder picker when its Python/Tk environment supports it, with manual path entry as a fallback. The Windows app can open the chosen or default render folder afterward.
- Use **File → New / Load / Save** with Windows file dialogs and keyboard shortcuts. Choose the destination for subtitle exports too. MP4 export requires a chosen folder, writes one named file, and supports a custom bitrate such as 150 Mbps; a compatibility encoder helps with 4K when the browser codec is unavailable.
- Open **Diagnostics** to inspect errors and relevant Windows/hardware details before sharing a support report.

The editor, timeline, and first-run explanation are shown here:

| Preview | Timeline | First run |
| --- | --- | --- |
| ![Lyric preview](docs/media/kinetic-preview.png) | ![Timing timeline](docs/media/timeline-editor.png) | ![Model download explanation](docs/media/first-run.png) |

**0.4.9** improves Microsoft Store update results, adds real update progress and a startup notification, and verifies the running package after relaunch. A specific download fault gets one refreshed retry; canceled updates are never retried automatically. It also improves spacing in the welcome dialog. The 0.4.8 Enhanced LRC, custom-font and CJK fixes and the earlier export improvements remain included. Windows validation includes 246 automated tests. The [release notes](RELEASE_NOTES.md) cover the changes; proposed creative additions are tracked separately in the [feature backlog](docs/FEATURE_BACKLOG.md). macOS code paths have not been verified on a real Mac.

## Get Phrasync

**Microsoft Store:** [Install the free Windows app](https://apps.microsoft.com/detail/9NF9JBG2PKHX). The Store build packages the same local editor in a dedicated window with Windows file dialogs and an in-app update check. GitHub and Store releases use the same version line. The matching 0.4.9.0 package was submitted for certification on October 22, 2026, with automatic publication after approval. Until rollout completes the previous approved version remains available. Check the listing for the version currently offered.

**GitHub source:** The current source release is [v0.4.9](https://github.com/jaydemks/phrasync/releases/tag/v0.4.9). On Windows, install [Python 3.11 or 3.12](https://www.python.org/downloads/) with its `py` launcher, clone or download the repository, and run `run_windows.bat`. The first launch installs dependencies. For the same editor in your local browser, run `.venv\Scripts\python.exe app.py --external-browser` after setup. The GitHub release has source code, not a ready-to-install Windows package. Linux and macOS launch scripts are included but are not release-tested like Windows.

Phrasync began as a local browser editor. The Windows app is a more convenient way to install and use it; both modes share the same code and local engine. You can modify the open-source project and run your changes in either mode. You cannot directly edit the installed Store package.

If you have a Store installation older than 0.4.3, back up important projects and reinstall once; this clears stale app data that could leave controls unresponsive after an in-place update. **Settings → App updates** checks for later versions. If an older in-app updater cannot install, update through Microsoft Store itself; this updater defect does not inherently require uninstalling. A real 0.4.7 to 0.4.8 Store update succeeded after retrying in Microsoft Store. The new 0.4.9 recovery and restart flow still requires confirmation with a subsequent Store upgrade.

## First run and practical limits

The first transcription downloads the selected speech model to your computer. Phrasync shows its progress, size, and estimated time remaining; later uses of that model work from the local copy. Internet access is needed to install dependencies and download a new model, not to upload your media. Smaller models run with less memory; a compatible NVIDIA GPU speeds up transcription, while CPU mode also works. MP4 rendering, particularly long or high-resolution video, can still take substantial time and disk space.

Automatic transcription and alignment are starting points, not a replacement for listening and checking the result—especially with expressive singing, effects, or mixed languages. Saved project files refer to local media rather than embedding every source file, so move the media too if you move a project to another computer.

To run the automated tests from a Windows source checkout, use `scripts/run_tests_windows.bat`.

## License

Phrasync is open source under [Apache-2.0](LICENSE). Preserve [NOTICE](NOTICE) and applicable [third-party notices](THIRD_PARTY_NOTICES.md) when redistributing it. Videos you create remain yours, subject to your rights in the music, lyrics, footage, images, and fonts you use.
