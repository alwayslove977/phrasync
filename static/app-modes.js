"use strict";

const MODE_COPY = {
  lyric: {
    description: "Turn a song into a kinetic lyric video.",
    source: "Add song", hint: "WAV, MP3, FLAC, M4A…",
    transcribe: "Transcribe song locally", section: "Local song transcription",
    panel: "Lyrics", bulk: "Paste or OCR lyrics", placeholder: "One lyric cue per line…",
    importLabel: "Import lyrics", preview: "Add a song or scrub the timeline to preview",
    render: "Building your lyric video"
  },
  subtitles: {
    description: "Transcribe speech and burn readable subtitles directly into audio or video.",
    source: "Add video or audio", hint: "MP4/WebM · up to 16 GB · long-form video",
    transcribe: "Transcribe media locally", section: "Local speech transcription",
    panel: "Subtitles", bulk: "Paste or import transcript", placeholder: "One subtitle cue per line…",
    importLabel: "Import subtitles", preview: "Add media or scrub the timeline to preview",
    render: "Burning subtitles into your video"
  }
};

const PRESET_LABELS_2D = {
  spiral:"Spiral Flight: orbit into focus", constellation:"Word Constellation: scattered typography",
  "kinetic-slam": "Kinetic Slam: high-impact words",
  "neon-flux": "Neon Flux: blur-to-focus glow",
  "focus-word": "Focus Word: one word at a time",
  cascade: "Cascade: stacked words",
  "wipe-fill": "Wipe Fill: karaoke fill",
  "bold-stack": "Bold Stack: poster",
  minimal: "Minimal Caption"
};

const PRESET_LABELS_3D = {
  spiral:"Spiral Flight: orbit through depth", constellation:"Word Constellation: spatial word field",
  "kinetic-slam": "Monolith: solid impact",
  "neon-flux": "Deep Neon: drifting light",
  "focus-word": "Hero Word: single giant form",
  cascade: "Depth Cascade: stepped layers",
  "wipe-fill": "Spatial Wipe: live colour fill",
  "bold-stack": "Poster Blocks: architectural stack",
  minimal: "Cinema Depth: restrained titles"
};

const PRESET_HINTS_3D = {
  "kinetic-slam": "Heavy word slabs punch forward, planted on the scene floor.",
  "neon-flux": "Words drift laterally through depth with a restrained neon face.",
  "focus-word": "One monumental word at a time travels through the environment.",
  cascade: "Each line occupies its own depth plane and falls into position.",
  "wipe-fill": "A grounded phrase board stays calm while sung words fill in colour.",
  "bold-stack": "Poster-like rows form a physical typographic structure.",
  minimal: "Small cinematic type enters softly and leaves with the world."
};

const BROWSER_VIDEO_FILE = /\.(mp4|webm)$/i;

function isVideoUpload(file) {
  return file.type.startsWith("video/") || /\.(mp4|webm|mov|mkv|avi|m4v)$/i.test(file.name);
}

async function assertBrowserPreviewableVideo(file) {
  if (!BROWSER_VIDEO_FILE.test(file.name)) {
    throw new Error("For reliable browser preview, convert this video to MP4 (H.264/AAC) or WebM first.");
  }
  const url = URL.createObjectURL(file);
  const probe = document.createElement("video");
  probe.preload = "metadata";
  probe.muted = true;
  try {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Video preview check timed out.")), 30000);
      const finish = callback => () => { clearTimeout(timeout); callback(); };
      probe.addEventListener("loadedmetadata", finish(resolve), { once: true });
      probe.addEventListener("error", finish(() => reject(new Error(
        "This browser cannot decode the video. Use MP4 with H.264/AAC or WebM with VP9/Opus."
      ))), { once: true });
      probe.src = url;
      probe.load();
    });
  } finally {
    probe.removeAttribute("src");
    probe.load();
    URL.revokeObjectURL(url);
  }
}

function updatePresetPresentation() {
  const sceneText = project.background.textSpace === "scene";
  const labels = sceneText ? PRESET_LABELS_3D : PRESET_LABELS_2D;
  for (const option of els.stylePreset.options) {
    if (labels[option.value]) option.textContent = labels[option.value];
  }
  els.positionY.disabled = sceneText;
  els.text3dOffsetControls.hidden = !sceneText;
  const positionLabel = els.positionY.closest("label")?.querySelector("span");
  if (positionLabel?.firstChild) {
    const source = sceneText ? "Ground anchored " : "Vertical position ";
    positionLabel.firstChild.nodeValue = typeof t === "function" ? t(source) : source;
  }
  els.positionY.title = sceneText
    ? "3D typography is planted on the world floor. Switch to Flat text for screen positioning."
    : "Position the text vertically in the frame.";
  updatePresetHint();
}

function applyEnvironmentUI() {
  const fullWorld = project.background.type === "dynamic"
    && project.background.visual === "scene3d";
  els.environmentControls.hidden = !fullWorld;
  els.manualEnvironmentControls.hidden = project.background.environmentMode === "auto";
  if (project.background.environmentMode !== "auto") {
    els.environmentResolved.textContent = [
      project.background.season, project.background.daytime, project.background.weather
    ].join(" · ");
  }
}

function applyModeUI() {
  const mode = MODE_COPY[project.mode] ? project.mode : "lyric";
  const copy = MODE_COPY[mode];
  els.root.dataset.projectMode = mode;
  $$('button', els.projectMode).forEach(button =>
    button.classList.toggle("active", button.dataset.value === mode));
  els.modeDescription.textContent = t(copy.description);
  els.audioName.textContent = project.audio?.name || t(copy.source);
  els.audioHint.textContent = t(copy.hint);
  els.audioInput.accept = mode === "subtitles"
    ? "audio/*,video/mp4,video/webm,.wav,.mp3,.m4a,.aac,.flac,.ogg,.opus,.mp4,.webm"
    : "audio/*,.wav,.mp3,.m4a,.aac,.flac,.ogg,.opus";
  els.transcribeButton.textContent = t(copy.transcribe);
  els.transcriptionSectionName.textContent = t(copy.section);
  els.cuePanelTitle.textContent = t(copy.panel);
  els.bulkLyricsLabel.textContent = t(copy.bulk);
  els.bulkLyrics.placeholder = t(copy.placeholder);
  els.lyricsPickTitle.textContent = t(copy.importLabel);
  els.noAudioHint.textContent = t(copy.preview);
  els.renderTitle.textContent = t(copy.render);
}

function resolvedEnvironmentAt(t) {
  const bg = project.background;
  if (bg.environmentMode !== "auto") {
    return {
      weather: bg.weather, daytime: bg.daytime, season: bg.season,
      nextDaytime: bg.daytime, nextSeason: bg.season, dayMix: 0, seasonMix: 0
    };
  }
  const seasons = ["spring", "summer", "autumn", "winter"];
  const times = ["dawn", "day", "sunset", "night"];
  const cycleIndex = (value, length) => ((Math.floor(value) % length) + length) % length;
  const seasonIndex = cycleIndex(t / 24, seasons.length);
  const daytimeIndex = cycleIndex(t / 12, times.length);
  const season = seasons[seasonIndex];
  const daytime = times[daytimeIndex];
  const weatherBySeason = {
    spring: ["clear", "rain", "clear"], summer: ["clear", "clear", "storm"],
    autumn: ["leaves", "fog", "rain"], winter: ["snow", "fog", "clear"]
  };
  const weather = weatherBySeason[season][cycleIndex(t / 8, 3)];
  return {
    weather, daytime, season,
    nextDaytime: times[(daytimeIndex + 1) % times.length],
    nextSeason: seasons[(seasonIndex + 1) % seasons.length],
    dayMix: ((t % 12) + 12) % 12 / 12,
    seasonMix: ((t % 24) + 24) % 24 / 24
  };
}
