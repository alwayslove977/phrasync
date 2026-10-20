from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


def test_browser_and_desktop_export_folder_controller():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    result = subprocess.run([node, str(ROOT / "tests/browser_export_folder_ui.cjs")],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
APP_SCRIPTS = [
    "diagnostics.js",
    "i18n.js",
    "app-state.js",
    "app-modes.js",
    "app-ocean.js",
    "app-text-orientation.js",
    "app-ui.js",
    "app-fonts.js",
    "app-lyrics.js",
    "app-visuals.js",
    "media-effects.js",
    "visual-clips.js",
    "app-footage.js",
    "app-media-bin.js",
    "app-editor-tools.js",
    "app-visual-tracks.js",
    "app-loop.js",
    "app-cues.js",
    "app-workflows.js",
    "app-render.js",
    "store-updates.js",
    "app-timeline.js",
    "app-export-range.js",
    "app.js",
]


def test_frontend_fragments_are_ordered_once_and_stay_focused():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    positions = []
    for name in APP_SCRIPTS:
        tag = f'<script src="/static/{name}" defer></script>'
        assert html.count(tag) == 1, name
        positions.append(html.index(tag))
        limit = 450 if name == "i18n.js" else 400  # the translation dictionary grows with UI copy
        assert len((STATIC / name).read_text(encoding="utf-8").splitlines()) <= limit, name
    assert positions == sorted(positions)


def test_frontend_fragments_compile_as_one_classic_script_scope():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    source = "\n".join((STATIC / name).read_text(encoding="utf-8") for name in APP_SCRIPTS)
    result = subprocess.run(
        [node, "--check", "-"],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_3d_lyric_world_motion_is_linear_and_passes_camera():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    scene = (STATIC / "scene3d.js").read_text(encoding="utf-8")
    probe = """
global.window = global;
%s
const speed = 2;
const end = 4;
const samples = [-0.6, 0, end, end + 3.5].map(t =>
  VFScene.lyricBoardDistance(end, t, speed, 8));
if (VFScene.lyricBoardZ(end, speed, 8) !== -16) process.exit(1);
if (samples.join(',') !== '17.2,16,8,1') process.exit(2);
""" % scene
    result = subprocess.run(
        [node, "-"], input=probe, capture_output=True, text=True,
        encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_3d_mode_is_not_coupled_to_background_or_canvas_visibility():
    visuals = (STATIC / "app-visuals.js").read_text(encoding="utf-8")
    loop = (STATIC / "app-loop.js").read_text(encoding="utf-8")
    lyrics = (STATIC / "app-lyrics.js").read_text(encoding="utf-8")
    ui = (STATIC / "app-ui.js").read_text(encoding="utf-8")

    lyric_mode = visuals[visuals.index("function lyric3DEnabled"):
                         visuals.index("function glLayerNeeded")]
    assert "textSpace === \"scene\"" in lyric_mode
    assert ".hidden" not in lyric_mode
    assert "prepareWebGLOverlay(time)" in visuals
    assert "project.background.type === \"dynamic\"" in loop
    assert "prepareWebGLOverlay(time)" in loop
    assert loop.index("drawDynamicVisual(now)") < loop.index("updatePlaybackUI(time)")
    assert loop.index("updatePlaybackUI(time)") < loop.index("glScene?.render()")

    assert "return lyric3DEnabled();" in lyrics
    assert "clearLyric();" in lyrics
    assert "preset3D(spec, true)" in lyrics
    assert "|| project.background.textSpace === \"scene\"" in ui


def test_project_modes_and_environment_controls_are_wired():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    state = (STATIC / "app-state.js").read_text(encoding="utf-8")
    modes = (STATIC / "app-modes.js").read_text(encoding="utf-8")
    workflow = (STATIC / "app-workflows.js").read_text(encoding="utf-8")
    scene = (STATIC / "scene3d-gl.js").read_text(encoding="utf-8")

    for element_id in (
        "projectMode", "environmentMode", "weather", "daytime", "season",
        "environmentResolved", "text3dOffsetControls", "offset3DX", "offset3DY",
    ):
        assert f'id="{element_id}"' in html
        assert f'$("#{element_id}")' in state
    assert 'mode: "lyric"' in state
    assert 'mode === "subtitles"' in workflow
    assert 'uploadAsset(kind, file)' in workflow
    assert 'video/mp4' in modes and 'video/webm' in modes
    assert 'PRESET_LABELS_3D' in modes
    assert 'resolvedEnvironmentAt(t)' in modes
    assert 'from "/static/scene3d-environment.js"' in scene
    assert "const groundClearance = 0.32" in scene
    assert "style.offset3DX" in scene and "style.offset3DY" in scene
    assert "cam.x + slot.x" not in scene


def test_interface_defaults_to_english_and_offers_persistent_italian_toggle():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")

    assert '<html lang="en"' in html
    assert 'id="languageToggle"' in html
    assert 'id="onboardingLanguageToggle"' in html
    assert 'id="onboardingDialog"' in html
    assert "Your first transcription downloads an AI model" in html
    assert 'const LANGUAGE_KEY = "phrasync.language"' in i18n
    assert 'currentLanguage = "en"' in i18n
    assert '"Start creating": "Inizia a creare"' in i18n
    assert "initI18n();" in app


def test_transcription_progress_formats_model_download_size_and_eta():
    workflow = (STATIC / "app-workflows.js").read_text(encoding="utf-8")
    i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")
    assert "formatTranscriptionJob(job)" in workflow
    assert 'job?.phase === "model-download"' in i18n
    assert "job.downloaded_bytes" in i18n
    assert "job.total_bytes" in i18n
    assert "job.eta_seconds" in i18n


def test_desktop_preview_limits_expensive_idle_work():
    state = (STATIC / "app-state.js").read_text(encoding="utf-8")
    visuals = (STATIC / "app-visuals.js").read_text(encoding="utf-8")
    loop = (STATIC / "app-loop.js").read_text(encoding="utf-8")
    timeline = (STATIC / "timeline.js").read_text(encoding="utf-8")
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")

    assert 'get("desktop") === "1"' in state
    assert "1000 / 60" in loop and "1000 / 12" in loop
    assert "document.hidden" in loop
    assert "if (playing || timeline?._lastPaintTime !== lyricTime()) timeline?.tick();" in loop
    assert "this._lastPaintTime = playhead" in timeline
    assert "IS_DESKTOP_HOST ? 1" in visuals
    assert "IS_DESKTOP_HOST ? 1" in timeline
    assert ".desktop-host .topbar" in styles
    assert "backdrop-filter: none" in styles
