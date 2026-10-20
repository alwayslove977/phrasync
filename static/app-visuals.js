"use strict";

function initParticles(width, height) {
  const key = `${width}x${height}:${project.background.sceneSeed || 1337}`;
  if (key === lastParticleSize && particles.length) return;
  lastParticleSize = key;
  const count = Math.max(35, Math.round(width * height / 11000));
  const rand = n => { const x=Math.sin(n*127.1+(project.background.sceneSeed||1337))*43758.5453; return x-Math.floor(x); };
  particles = Array.from({ length: count }, (_,i) => ({
    x: rand(i*5+1) * width,
    y: rand(i*5+2) * height,
    r: .5 + rand(i*5+3) * 2.2,
    speed: .15 + rand(i*5+4) * .55,
    phase: rand(i*5+5) * Math.PI * 2
  }));
}
function audioAmplitude() {
  if (Number.isFinite(window.__vfExportAmplitude)) return window.__vfExportAmplitude;
  if (!analyser || !frequencyData) return .18 + .08 * Math.sin(performance.now() / 350);
  analyser.getByteFrequencyData(frequencyData);
  let sum = 0;
  const end = Math.min(70, frequencyData.length);
  for (let i = 2; i < end; i++) sum += frequencyData[i];
  return Math.min(1, sum / Math.max(1, end - 2) / 175);
}

function resizeVisualCanvas() {
  const rect = (els.visualCanvas.isConnected ? els.visualCanvas : els.stage).getBoundingClientRect();
  // The preview is already scaled inside the editor. Rendering it at a full
  // high-DPI backing resolution wastes millions of pixels per frame in a
  // desktop WebView without improving the exported video.
  const dpr = IS_DESKTOP_HOST ? 1 : Math.min(1.5, window.devicePixelRatio || 1);
  const width = Math.max(2, Math.round(rect.width * dpr));
  const height = Math.max(2, Math.round(rect.height * dpr));
  if (els.visualCanvas.width !== width || els.visualCanvas.height !== height) {
    els.visualCanvas.width = width;
    els.visualCanvas.height = height;
    initParticles(width, height);
  }
}

/**
 * Live spectrum for the particle wave, normalised to 0..1.
 *
 * Falls back to a slow synthetic sweep when no audio is playing so the field
 * still breathes while the user is only scrubbing.
 */
function spectrumSnapshot() {
  if (window.__vfExportSpectrum?.length) return window.__vfExportSpectrum;
  if (!analyser || !frequencyData) return null;
  analyser.getByteFrequencyData(frequencyData);
  const bins = Math.min(64, frequencyData.length);
  const out = new Float32Array(bins);
  for (let i = 0; i < bins; i += 1) out[i] = frequencyData[i] / 255;
  return out;
}

/** World travel speed, shared by the corridor and by 3D word placement. */
function sceneSpeedFor(bg, intensity) {
  return 9 * (bg.sceneSpeed ?? 1) * (0.7 + (intensity ?? 0.9) * 0.45);
}

function lyric3DEnabled() {
  return project.background.textSpace === "scene"
    && Boolean(window.VFSceneGL) && Boolean(els.glCanvas);
}

function glLayerNeeded() {
  const bg = project.background;
  return Boolean(window.VFSceneGL)
    && (lyric3DEnabled() || Boolean(bg.sceneWave)
      || (bg.type === "dynamic" && bg.visual === "scene3d" && !VFMedia.enabled()));
}

/**
 * Drive the WebGL layer.
 *
 * Two shapes: the full Odyssey corridor, or a bare scene holding only the 3D
 * lyric so it can sit over any other background. The 2D canvas keeps painting
 * underneath in the second case, which is why it is not hidden there.
 */
function drawSceneGL(t, bg, pulse, intensity) {
  if (!window.VFSceneGL) return null;
  const gl = els.glCanvas;
  const world = bg.type === "dynamic" && bg.visual === "scene3d" && !VFMedia.enabled();
  if (gl.hidden) gl.hidden = false;
  if (els.visualCanvas.hidden !== world) els.visualCanvas.hidden = world;

  const rect = els.stage.getBoundingClientRect();
  const width = Math.max(2, Math.round(rect.width));
  const height = Math.max(2, Math.round(rect.height));
  if (gl.style.width !== `${width}px`) {
    gl.style.width = `${width}px`;
    gl.style.height = `${height}px`;
  }

  const scene = window.VFSceneGL.get(gl);
  if (world) scene.build(bg.sceneKit || "japan");
  else scene.buildTextOnly();
  scene.setSize(width, height);
  const environment = resolvedEnvironmentAt(t);
  if (world) {
    els.environmentResolved.textContent = [
      environment.season, environment.daytime, environment.weather
    ].join(" · ");
  }
  scene.update(t, {
    direction: bg.sceneDirection || "forward",
    artStyle: bg.artStyle || "cinematic",
    secondaryMotion: bg.secondaryMotion || "none",
    motionAmount: bg.motionAmount ?? .35,
    sunAzimuth: bg.sunAzimuth ?? 25, sunElevation: bg.sunElevation ?? 12,
    moonAzimuth: bg.moonAzimuth ?? -25, moonElevation: bg.moonElevation ?? 18,
    waveStrength: bg.oceanWaveStrength ?? .65,
    seed: bg.sceneSeed || 1337,
    speed: sceneSpeedFor(bg, intensity),
    density: bg.sceneDensity ?? 1,
    // Props and lights hold still unless the user asks for beat reaction.
    pulse: bg.sceneBeat ? pulse : 0,
    wave: Boolean(bg.sceneWave),
    waveColor: bg.waveColor || "#4de2ff",
    waveIntensity: bg.waveIntensity ?? 1,
    spectrum: bg.sceneWave ? spectrumSnapshot() : null,
    environment
  });
  return scene;
}

function drawDynamicVisual(now) {
  resizeVisualCanvas();
  const canvas = els.visualCanvas;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const t = now / 1000;
  const bg = project.background;
  const intensity = bg.visualIntensity;
  const amplitude = audioAmplitude();
  const pulse = Math.max(beatValue(lyricTime()), amplitude * 0.8);
  if (!els.glCanvas.hidden && !glLayerNeeded()) {
    els.glCanvas.hidden = true;
  }
  if (els.visualCanvas.hidden) els.visualCanvas.hidden = false;
  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = bg.backgroundColor;
  ctx.fillRect(0, 0, width, height);

  if (bg.visual === "scene3d") {
    return drawSceneGL(lyricTime(), bg, pulse, intensity);
  }

  if (bg.visual === "scene") {
    window.VFSceneDraw.paint(ctx, width, height, {
      t,
      kit: bg.sceneKit || "japan",
      direction: bg.sceneDirection || "forward",
      seed: bg.sceneSeed || 1337,
      speed: 7 * (bg.sceneSpeed ?? 1) * (0.65 + intensity * 0.5),
      density: bg.sceneDensity ?? 1,
      pulse
    });
  }

  const aurora = () => {
    ctx.globalCompositeOperation = "screen";
    const blobs = [
      [.18 + .13 * Math.sin(t * .31), .24 + .17 * Math.cos(t * .23), .95, project.style.accentColor],
      [.79 + .12 * Math.cos(t * .27), .40 + .15 * Math.sin(t * .18), .82, bg.secondaryColor],
      [.48 + .19 * Math.sin(t * .16), .84 + .09 * Math.cos(t * .29), .72, project.style.accentColor2],
      [.62 + .16 * Math.cos(t * .21), .16 + .11 * Math.sin(t * .25), .58, bg.secondaryColor]
    ];
    for (const [nx, ny, strength, color] of blobs) {
      // The beat swells the blobs, which is what makes the field feel scored
      // to the track rather than idly drifting.
      const swell = 1 + .13 * pulse;
      const radius = Math.max(width, height) * (.40 + intensity * .16) * swell;
      // Kept moderate on purpose: overlapping "screen" blobs wash out to
      // pastel and the lyric loses contrast against them.
      const alpha = Math.min(.60, (.15 + intensity * .26) * strength * (1 + .18 * pulse));
      const gradient = ctx.createRadialGradient(nx * width, ny * height, 0, nx * width, ny * height, radius);
      gradient.addColorStop(0, `${color}${Math.round(alpha * 255).toString(16).padStart(2,"0")}`);
      gradient.addColorStop(.55, `${color}${Math.round(alpha * .34 * 255).toString(16).padStart(2,"0")}`);
      gradient.addColorStop(1, `${color}00`);
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);
    }
    ctx.globalCompositeOperation = "source-over";
    const vignette = ctx.createRadialGradient(width/2, height/2, Math.min(width,height)*.22, width/2, height/2, Math.max(width,height)*.78);
    vignette.addColorStop(0, "rgba(0,0,0,0)");
    vignette.addColorStop(1, "rgba(0,0,0,.46)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0,0,width,height);
  };

  if (bg.visual === "aurora" || bg.visual === "equalizer" || bg.visual === "particles") aurora();

  if (bg.visual === "particles") {
    ctx.globalCompositeOperation = "screen";
    for (const particle of particles) {
      const px = (particle.x+t*60*particle.speed*(.35+intensity))%width;
      const py = ((particle.y-t*60*particle.speed*.23)%height+height)%height;
      const twinkle = .65 + .35 * Math.sin(t * 1.2 + particle.phase);
      ctx.beginPath();
      ctx.fillStyle = `rgba(227,132,255,${.30 + amplitude * .55 + pulse * .16})`;
      ctx.arc(px, py, particle.r * twinkle * (1 + amplitude + pulse * .5), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
  } else if (bg.visual === "equalizer") {
    const bars = 40;
    const gap = width * .004;
    const available = width * .78;
    const barWidth = Math.max(2, (available - gap * (bars - 1)) / bars);
    const left = (width - available) / 2;
    const base = height * .91;
    for (let i = 0; i < bars; i++) {
      const exported=window.__vfExportSpectrum;
      const freq = exported?.length ? exported[Math.min(exported.length-1,Math.floor(i*exported.length/bars))] : frequencyData ? frequencyData[Math.min(frequencyData.length - 1, 3 + i * 2)] / 255 : .15 + .12 * Math.abs(Math.sin(i * .67 + t * 3));
      const value = Math.max(.05, freq * (.62 + intensity * .95) * (1 + pulse * .22));
      const barHeight = height * .34 * value;
      const gradient = ctx.createLinearGradient(0, base - barHeight, 0, base);
      gradient.addColorStop(0, project.style.accentColor);
      gradient.addColorStop(1, `${project.style.accentColor2}77`);
      ctx.fillStyle = gradient;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(left + i * (barWidth + gap), base - barHeight, barWidth, barHeight, barWidth/2);
      else ctx.rect(left + i * (barWidth + gap), base - barHeight, barWidth, barHeight);
      ctx.fill();
    }
  } else if (bg.visual === "grid") {
    const horizon = height * .58;
    const center = width / 2;
    const color = project.style.accentColor;
    ctx.strokeStyle = `${color}${Math.round(Math.min(255, 110 + pulse * 80)).toString(16).padStart(2,"0")}`;
    ctx.lineWidth = Math.max(1, width / 760) * (1 + pulse * .3);
    for (let i = -14; i <= 14; i++) {
      ctx.beginPath(); ctx.moveTo(center, horizon); ctx.lineTo(center + i * width / 13, height); ctx.stroke();
    }
    const phase = (t * .6) % 1;
    for (let row = 0; row < 20; row++) {
      const z = (row + phase) / 20;
      const y = horizon + z * z * (height - horizon);
      ctx.globalAlpha = .26 + z * .62;
      ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(width,y); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    const glow = ctx.createLinearGradient(0, horizon - height*.08, 0, horizon + height*.1);
    glow.addColorStop(0, `${color}00`); glow.addColorStop(.5, `${color}88`); glow.addColorStop(1, `${color}00`);
    ctx.fillStyle = glow; ctx.fillRect(0,horizon-height*.08,width,height*.18);
  }

  if ((lyric3DEnabled() || bg.sceneWave) && bg.visual !== "scene3d") {
    return drawSceneGL(lyricTime(), bg, pulse, intensity);
  }
  return null;
}
function prepareWebGLOverlay(time) {
  const bg = project.background;
  if (!glLayerNeeded()) {
    if (!els.glCanvas.hidden) {
      window.VFSceneGL?.get(els.glCanvas).clearLyric();
      els.glCanvas.hidden = true;
    }
    return null;
  }
  const intensity = bg.visualIntensity;
  const pulse = Math.max(beatValue(time), audioAmplitude() * 0.8);
  return drawSceneGL(time, bg, pulse, intensity);
}

/** Deterministic frame hook used by the local MP4 WebGL renderer. */
window.VFExport = {
  async prepare(width, height, exportProject) {
    window.__vfExportMode = true;
    virtualPlaying = false;
    virtualTime = 0;
    if (!els.audioPlayer.paused) els.audioPlayer.pause();
    project = migrateProject(exportProject);
    // Do not encode frames until the requested font is actually ready.
    await ensureCustomFont();
    // The server muxes the original audio after the WebGL video pass. Keeping
    // the browser audio detached makes currentPlaybackTime deterministic.
    project.audio = null;
    els.audioPlayer.removeAttribute("src");
    Object.assign(els.stage.style, {
      position: "fixed", inset: "0", width: `${width}px`, height: `${height}px`,
      maxWidth: "none", maxHeight: "none", transform: "none"
    });
    Object.assign(els.stageShell.style, {
      position: "fixed", inset: "0", width: `${width}px`, height: `${height}px`,
      padding: "0", margin: "0", border: "0", transform: "none"
    });
    document.body.style.margin = "0";
    this.output = document.createElement("canvas");
    this.output.width = width;
    this.output.height = height;
    renderLyric(true);
    await new Promise(resolve => requestAnimationFrame(resolve));
    return Boolean(window.VFSceneGL?.ready);
  },

  async renderFrame(time, amplitude = 0) {
    virtualTime = Number(time) || 0;
    window.__vfExportAmplitude = Number(amplitude) || 0;
    const lyricT = lyricTime(virtualTime);
    const bg = project.background;
    const timing = project.timing || {};
    const beat = project.style.beatReact
      ? K().beatPulse(lyricT, Number(timing.bpm) || 0, Number(timing.beatOffset) || 0)
      : 0;
    const pulse = Math.max(beat, (Number(amplitude) || 0) * 0.8);
    const world = bg.type === "dynamic" && bg.visual === "scene3d" && !VFMedia.enabled();
    let scene;
    if (world) scene = drawSceneGL(lyricT, bg, pulse, bg.visualIntensity);
    else if (bg.type === "dynamic" && !VFMedia.enabled()) scene = drawDynamicVisual(virtualTime * 1000);
    else scene = prepareWebGLOverlay(lyricT);
    // setLyric intentionally creates only four slabs per UI frame. During an
    // offline export we can finish the current phrase before encoding it.
    renderLyric(false);
    for (let pass = 0; pass < 12; pass += 1) updateLyricFrame(lyricT);
    scene?.render();
    // Copy WebGL pixels before awaiting media loads/seeks: Chromium may clear
    // its drawing buffer when the async task yields to the compositor.
    if (glLayerNeeded() && (!world || VFMedia.usesCanvas())) {
      this.glSnapshot ||= document.createElement("canvas");
      if (this.glSnapshot.width !== els.glCanvas.width || this.glSnapshot.height !== els.glCanvas.height) {
        this.glSnapshot.width = els.glCanvas.width; this.glSnapshot.height = els.glCanvas.height;
      }
      const snapshot = this.glSnapshot.getContext("2d");
      snapshot.clearRect(0, 0, this.glSnapshot.width, this.glSnapshot.height);
      snapshot.drawImage(els.glCanvas, 0, 0);
      window.__vfExportGLSnapshot = this.glSnapshot;
    }
    if (world && !VFMedia.usesCanvas()) return { width: els.glCanvas.width, height: els.glCanvas.height };

    const canvas = this.output;
    const ctx = canvas.getContext("2d", { alpha: false });
    ctx.fillStyle = bg.backgroundColor || "#080812";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const cover = source => {
      if (!source?.naturalWidth && !source?.videoWidth) return;
      const sw = source.naturalWidth || source.videoWidth;
      const sh = source.naturalHeight || source.videoHeight;
      const scale = Math.max(canvas.width / sw, canvas.height / sh);
      const dw = sw * scale, dh = sh * scale;
      ctx.drawImage(source, (canvas.width - dw) / 2, (canvas.height - dh) / 2, dw, dh);
    };
    if (VFMedia.usesCanvas()) await VFMedia.exportBase(ctx, virtualTime, amplitude);
    else if (bg.type === "dynamic") ctx.drawImage(els.visualCanvas, 0, 0, canvas.width, canvas.height);
    else if (bg.type === "image") cover(els.backgroundImage);
    else if (bg.type === "video") {
      const video = els.backgroundVideo;
      if (Number.isFinite(video.duration) && video.duration > 0) {
        const target = virtualTime % video.duration;
        if (Math.abs(video.currentTime - target) > 0.002) {
          await new Promise(resolve => {
            const done = () => resolve();
            video.addEventListener("seeked", done, { once: true });
            video.currentTime = target;
            setTimeout(done, 250);
          });
        }
      }
      cover(video);
    }
    const shade = Math.max(0, Math.min(0.92, Number(bg.shade) || 0));
    if (shade) {
      ctx.fillStyle = `rgba(0,0,0,${shade})`;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    if (!world && glLayerNeeded()) ctx.drawImage(this.glSnapshot, 0, 0, canvas.width, canvas.height);
    if (VFMedia.usesCanvas()) VFMedia.drawOverlay(ctx, virtualTime, amplitude);
    return { width: canvas.width, height: canvas.height };
  },

  canvas() {
    const bg = project.background;
    return bg.type === "dynamic" && bg.visual === "scene3d" && !VFMedia.enabled() && !VFMedia.usesCanvas() ? els.glCanvas : this.output;
  }
};
