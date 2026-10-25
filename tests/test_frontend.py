from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
APP_SCRIPTS = [
    "diagnostics.js",
    "i18n.js",
    "i18n-dom.js",
    "app-state.js",
    "app-modes.js",
    "app-ocean.js",
    "app-text-orientation.js",
    "app-ui.js",
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
    "app-fonts.js",
    "app.js",
]


def test_frontend_fragments_are_ordered_once_and_stay_focused():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    positions = []
    for name in APP_SCRIPTS:
        tag = f'<script src="/static/{name}" defer></script>'
        assert html.count(tag) == 1, name
        positions.append(html.index(tag))
        assert len((STATIC / name).read_text(encoding="utf-8").splitlines()) <= 400, name
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


def test_interface_defaults_to_english_and_offers_persistent_chinese_toggle():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")
    dom = (STATIC / "i18n-dom.js").read_text(encoding="utf-8")
    zh = (STATIC / "i18n-zh.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")

    assert '<html lang="en"' in html
    assert 'id="languageToggle"' in html
    assert 'id="onboardingLanguageToggle"' in html
    assert 'id="onboardingDialog"' in html
    assert "Your first transcription downloads an AI model" in html
    # The dictionary must be registered before the engine reads it, and the DOM
    # half runs last because it needs both.
    dictionary_tag = html.index('src="/static/i18n-zh.js"')
    engine_tag = html.index('src="/static/i18n.js"')
    dom_tag = html.index('src="/static/i18n-dom.js"')
    assert dictionary_tag < engine_tag < dom_tag
    assert "window.PHRASYNC_I18N = {" in zh
    assert '"zh-CN": {' in zh
    assert '"File": "文件"' in zh
    assert "const DICTIONARIES = window.PHRASYNC_I18N || {};" in i18n
    assert 'code: "zh-CN"' in i18n and 'code: "en"' in i18n
    assert 'const LANGUAGE_KEY = "phrasync.language"' in i18n
    assert 'currentLanguage = "en"' in i18n
    # The language state has one declaration and one writer: the engine owns
    # both, and the DOM half can only go through setCurrentLanguage().
    assert i18n.count("let currentLanguage") == 1
    assert "currentLanguage = " not in dom
    assert "setCurrentLanguage(" in dom
    # The toggle flips between exactly the two supported languages and the choice persists.
    assert 'currentLanguage === "zh-CN" ? "en" : "zh-CN"' in dom
    assert "localStorage.setItem(LANGUAGE_KEY, next)" in dom
    assert "setCurrentLanguage(preferredLanguage())" in dom
    # The Italian dictionary is gone, not shadowed by a leftover branch.
    assert "Inizia a creare" not in i18n and "Inizia a creare" not in zh
    assert 'code: "it"' not in i18n
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


def test_custom_font_selector_keeps_its_contract():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    fonts_js = STATIC / "app-fonts.js"
    assert fonts_js.read_text(encoding="utf-8").splitlines()[0] == '"use strict";'
    probe = """
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

function makeElement(tag) {
  const el = {
    tagName: tag.toUpperCase(), dataset: {}, children: [], options: [],
    value: "", textContent: "", title: "", label: "", handlers: {}, clicks: 0,
    addEventListener(type, handler) { el.handlers[type] = handler; },
    appendChild(node) {
      el.children.push(node);
      if (node.tagName === "OPTGROUP") el.options.push(...node.children);
      return node;
    },
    querySelectorAll() { return []; },
    click() { el.clicks += 1; }
  };
  return el;
}

const added = [];
const fetchCalls = [];
const sandbox = {
  console: console,
  els: {
    fontPreset: makeElement("select"),
    fontPick: makeElement("button"),
    fontInput: makeElement("input")
  },
  project: { style: { fontPath: "Demo.ttf" } },
  stageCalls: 0,
  saveCalls: 0,
  applyStageStyle() { sandbox.stageCalls += 1; },
  scheduleSave() { sandbox.saveCalls += 1; },
  handleFontFile() {},
  fetch: async (url, init) => {
    fetchCalls.push([url, init]);
    return { ok: true, json: async () => ({ fonts: [{ filename: "Demo.ttf", name: "Demo Font" }] }) };
  },
  FontFace: class FontFace {
    constructor(family, src) { this.family = family; this.src = src; }
    async load() { return this; }
  },
  document: {
    createElement: tag => makeElement(tag),
    fonts: { add(face) { added.push(face); } }
  }
};
sandbox.window = sandbox;
vm.runInContext(fs.readFileSync(process.env.PHRASYNC_FONTS_JS, "utf8"), vm.createContext(sandbox));

(async () => {
  assert.equal(typeof sandbox.loadCustomFonts, "function", "loadCustomFonts() must stay global");
  assert.equal(typeof sandbox.bindFontControls, "function", "bindFontControls() must be exposed");

  const select = sandbox.els.fontPreset;
  sandbox.bindFontControls();
  sandbox.els.fontPick.handlers.click();
  assert.equal(sandbox.els.fontInput.clicks, 1, "the font button must still open the file dialog");

  await sandbox.loadCustomFonts();

  assert.deepEqual(fetchCalls[0], ["/api/fonts", { cache: "no-store" }]);
  const group = select.children[0];
  assert.equal(group.tagName, "OPTGROUP");
  assert.equal(group.label, "Custom fonts · ~/phrasync/fonts");
  const option = group.children[0];
  assert.equal(option.value, "custom:Demo.ttf");
  assert.equal(option.textContent, "Demo Font");
  assert.equal(option.title, "Demo.ttf");
  assert.equal(option.dataset.customFont, "true");
  assert.equal(option.dataset.fontPath, "Demo.ttf");
  assert.equal(option.dataset.fontFamily, '"PhrasyncCustomFont0"');
  assert.equal(added.length, 1, "the preview face must be registered once");
  assert.equal(added[0].family, "PhrasyncCustomFont0");
  assert.equal(added[0].src, 'url("/api/fonts/file/Demo.ttf")');
  assert.equal(select.value, "custom:Demo.ttf", "a saved style.fontPath must be re-selected");

  select.selectedOptions = [option];
  select.handlers.change();
  assert.equal(sandbox.project.style.fontPath, "Demo.ttf");
  assert.equal(sandbox.stageCalls, 1);
  assert.equal(sandbox.saveCalls, 1);

  select.selectedOptions = [makeElement("option")];
  select.handlers.change();
  assert.equal("fontPath" in sandbox.project.style, false, "a preset must clear style.fontPath");
  assert.equal(sandbox.saveCalls, 2);
})().catch(error => { console.error(error.message); process.exit(1); });
"""
    result = subprocess.run(
        [node, "-"], input=probe, capture_output=True, text=True,
        encoding="utf-8", timeout=30,
        env={**os.environ, "PHRASYNC_FONTS_JS": str(fonts_js)},
    )
    assert result.returncode == 0, result.stderr
