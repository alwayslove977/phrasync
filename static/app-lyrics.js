"use strict";

/* ------------------------------------------------------------------ *
 * Kinetic lyric engine (mirrors phrasync/kinetic.py)
 * ------------------------------------------------------------------ */

const K = () => window.VFKinetic;

function activePreset() {
  return K().resolvedPreset(project.style);
}
// Playback clock shifted by the user's global sync offset.
function lyricTime(time = currentPlaybackTime()) {
  return time - (project.timing?.offset || 0);
}
function beatValue(time) {
  if (!analysis || !project.style.beatReact) return 0;
  return K().beatPulse(time, analysis.bpm, analysis.beatOffset);
}

function cueSignature(cue, spec) {
  if (!cue) return "";
  const words = K().cueWords(cue);
  return [
    cue.id, spec.layout, project.style.uppercase ? "u" : "l",
    project.style.fontSize, project.style.maxWidth, project.style.fontPreset, project.style.fontAssetId,
    words.map(word => `${word.text}@${word.start.toFixed(3)}-${word.end.toFixed(3)}`).join("|")
  ].join("::");
}

function restartLyricAnimation() {
  for (const entry of lyricCues.values()) entry.root.remove();
  lyricCues.clear();
  window.VFSceneGL?.get(els.glCanvas)?.clearLyric();
  renderLyric(true);
}

/** Build the DOM for one cue. Per-frame work only touches inline styles. */
function buildCueDOM(cue, spec, signature) {
  const root = document.createElement("div");
  root.className = "lyric-cue";
  const nodes = [];

  const words = K().cueWords(cue);
  const upper = project.style.uppercase;
  const lines = K().layoutLines(words, spec, K().charBudget(project.style, project.canvas, spec));

  lines.forEach((line, lineIndex) => {
    const lineNode = document.createElement("div");
    lineNode.className = "lyric-line";
    const lead = spec.layout === "stack" && lineIndex === 0 && lines.length > 1;
    if (lead) lineNode.dataset.role = "lead";
    if (spec.layout === "focus" && line[0]) {
      lineNode.style.setProperty("--focus-scale", K().focusScale(line[0].text));
    }
    for (const word of line) {
      const text = upper ? word.text.toUpperCase() : word.text;
      const wordNode = document.createElement("span");
      wordNode.className = "lyric-word";
      const base = document.createElement("span");
      base.className = "lw-base";
      base.textContent = text;
      const fill = document.createElement("span");
      fill.className = "lw-fill";
      fill.textContent = text;
      fill.setAttribute("aria-hidden", "true");
      wordNode.append(base, fill);
      lineNode.append(wordNode);
      nodes.push({
        el: wordNode, word, lead,
        lineIndex, lineCount: lines.length, lineKey: `${cue.id}#${lineIndex}`
      });
    }
    root.append(lineNode);
  });

  els.lyricDisplay.append(root);
  return { cue, root, nodes, signature };
}

/**
 * Sync the DOM with whichever cues are on screen. Two cues coexist during a
 * phrase change so the outgoing phrase dissolves under the incoming one
 * instead of cutting.
 */
function renderLyric(force = false) {
  const spec = activePreset();
  const time = lyricTime();
  const active = K().activeCues(project.cues, time, lyricIsIn3D() ? preset3D(spec, true) : spec);

  if (force || els.lyricDisplay.dataset.preset !== project.style.preset) {
    els.lyricDisplay.className = "lyric-display";
    els.lyricDisplay.dataset.preset = project.style.preset;
    els.lyricDisplay.dataset.layout = spec.layout;
    els.lyricDisplay.dataset.case = project.style.uppercase ? "upper" : (spec.caseTransform || "none");
    els.lyricDisplay.style.setProperty("--word-gap", `${spec.wordGap}em`);
    els.lyricDisplay.style.setProperty("--line-h", spec.lineHeight);
  }

  const wanted = new Set(active.map(cue => cue.id));
  for (const [id, entry] of [...lyricCues]) {
    if (!wanted.has(id)) {
      entry.root.remove();
      lyricCues.delete(id);
    }
  }
  for (const cue of active) {
    const signature = cueSignature(cue, spec);
    const existing = lyricCues.get(cue.id);
    if (existing && existing.signature === signature) continue;
    if (existing) existing.root.remove();
    lyricCues.set(cue.id, buildCueDOM(cue, spec, signature));
  }

  const primary = active.find(cue => time >= cue.start && time < cue.end) || active[active.length - 1] || null;
  const primaryId = primary?.id || null;
  if (primaryId !== currentCueId) {
    currentCueId = primaryId;
    highlightCurrentCue(primaryId);
    els.currentCueLabel.textContent = primary
      ? `Cue ${project.cues.findIndex(item => item.id === primary.id) + 1} · ${primary.start.toFixed(2)}–${primary.end.toFixed(2)}`
      : "No active cue";
  }
  updateLyricFrame(time);
}

/** Per-frame pass: writes the transform of every visible word. */
/** Typography handed to the 3D text renderer. */
function lyricStyleFor3D() {
  const style = project.style;
  return {
    font: lyricFontStack(style),
    color: style.textColor,
    accent: style.accentColor,
    stroke: style.strokeColor,
    strokeWidth: style.strokeWidth,
    fontSize: style.fontSize,
    maxWidth: style.maxWidth,
    offset3DX: style.offset3DX,
    offset3DY: style.offset3DY,
    text3DPitch: style.text3DPitch,
    text3DYaw: style.text3DYaw,
    text3DRoll: style.text3DRoll,
    uppercase: style.uppercase
  };
}

function lyricIsIn3D() {
  // Opt-in, and independent of the background: 3D type works over the Odyssey
  // corridor, over a video, or over any of the flat visuals.
  return lyric3DEnabled();
}

/**
 * Preset tuned for the 3D path.
 *
 * The lyric must exist for the complete flight. A 0.12 s lead created the mesh
 * near the end of its 0.55 s arrival, while a fixed one-second tail removed it
 * before it passed the lens at low scene speeds.
 */
function preset3D(spec, preload = false) {
  const speed = Math.max(0.1,
    sceneSpeedFor(project.background, project.background.visualIntensity));
  // BOARD_NEAR is 8 in the renderer; allow the board to clear the 1.2-unit
  // near plane, plus a small safety margin. Focus Word intentionally keeps its
  // short per-word exit so consecutive words never stack on the same board.
  const passageTail = (8 - 1.2) / speed + 0.15;
  const tail = spec.hold === "word" ? spec.tail : Math.max(spec.tail, passageTail);
  // Allocate boards early to spread mesh creation over several frames, but
  // keep visible text on the user's word timing. Geometry preloading must not
  // turn the first sung word into a 600 ms anticipation on every phrase.
  return { ...spec, lead: preload ? Math.max(spec.lead, 0.6) : spec.lead, tail };
}

function updateLyricFrame(time) {
  const in3D = lyricIsIn3D();
  if (!lyricCues.size) {
    els.lyricDisplay.style.visibility = in3D ? "hidden" : "";
    window.VFSceneGL?.get(els.glCanvas)?.clearLyric();
    return;
  }
  const spec = activePreset();
  const intensity = Number(project.style.animation);
  const strength = Number.isFinite(intensity) ? intensity : 1;
  const beat = beatValue(time);
  const kinetic = K();

  // Odyssey 3D draws the lyric inside the scene, so the flat DOM layer steps
  // aside rather than doubling every word on screen.
  const entries3D = [];
  const wanted = in3D ? "hidden" : "";
  if (els.lyricDisplay.style.visibility !== wanted) els.lyricDisplay.style.visibility = wanted;

  for (const entry of lyricCues.values()) {
    for (const node of entry.nodes) {
      const state = kinetic.wordState(node.word, entry.cue, time, in3D ? preset3D(spec) : spec, beat);
      // wordState reuses a frozen singleton for hidden words. Keep its result
      // immutable and apply the lead-line override only to the rendered value.
      const fill = node.lead ? Math.max(state.fill, 1) : state.fill;

      if (in3D) {
        // The flight lands exactly on the sung syllable: the word travels
        // through depth beforehand but only resolves at its own moment.
        const flight = 0.55;
        entries3D.push({
          key: `${entry.cue.id}:${node.word.index}`,
          wordIndex: node.word.index,
          text: project.style.uppercase ? node.word.text.toUpperCase() : node.word.text,
          state: { ...state, fill },
          lineIndex: node.lineIndex || 0,
          lineCount: node.lineCount || 1,
          lineKey: node.lineKey || entry.cue.id,
          arrive: kinetic.clamp((time - (node.word.start - flight)) / flight),
          age: Math.max(0, time - node.word.end),
          wordStart: node.word.start,
          cueId: entry.cue.id,
          cueStart: entry.cue.start,
          cueEnd: entry.cue.end
        });
        continue;
      }

      const el = node.el;
      if (!state.visible || state.opacity <= 0.003) {
        if (el.style.visibility !== "hidden") el.style.visibility = "hidden";
        continue;
      }
      if (el.style.visibility === "hidden") el.style.visibility = "";

      const scale = 1 + (state.scale - 1) * strength;
      const dx = state.dx * strength;
      const dy = state.dy * strength;
      const rotate = state.rotate * strength;
      const blur = state.blur * strength;

      el.style.opacity = state.opacity.toFixed(3);
      el.style.transform =
        `translate3d(${dx.toFixed(3)}em, ${dy.toFixed(3)}em, 0) scale(${scale.toFixed(4)}) rotate(${rotate.toFixed(2)}deg)`;
      el.style.setProperty("--fill", fill.toFixed(3));
      el.style.setProperty("--fill-alpha", state.fillAlpha.toFixed(3));
      el.style.letterSpacing = state.tracking ? `${(state.tracking * strength).toFixed(3)}em` : "";

      const glow = state.glow;
      el.style.filter = blur > 0.05
        ? `drop-shadow(var(--lyric-shadow)) blur(${blur.toFixed(2)}px)`
        : glow > 0.02
          ? `drop-shadow(var(--lyric-shadow)) drop-shadow(0 0 ${(glow * 0.34).toFixed(3)}em var(--lyric-accent))`
          : "drop-shadow(var(--lyric-shadow))";
    }
  }

  if (in3D) {
    window.VFSceneGL.get(els.glCanvas).setLyric(entries3D, lyricStyleFor3D(), time, {
      speed: sceneSpeedFor(project.background, project.background.visualIntensity),
      spec: preset3D(spec)
    });
  } else {
    window.VFSceneGL?.get(els.glCanvas)?.clearLyric();
  }
}

function currentPlaybackTime() {
  if (project.audio?.url && Number.isFinite(els.audioPlayer.currentTime)) return els.audioPlayer.currentTime;
  if (virtualPlaying) return virtualStartedTime + (performance.now() - virtualStartedAt) / 1000;
  return virtualTime;
}

function seekTo(value) {
  const duration = projectDuration();
  value = Math.max(0, Math.min(duration, Number(value) || 0));
  if (project.audio?.url) {
    try { els.audioPlayer.currentTime = value; } catch { /* metadata may still be loading */ }
  } else {
    virtualTime = value;
    if (virtualPlaying) {
      virtualStartedTime = value;
      virtualStartedAt = performance.now();
    }
  }
  syncBackgroundVideo(value);
  updatePlaybackUI(value);
}

async function ensureAudioAnalyser() {
  if (!project.audio?.url || analyser) return;
  try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
    audioSource = audioContext.createMediaElementSource(els.audioPlayer);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = .78;
    analyser.minDecibels = -100;
    analyser.maxDecibels = -30;
    frequencyData = new Uint8Array(analyser.frequencyBinCount);
    audioSource.connect(analyser);
    analyser.connect(audioContext.destination);
  } catch {
    analyser = null;
  }
}

async function togglePlay() {
  if (project.audio?.url) {
    await ensureAudioAnalyser();
    if (audioContext?.state === "suspended") await audioContext.resume();
    if (els.audioPlayer.paused) {
      try {
        await els.audioPlayer.play();
        if (project.background.type === "video") els.backgroundVideo.play().catch(() => {});
      } catch (error) {
        toast(`Playback failed: ${error.message}`, "error");
      }
    } else {
      els.audioPlayer.pause();
      els.backgroundVideo.pause();
    }
  } else {
    virtualPlaying = !virtualPlaying;
    if (virtualPlaying) {
      if (virtualTime >= projectDuration()) virtualTime = 0;
      virtualStartedTime = virtualTime;
      virtualStartedAt = performance.now();
    } else {
      virtualTime = currentPlaybackTime();
    }
  }
  updatePlayButton();
}

function updatePlayButton() {
  const playing = project.audio?.url ? !els.audioPlayer.paused : virtualPlaying;
  els.playButton.textContent = playing ? "❚❚" : "▶";
  els.playButton.style.paddingLeft = playing ? "0" : "3px";
}

function syncBackgroundVideo(time) {
  if (project.background.type !== "video" || !Number.isFinite(els.backgroundVideo.duration) || !els.backgroundVideo.duration) return;
  const target = time % els.backgroundVideo.duration;
  if (Math.abs(els.backgroundVideo.currentTime - target) > .28) {
    try { els.backgroundVideo.currentTime = target; } catch { /* ignored */ }
  }
}

function updateDurationUI() {
  const duration = projectDuration();
  project.duration = duration;
  els.seekBar.max = duration;
  els.durationTime.textContent = formatTime(duration);
  updateRangeUI(els.seekBar);
  if (typeof refreshExportRange === "function") refreshExportRange();
}

function updatePlaybackUI(time) {
  const duration = projectDuration();
  if (!Number.isFinite(time)) time = 0;
  if (time > duration && !project.audio?.url) {
    virtualPlaying = false;
    virtualTime = duration;
    time = duration;
    updatePlayButton();
  }
  els.currentTime.textContent = formatTime(time);
  if (!els.seekBar.matches(":active")) els.seekBar.value = Math.min(duration, time);
  updateRangeUI(els.seekBar);
  renderLyric();
}

function highlightCurrentCue(id) {
  $$(".cue-card", els.cueList).forEach(card => card.classList.toggle("active", card.dataset.id === id));
}
