"use strict";

function bindControls() {
  els.projectTitle.addEventListener("input", () => { project.title = els.projectTitle.value; scheduleSave(); });
  $$("button", els.projectMode).forEach(button => button.addEventListener("click", () => {
    project.mode = button.dataset.value;
    applyModeUI(); scheduleSave();
  }));
  els.themeToggle.addEventListener("click", () => {
    const theme = els.root.dataset.theme === "dark" ? "light" : "dark";
    els.root.dataset.theme = theme; localStorage.setItem(THEME_KEY, theme);
    timeline?.refreshTheme();
  });
  els.criticButton.addEventListener("click", runCritic);
  els.renderButton.addEventListener("click", openRenderDialog);
  els.audioPick.addEventListener("click", () => els.audioInput.click());
  els.audioInput.addEventListener("change", () => handleAudioFile(els.audioInput.files[0]));
  els.backgroundPick.addEventListener("click", () => els.backgroundInput.click());
  els.backgroundInput.addEventListener("change", () => handleBackgroundFile(els.backgroundInput.files[0]));
  els.ocrPick.addEventListener("click", () => els.ocrInput.click());
  els.ocrInput.addEventListener("change", () => handleOCRFile(els.ocrInput.files[0]));
  els.lyricsPick.addEventListener("click", () => els.lyricsInput.click());
  els.lyricsInput.addEventListener("change", () => handleLyricsFile(els.lyricsInput.files[0]));
  bindFontControls();
  els.transcribeButton.addEventListener("click", () => transcribeSong());
  els.cancelTranscription.addEventListener("click", stopTranscription);

  $$("button", els.backgroundType).forEach(button => button.addEventListener("click", () => {
    project.background.type = button.dataset.value;
    project.background.footageEnabled = false;
    refreshFootageControls();
    const asset = activeBackgroundAsset(project.background.type);
    project.background.assetId = asset?.id || null;
    project.background.url = asset?.url || null;
    project.background.name = asset?.name || null;
    applyBackgroundPreview(); scheduleSave();
  }));
  const sceneBindings = [
    [els.sceneKit, "sceneKit", value => value],
    [els.sceneDirection, "sceneDirection", value => value],
    [els.sceneArtStyle, "artStyle", value => value],
    [els.secondaryMotion, "secondaryMotion", value => value],
    [els.motionAmount, "motionAmount", value => Number(value) / 100],
    [els.textSpace, "textSpace", value => value],
    [els.environmentMode, "environmentMode", value => value],
    [els.weather, "weather", value => value],
    [els.daytime, "daytime", value => value],
    [els.season, "season", value => value],
    [els.sceneSpeed, "sceneSpeed", value => Number(value) / 100],
    [els.sceneDensity, "sceneDensity", value => Number(value) / 100],
    [els.waveColor, "waveColor", value => value],
    [els.waveIntensity, "waveIntensity", value => Number(value) / 100]
  ];
  for (const [element, key, convert] of sceneBindings) {
    element.addEventListener("input", () => {
      project.background[key] = convert(element.value);
      if (element.type === "range") updateRangeUI(element);
      if ([els.environmentMode, els.weather, els.daytime, els.season].includes(element)) {
        applyEnvironmentUI();
      }
      scheduleSave();
    });
  }
  els.textSpace.addEventListener("change", () => {
    project.background.textSpace = els.textSpace.value;
    applyTextOrientation();
    updatePresetPresentation(); restartLyricAnimation(); scheduleSave();
  });
  els.sceneBeat.addEventListener("change", () => {
    project.background.sceneBeat = els.sceneBeat.checked;
    scheduleSave();
  });
  els.sceneWave.addEventListener("change", () => {
    project.background.sceneWave = els.sceneWave.checked;
    els.waveControls.hidden = !els.sceneWave.checked;
    scheduleSave();
  });
  els.sceneReseed.addEventListener("click", () => {
    project.background.sceneSeed = Math.floor(Math.random() * 100000) + 1;
    scheduleSave();
    toast("World regenerated.");
  });

  els.visualSelect.addEventListener("change", () => { project.background.visual = els.visualSelect.value; scheduleSave(); });
  els.visualSelect.addEventListener("change", applyBackgroundTypeUI);

  const styleBindings = [
    [els.stylePreset, "preset", value => value],
    [els.fontPreset, "fontPreset", value => value],
    [els.fontSize, "fontSize", Number],
    [els.topScale, "topScale", value => Number(value) / 100],
    [els.maxWidth, "maxWidth", Number],
    [els.positionY, "positionY", Number],
    [els.offset3DX, "offset3DX", Number],
    [els.offset3DY, "offset3DY", Number],
    [els.lineGap, "lineGap", Number],
    [els.textColor, "textColor", value => value],
    [els.accentColor, "accentColor", value => value],
    [els.accentColor2, "accentColor2", value => value],
    [els.strokeColor, "strokeColor", value => value],
    [els.animationSelect, "animation", Number],
    [els.strokeWidth, "strokeWidth", Number],
    [els.shadow, "shadow", Number]
  ];
  for (const [element, key, convert] of styleBindings) {
    element.addEventListener("input", () => {
      project.style[key] = convert(element.value);
      if (element.type === "range") updateRangeUI(element);
      applyStageStyle(); scheduleSave();
    });
  }
  els.uppercaseToggle.addEventListener("change", () => { project.style.uppercase = els.uppercaseToggle.checked; restartLyricAnimation(); scheduleSave(); });
  els.beatReactToggle.addEventListener("change", () => { project.style.beatReact = els.beatReactToggle.checked; scheduleSave(); });
  els.stylePreset.addEventListener("change", () => {
    // Set it here too: "change" can arrive without the generic "input" binding
    // having run, and the preset drives the whole layout.
    project.style.preset = els.stylePreset.value;
    updatePresetHint(); restartLyricAnimation(); scheduleSave();
  });

  els.analyzeButton.addEventListener("click", () => ensureAnalysis(true));
  els.autoAlignButton.addEventListener("click", runAutoAlign);
  els.timingOffset.addEventListener("input", () => {
    project.timing.offset = Number(els.timingOffset.value) / 1000;
    updateRangeUI(els.timingOffset);
    restartLyricAnimation(); scheduleSave();
  });
  els.wordLead.addEventListener("input", () => {
    project.style.wordLead = Number(els.wordLead.value) / 1000;
    updateRangeUI(els.wordLead);
    restartLyricAnimation(); scheduleSave();
  });
  els.snapWindow.addEventListener("change", () => { project.timing.snapWindow = Number(els.snapWindow.value); scheduleSave(); });
  els.snapStrength.addEventListener("change", () => { project.timing.snapStrength = Number(els.snapStrength.value); scheduleSave(); });
  els.snapPhrasesToggle.addEventListener("change", () => { project.timing.snapPhrases = els.snapPhrasesToggle.checked; scheduleSave(); });

  els.wordBack.addEventListener("click", () => nudgeWord(-0.02));
  els.wordForward.addEventListener("click", () => nudgeWord(0.02));
  els.tapSyncButton.addEventListener("click", toggleTapSync);
  els.splitCueButton.addEventListener("click", splitCueAtPlayhead);
  els.clearWordsButton.addEventListener("click", resetCueWords);

  const backgroundBindings = [
    [els.shade, "shade", value => Number(value) / 100],
    [els.visualIntensity, "visualIntensity", value => Number(value) / 100],
    [els.grain, "grain", value => Number(value) / 100],
    [els.motion, "motion", value => Number(value) / 100],
    [els.blur, "blur", Number],
    [els.backgroundColor, "backgroundColor", value => value],
    [els.secondaryColor, "secondaryColor", value => value]
  ];
  for (const [element, key, convert] of backgroundBindings) {
    element.addEventListener("input", () => {
      project.background[key] = convert(element.value);
      if (element.type === "range") updateRangeUI(element);
      applyStageStyle(); scheduleSave();
    });
  }

  els.aspectSelect.addEventListener("change", () => { project.canvas.aspect = els.aspectSelect.value; setCanvasDimensions(); });
  els.resolutionSelect.addEventListener("change", setCanvasDimensions);
  els.fpsSelect.addEventListener("change", setCanvasDimensions);
  els.qualitySelect.addEventListener("change", () => { project.export.crf = Number(els.qualitySelect.value); scheduleSave(); });
  const updateBitrate = () => {
    const custom = els.rateControlSelect.value === "bitrate";
    els.bitrateField.hidden = !custom; els.qualitySelect.disabled = custom;
    project.export.bitrateMbps = custom ? Number(els.bitrateInput.value) : null;
    scheduleSave();
  };
  els.rateControlSelect.addEventListener("change", updateBitrate);
  els.bitrateInput.addEventListener("input", updateBitrate);
  els.safeAreaToggle.addEventListener("change", applyStageStyle);

  els.playButton.addEventListener("click", togglePlay);
  els.audioPlayer.addEventListener("play", updatePlayButton);
  els.audioPlayer.addEventListener("pause", updatePlayButton);
  els.audioPlayer.addEventListener("ended", updatePlayButton);
  els.audioPlayer.addEventListener("error", () => reportMediaPreviewError(els.audioPlayer, "Source media"));
  els.backgroundVideo.addEventListener("error", () => reportMediaPreviewError(els.backgroundVideo, "Background video"));
  els.audioPlayer.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(els.audioPlayer.duration)) {
      project.audio.duration = els.audioPlayer.duration;
      project.duration = els.audioPlayer.duration;
      updateDurationUI(); scheduleSave();
    }
  });
  els.seekBar.addEventListener("input", () => seekTo(els.seekBar.value));
  els.volumeSlider.addEventListener("input", () => { els.audioPlayer.volume = Number(els.volumeSlider.value); updateRangeUI(els.volumeSlider); });
  els.muteButton.addEventListener("click", () => {
    els.audioPlayer.muted = !els.audioPlayer.muted;
    els.muteButton.textContent = els.audioPlayer.muted ? "○" : "◕";
  });
  els.restartAnimation.addEventListener("click", restartLyricAnimation);
  els.fullscreenButton.addEventListener("click", () => els.stage.requestFullscreen?.());

  els.appendBulkButton.addEventListener("click", () => createCuesFromLines(els.bulkLyrics.value.split(/\r?\n/), false));
  els.replaceBulkButton.addEventListener("click", () => createCuesFromLines(els.bulkLyrics.value.split(/\r?\n/), true));
  els.addCueButton.addEventListener("click", () => {
    const start = Math.max(0, lyricTime());
    const cue = { id: `cue-${crypto.randomUUID()}`, start, end: start + 2.5, text: "NEW LYRIC", words: [], manual: true };
    project.cues.push(cue); selectedCueId = cue.id; renderCueList({ preservePage: true }); updateDurationUI(); scheduleSave();
  });
  els.sortCuesButton.addEventListener("click", () => { normalizeCues(); renderCueList(); scheduleSave(); });
  els.nudgeBackButton.addEventListener("click", () => nudgeSelected(-.1));
  els.nudgeForwardButton.addEventListener("click", () => nudgeSelected(.1));
  els.exportSrtButton.addEventListener("click", async () => {
    // The server owns every format so the export matches what the renderer
    // knows, including the per-word timing that SRT alone cannot carry.
    const format = els.exportFormat.value;
    const extension = format === "elrc" ? "lrc" : format;
    try {
      const body = await api(`/api/lyrics/export/${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cues: project.cues, style: project.style, canvas: project.canvas })
      });
      const path = await saveTextFile(body, `${safeFilename(project.title)}.${extension}`, extension);
      if (path) toast(`Exported ${format.toUpperCase()}: ${path}`, "success");
    } catch (error) {
      toast(`Export failed: ${error.message}`, "error");
    }
  });

  const loadProject = async content => {
      const loaded = migrateProject(JSON.parse(content));
      els.audioPlayer.pause(); project = loaded;
      analysis = null; analysisPending = false; selectedWordIndex = 0; tapArmed = false; tapQueue = [];
      selectedCueId = project.cues[0]?.id || null;
      applyProjectToControls();
  loadCustomFonts(); updateSyncSummary(); timeline?.fitAll(); seekTo(0); scheduleSave();
      toast("Project loaded. Media links refer to this local Phrasync workspace.", "success");
      if (project.audioAssetId) ensureAnalysis();
  };
  els.loadProjectButton.addEventListener("click", async () => {
    if (!IS_DESKTOP_HOST) return els.projectInput.click();
    try {
      const bridge = window.pywebview?.api;
      if (!bridge?.load_project_file) throw new Error("Desktop file dialogs are not ready. Please try again.");
      const file = await bridge.load_project_file();
      if (file) await loadProject(file.content);
    } catch (error) { toast(`Could not load project: ${error.message}`, "error"); }
  });
  els.projectInput.addEventListener("change", async () => {
    const file = els.projectInput.files[0];
    if (!file) return;
    try {
      await loadProject(await file.text());
    } catch (error) { toast(`Invalid project: ${error.message}`, "error"); }
    finally { els.projectInput.value = ""; }
  });
  els.saveProjectButton.addEventListener("click", async () => {
    try {
      const path = await saveTextFile(JSON.stringify(project, null, 2), `${safeFilename(project.title)}.phrasync.json`, "json", "application/json");
      if (path) toast(`Project saved: ${path}`, "success");
    } catch (error) { toast(`Could not save project: ${error.message}`, "error"); }
  });
  els.resetProjectButton.addEventListener("click", () => {
    if (!confirm(t("Create a new project? Save your current project first to keep it."))) return;
    els.audioPlayer.pause(); analysis = null; analysisPending = false; selectedFootageId = null;
    selectedWordIndex = 0; tapArmed = false; tapQueue = [];
    project = clone(DEFAULT_PROJECT); selectedCueId = project.cues[0].id; currentCueId = null;
    localStorage.removeItem(STORAGE_KEY); applyProjectToControls(); updateSyncSummary(); timeline?.fitAll(); seekTo(0); scheduleSave(); toast("Project reset.");
  });

  els.renderClose.addEventListener("click", () => els.renderDialog.close());
  els.chooseRenderDirectory.addEventListener("click", chooseRenderDirectory);
  els.openRenderDirectory.addEventListener("click", openRenderDirectory);
  els.openDefaultRenderDirectory.addEventListener("click", openDefaultRenderDirectory);
  els.confirmRender.addEventListener("click", startRender);
  els.downloadRender.addEventListener("click", downloadRender);
  els.cancelRender.addEventListener("click", cancelRender);
  window.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); openRenderDialog(); }
    if (event.target.matches("input,textarea,select")) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") {
      event.preventDefault(); duplicateCue(); return;
    }
    if (event.code === "Space" && !event.target.matches("button")) { event.preventDefault(); togglePlay(); }
    // Tap sync only listens once it is armed, so T stays free otherwise.
    if (tapArmed && (event.key === "t" || event.key === "T")) { event.preventDefault(); handleTap(); }
    if (event.key === "ArrowLeft" && event.shiftKey) { event.preventDefault(); nudgeWord(-0.02); }
    if (event.key === "ArrowRight" && event.shiftKey) { event.preventDefault(); nudgeWord(0.02); }
    if (event.key === "ArrowLeft" && !event.shiftKey) { event.preventDefault(); seekTo(currentPlaybackTime() - (event.altKey ? 0.05 : 1)); }
    if (event.key === "ArrowRight" && !event.shiftKey) { event.preventDefault(); seekTo(currentPlaybackTime() + (event.altKey ? 0.05 : 1)); }
    if (event.key === "w" || event.key === "W") { selectWordAtPlayhead(); }
    if ((event.key === "s" || event.key === "S") && !event.ctrlKey && !event.metaKey) {
      event.preventDefault(); splitCueAtPlayhead();
    }
  });
  new ResizeObserver(applyStageStyle).observe(els.stage);
}

function safeFilename(value) {
  return String(value || "phrasync_project").replace(/[^a-z0-9_-]+/gi, "_").replace(/^_+|_+$/g, "").slice(0, 70) || "phrasync_project";
}

function initTheme() {
  els.root.dataset.theme = localStorage.getItem(THEME_KEY) || localStorage.getItem(LEGACY_THEME_KEY) || "dark";
}

async function shutdownServer() {
  if (!confirm("Save the current project and stop Phrasync?")) return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
  try {
    const response = await fetch("/api/shutdown", { method: "POST" });
    if (!response.ok) throw new Error(await response.text());
    document.body.innerHTML = '<main class="shutdown-screen"><h1>Phrasync stopped.</h1><p>You can close this tab. Port released.</p></main>';
  } catch (error) {
    toast(`Could not stop Phrasync: ${error.message}`, "error");
  }
}

function showHfTokenStatus(status) {
  els.hfTokenStatus.textContent = status.configured
    ? `${status.masked} · ${status.source === "environment" ? "environment variable" : "saved locally"}`
    : "Not configured";
  els.hfTokenStatus.classList.toggle("configured", Boolean(status.configured));
  els.hfTokenRemove.disabled = !status.canRemove;
}

async function openSettings() {
  els.hfTokenInput.value = "";
  els.hfTokenInput.type = "password";
  els.hfTokenReveal.textContent = "Show";
  try {
    const result = await api("/api/settings");
    document.getElementById("aboutVersion").textContent = `${t("Version")} ${result.version || "0.4.5"}`;
    showHfTokenStatus(result.huggingFace);
    if (!els.settingsDialog.open) els.settingsDialog.showModal();
  } catch (error) {
    toast(`Could not load settings: ${error.message}`, "error");
  }
}

async function saveHfToken() {
  const token = els.hfTokenInput.value.trim();
  if (!token) { toast("Enter a Hugging Face token first.", "error"); return; }
  try {
    els.hfTokenSave.disabled = true;
    const result = await api("/api/settings/hugging-face", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token })
    });
    els.hfTokenInput.value = "";
    showHfTokenStatus(result.huggingFace);
    toast("Hugging Face token saved locally.", "success");
  } catch (error) {
    toast(`Could not save token: ${error.message}`, "error");
  } finally {
    els.hfTokenSave.disabled = false;
  }
}

async function removeHfToken() {
  if (!confirm("Remove the saved Hugging Face token from this computer?")) return;
  try {
    const result = await api("/api/settings/hugging-face", { method: "DELETE" });
    showHfTokenStatus(result.huggingFace);
    toast("Saved Hugging Face token removed.");
  } catch (error) {
    toast(`Could not remove token: ${error.message}`, "error");
  }
}

function init() {
  initI18n();
  initTheme();
  setupTimeline();
  bindControls();
  initOceanControls();
  initTextOrientation();
  initFootage();
  initEditorTools();
  applyProjectToControls();
  loadCustomFonts();
  els.audioPlayer.volume = Number(els.volumeSlider.value);
  updateRangeUI(els.volumeSlider);
  checkHealth();
  els.settingsButton.addEventListener("click", openSettings);
  els.hfTokenSave.addEventListener("click", saveHfToken);
  els.hfTokenRemove.addEventListener("click", removeHfToken);
  els.hfTokenReveal.addEventListener("click", () => {
    const reveal = els.hfTokenInput.type === "password";
    els.hfTokenInput.type = reveal ? "text" : "password";
    els.hfTokenReveal.textContent = reveal ? "Hide" : "Show";
  });
  els.shutdownButton.addEventListener("click", shutdownServer);
  document.addEventListener("phrasync-language-change", () => {
    applyModeUI();
    checkHealth();
    if (currentTranscriptionJob) pollTranscription();
  });
  if (project.audioAssetId) ensureAnalysis();
  requestAnimationFrame(animationLoop);
  window.PhrasyncDiagnostics?.record("info", "frontend", "Editor controls initialized");
}

init();
