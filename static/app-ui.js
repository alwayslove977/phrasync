"use strict";

function toast(message, type = "") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  els.toastStack.append(node);
  setTimeout(() => node.remove(), 4300);
}
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    window.PhrasyncDiagnostics?.record("error", "api", `${options.method || "GET"} ${path} network failure: ${error.name}`);
    throw error;
  }
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    window.PhrasyncDiagnostics?.record("error", "api", `${options.method || "GET"} ${path} returned ${response.status}`);
    const detail = typeof data === "object" ? data.detail || JSON.stringify(data) : data;
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return data;
}

async function uploadAsset(kind, file, onProgress = null) {
  // Send the File directly: multipart would spool and copy a long video twice.
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `/api/assets/${kind}/stream?filename=${encodeURIComponent(file.name)}`);
    request.setRequestHeader("Content-Type", "application/octet-stream");
    request.upload.onprogress = event => {
      if (!event.lengthComputable) return;
      const percent = Math.round(event.loaded / event.total * 100);
      onProgress?.(percent, "upload");
      setAssetStatus(`${window.t("Importing")}: ${file.name} · ${percent}% · ${formatByteCount(event.loaded)} / ${formatByteCount(event.total)}`);
    };
    request.upload.onload = () => { setAssetStatus(window.t("Checking media…")); onProgress?.(100, "checking"); };
    request.onerror = () => reject(new Error(window.t("Import interrupted. Check that Phrasync is still running and try again.")));
    request.onabort = () => reject(new Error(window.t("Import cancelled.")));
    request.onload = () => {
      let data;
      try { data = JSON.parse(request.responseText); }
      catch { reject(new Error(window.t("The local server returned an invalid import response."))); return; }
      if (request.status < 200 || request.status >= 300) reject(new Error(data.detail || `Import failed (${request.status})`));
      else resolve(data);
    };
    request.send(file);
  });
}

function setAssetStatus(message, type = "") {
  els.assetStatus.hidden = !message;
  els.assetStatus.className = `inline-status ${type}`;
  els.assetStatus.textContent = message;
}

function scheduleSave() {
  clearTimeout(saveTimer);
  els.autosaveStatus.textContent = "Saving…";
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
      els.autosaveStatus.textContent = "Autosaved locally";
    } catch {
      els.autosaveStatus.textContent = "Autosave unavailable";
    }
  }, 350);
}

function normalizeCues() {
  project.cues = (project.cues || [])
    .map((cue, index) => ({
      id: cue.id || `cue-${Date.now()}-${index}`,
      start: Math.max(0, Number(cue.start) || 0),
      end: Math.max((Number(cue.start) || 0) + 0.05, Number(cue.end) || (Number(cue.start) || 0) + 2),
      text: String(cue.text || "").trim(),
      words: Array.isArray(cue.words) ? cue.words : [],
      ...(cue.manual === true ? { manual: true } : {})
    }))
    .filter(cue => cue.text)
    .sort((a, b) => a.start - b.start || a.end - b.end);
}

function projectDuration() {
  if (Number(project.timelineDuration) > 0) return Number(project.timelineDuration);
  const cueEnd = Math.max(0, ...project.cues.map(cue => Number(cue.end) || 0));
  const footageEnd = project.background.footageEnabled ? Math.max(0, ...(project.background.clips || []).map(clip => clip.end)) : 0;
  const audioEnd=Number(project.audio?.duration) || 0;
  const videoEnd=project.background.type === "video" ? Number(project.background.videoAsset?.duration) || 0 : 0;
  const mediaEnd = Math.max(audioEnd || cueEnd, videoEnd, footageEnd);
  return Math.max(0.5, mediaEnd || 8);
}

function formatTime(value) {
  value = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  const millis = Math.floor((value % 1) * 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function escapeSrt(text) {
  return String(text || "").replace(/\r/g, "");
}

function formatSrtTime(value) {
  const ms = Math.max(0, Math.round(value * 1000));
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const z = ms % 1000;
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")},${String(z).padStart(3,"0")}`;
}

function downloadBlob(content, filename, type = "application/octet-stream") {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function updateRangeUI(input) {
  const min = Number(input.min || 0);
  const max = Number(input.max || 100);
  const value = Number(input.value);
  const fill = ((value - min) / Math.max(1, max - min)) * 100;
  input.style.setProperty("--range-fill", `${fill}%`);
  const mapping = rangeOutputs[input.id];
  if (mapping) {
    const output = document.getElementById(mapping[0]);
    if (output) output.value = mapping[1](value);
  }
}

function setCanvasDimensions() {
  const aspect = project.canvas.aspect;
  const resolution = Number(els.resolutionSelect.value || 1080);
  if (aspect === "16:9") {
    project.canvas.width = Math.round(resolution * 16 / 9);
    project.canvas.height = resolution;
  } else if (aspect === "9:16") {
    project.canvas.width = resolution;
    project.canvas.height = Math.round(resolution * 16 / 9);
  } else {
    project.canvas.width = resolution;
    project.canvas.height = resolution;
  }
  project.canvas.fps = Number(els.fpsSelect.value || 30);
  els.previewResolution.textContent = `${project.canvas.width} × ${project.canvas.height} · ${project.canvas.fps} fps`;
  els.stage.dataset.aspect = aspect;
  const ratio = project.canvas.width / Math.max(1, project.canvas.height);
  els.stage.style.setProperty("--stage-ar", `${project.canvas.width} / ${project.canvas.height}`);
  els.stage.style.setProperty("--stage-ar-num", ratio.toFixed(4));
  applyStageStyle();
  scheduleSave();
}

function inferResolution() {
  if (project.canvas.aspect === "16:9") return project.canvas.height;
  return project.canvas.width;
}

function applyProjectToControls() {
  normalizeCues();
  els.projectTitle.value = project.title;
  els.audioName.textContent = project.audio?.name || "Add song";
  els.visualSelect.value = project.background.visual;
  els.stylePreset.value = project.style.preset;
  els.fontPreset.value = project.style.fontPreset;
  els.fontPick.textContent = project.style.fontName || "Upload TTF/OTF";
  els.fontSize.value = project.style.fontSize;
  els.topScale.value = Math.round(project.style.topScale * 100);
  els.maxWidth.value = project.style.maxWidth;
  els.positionY.value = project.style.positionY;
  els.offset3DX.value = project.style.offset3DX ?? 0;
  els.offset3DY.value = project.style.offset3DY ?? 0;
  els.lineGap.value = project.style.lineGap;
  els.textColor.value = project.style.textColor;
  els.accentColor.value = project.style.accentColor;
  els.accentColor2.value = project.style.accentColor2;
  els.strokeColor.value = project.style.strokeColor;
  els.animationSelect.value = String(project.style.animation);
  els.uppercaseToggle.checked = project.style.uppercase;
  els.beatReactToggle.checked = project.style.beatReact !== false;
  els.timingOffset.value = Math.round((project.timing.offset || 0) * 1000);
  els.wordLead.value = Math.round((project.style.wordLead ?? 0.06) * 1000);
  els.sceneKit.value = project.background.sceneKit || "japan";
  els.sceneDirection.value = project.background.sceneDirection || "forward";
  els.sceneArtStyle.value = project.background.artStyle || "cinematic";
  els.secondaryMotion.value = project.background.secondaryMotion || "none";
  els.motionAmount.value = Math.round((project.background.motionAmount ?? .35) * 100);
  els.textSpace.value = project.background.textSpace || "flat";
  els.environmentMode.value = project.background.environmentMode || "manual";
  els.weather.value = project.background.weather || "clear";
  els.daytime.value = project.background.daytime || "sunset";
  els.season.value = project.background.season || "summer";
  els.sceneBeat.checked = Boolean(project.background.sceneBeat);
  els.sceneWave.checked = Boolean(project.background.sceneWave);
  els.waveControls.hidden = !project.background.sceneWave;
  els.waveColor.value = project.background.waveColor || "#4de2ff";
  els.waveIntensity.value = Math.round((project.background.waveIntensity ?? 1) * 100);
  els.sceneSpeed.value = Math.round((project.background.sceneSpeed ?? 1) * 100);
  els.sceneDensity.value = Math.round((project.background.sceneDensity ?? 1) * 100);
  els.snapWindow.value = String(project.timing.snapWindow);
  els.snapStrength.value = String(project.timing.snapStrength);
  els.snapPhrasesToggle.checked = Boolean(project.timing.snapPhrases);
  $$("button", els.snapMode).forEach(button =>
    button.classList.toggle("active", button.dataset.value === project.timing.snapMode));
  els.strokeWidth.value = project.style.strokeWidth;
  els.shadow.value = project.style.shadow;
  els.shade.value = Math.round(project.background.shade * 100);
  els.visualIntensity.value = Math.round(project.background.visualIntensity * 100);
  els.grain.value = Math.round(project.background.grain * 100);
  els.motion.value = Math.round(project.background.motion * 100);
  els.blur.value = project.background.blur;
  els.backgroundColor.value = project.background.backgroundColor;
  els.secondaryColor.value = project.background.secondaryColor;
  els.aspectSelect.value = project.canvas.aspect;
  els.resolutionSelect.value = String(inferResolution());
  if (![...els.resolutionSelect.options].some(option => option.value === els.resolutionSelect.value)) {
    els.resolutionSelect.value = "1080";
  }
  els.fpsSelect.value = String(project.canvas.fps);
  els.qualitySelect.value = String(project.export.crf);
  els.rateControlSelect.value = project.export.bitrateMbps != null ? "bitrate" : "auto";
  els.bitrateInput.value = String(project.export.bitrateMbps ?? 50);
  els.bitrateField.hidden = els.rateControlSelect.value !== "bitrate";
  els.qualitySelect.disabled = !els.bitrateField.hidden;
  $$("input[type=range]").forEach(updateRangeUI);
  applyBackgroundTypeUI();
  applyModeUI();
  applyEnvironmentUI();
  applyOceanUI();
  updatePresetPresentation();
  applyBackgroundPreview();
  applyAudioPreview();
  applyStageStyle();
  renderCueList();
  updateDurationUI();
  updatePresetHint();
  updateSyncSummary();
  updateWordLabel();
  refreshFootageControls();
}

function updatePresetHint() {
  const spec = window.VFKinetic.PRESETS[project.style.preset];
  els.presetHint.textContent = project.background.textSpace === "scene"
    ? (PRESET_HINTS_3D[project.style.preset] || "Grounded 3D typography in world space.")
    : (spec ? spec.description : "");
}

function applyAudioPreview() {
  if (project.audio?.url) {
    if (els.audioPlayer.src !== new URL(project.audio.url, location.href).href) {
      els.audioPlayer.src = project.audio.url;
      els.audioPlayer.load();
    }
    els.noAudioHint.hidden = true;
  } else {
    els.audioPlayer.removeAttribute("src");
    els.audioPlayer.load();
    els.noAudioHint.hidden = false;
  }
}

async function saveTextFile(content, filename, extension, type = "text/plain") {
  if (IS_DESKTOP_HOST) {
    const bridge = window.pywebview?.api;
    if (!bridge?.save_text_file) throw new Error("Desktop file dialogs are not ready. Please try again.");
    return await bridge.save_text_file(content, filename, extension);
  }
  if (window.showSaveFilePicker) {
    let handle;
    try {
      handle = await window.showSaveFilePicker({ suggestedName: filename,
        types: [{ description: extension.toUpperCase(), accept: { [type]: [`.${extension}`] } }] });
    } catch (error) { if (error.name === "AbortError") return null; throw error; }
    const stream = await handle.createWritable();
    await stream.write(content); await stream.close();
    return handle.name;
  }
  downloadBlob(content, filename, type);
  return "browser download";
}
let lastMediaErrorAt = 0;
function reportMediaPreviewError(media, label) {
  if (!media.currentSrc || Date.now() - lastMediaErrorAt < 600) return;
  lastMediaErrorAt = Date.now();
  const detail = media.error?.message ? ` (${media.error.message})` : "";
  const message = `${label} cannot be decoded by this browser${detail}. Convert it to MP4 (H.264/AAC) or WebM.`;
  setAssetStatus(message, "error");
  toast(message, "error");
}

function activeBackgroundAsset(type = project.background.type) {
  if (type === "image") return project.background.imageAsset;
  if (type === "video") return project.background.videoAsset;
  return null;
}

function applyBackgroundTypeUI() {
  applyTextOrientation();
  $$("button", els.backgroundType).forEach(button => button.classList.toggle("active", button.dataset.value === project.background.type));
  const dynamic = project.background.type === "dynamic";
  els.dynamicControls.hidden = !dynamic;
  els.backgroundUploadWrap.hidden = dynamic;
  els.sceneControls.hidden = !(
    (dynamic && ["scene", "scene3d"].includes(project.background.visual))
      || project.background.textSpace === "scene");
  $("#sceneArtControls").hidden = !((dynamic && project.background.visual === "scene3d")
    || project.background.textSpace === "scene");
  applyEnvironmentUI();
  applyOceanUI();
  if (!dynamic) {
    const isImage = project.background.type === "image";
    els.backgroundInput.accept = isImage ? "image/*,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff" : "video/mp4,video/webm,.mp4,.webm";
    els.backgroundHint.textContent = isImage ? "PNG, JPG, WEBP" : "MP4 (H.264/AAC) or WebM";
    const asset = activeBackgroundAsset();
    els.backgroundName.textContent = asset?.name || `Choose ${project.background.type}`;
  }
}

function applyBackgroundPreview() {
  const type = project.background.type;
  els.backgroundImage.hidden = type !== "image";
  els.backgroundVideo.hidden = type !== "video";
  if (type === "image") {
    const asset = project.background.imageAsset;
    if (asset?.url) els.backgroundImage.src = asset.url;
  } else if (type === "video") {
    const asset = project.background.videoAsset;
    if (asset?.url && els.backgroundVideo.src !== new URL(asset.url, location.href).href) {
      els.backgroundVideo.src = asset.url;
      els.backgroundVideo.load();
    }
  }
  applyBackgroundTypeUI();
}

const fontStacks = {
  impact: 'Impact, Haettenschweiler, "Arial Narrow Bold", "Arial Narrow", sans-serif',
  condensed: '"Arial Narrow Bold", "Arial Narrow", "Roboto Condensed", sans-serif',
  modern: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  serif: 'Georgia, "Times New Roman", serif',
  mono: 'Consolas, Menlo, "DejaVu Sans Mono", monospace',
  bebas: '"Bebas Neue", "Bebas Kai", Anton, Oswald, "DIN Condensed", Impact, sans-serif',
  geometric: 'Montserrat, Poppins, Futura, "Century Gothic", "Segoe UI", "Arial Black", sans-serif',
  rounded: 'Poppins, Quicksand, Nunito, "Varela Round", "Century Gothic", sans-serif',
  poster: 'Nexa, "SF UI Display", "Segoe UI", "Segoe UI Black", "Arial Black", Helvetica, sans-serif',
  techno: '"DIN Pro Cond", "DIN Pro", "DIN Condensed", Bahnschrift, Oswald, "Roboto Condensed", sans-serif',
  script: '"Segoe Script", "Bradley Hand", Noteworthy, Caveat, "Brush Script MT", cursive',
  jgothic: '"Yu Gothic", "Yu Gothic UI", "Hiragino Sans", "Noto Sans JP", "Microsoft YaHei", sans-serif'
};

function applyStageStyle() {
  const rect = els.stage.getBoundingClientRect();
  // Short edge: the preview must scale type the way the exporter does.
  const scale = rect.height ? Math.min(rect.width, rect.height) / 1080 : 0.5;
  const style = project.style;
  const bg = project.background;
  els.stage.style.setProperty("--lyric-size", `${Math.max(18, style.fontSize * scale)}px`);
  els.stage.style.setProperty("--top-size", `${Math.max(12, style.fontSize * style.topScale * scale)}px`);
  els.stage.style.setProperty("--lyric-max-width", `${style.maxWidth}%`);
  els.stage.style.setProperty("--lyric-y", `${style.positionY}%`);
  els.stage.style.setProperty("--lyric-gap", `${style.lineGap * scale}px`);
  els.stage.style.setProperty("--lyric-text", style.textColor);
  els.stage.style.setProperty("--lyric-accent", style.accentColor);
  els.stage.style.setProperty("--lyric-accent2", style.accentColor2);
  els.stage.style.setProperty("--lyric-stroke", style.strokeColor);
  els.stage.style.setProperty("--lyric-stroke-width", `${Math.max(0, style.strokeWidth * scale)}px`);
  els.stage.style.setProperty("--lyric-shadow", `0 ${style.shadow * scale * .75}px ${style.shadow * scale * 2.1}px rgba(0,0,0,.72)`);
  els.stage.style.setProperty("--stage-font", lyricFontStack(style));
  applyCustomFont();
  els.stage.style.setProperty("--shade-opacity", bg.shade);
  els.stage.style.setProperty("--grain-opacity", bg.grain);
  els.stage.style.setProperty("--background-blur", `${bg.blur * scale}px`);
  els.stage.style.setProperty("--background-zoom", `${1 + bg.motion * 0.02}`);
  els.safeArea.hidden = !els.safeAreaToggle.checked;
  renderLyric(true);
}
