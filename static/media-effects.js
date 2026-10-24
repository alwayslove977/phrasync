"use strict";

// Shared, deterministic background composition for preview and offline export.
window.VFMedia = (() => {
  const resources = new Map();
  const positive = (v, fallback = 0) => Number.isFinite(Number(v)) ? Number(v) : fallback;
  function enabled(p = project) { return Boolean(p.background.footageEnabled); }
  function usesCanvas(p = project) {
    const fx = p.background.effects || {};
    return enabled(p) || ["bw", "pendulum", "shake", "flash", "gradient", "particles", "spectrum", "drop", "pulse"].some(key => positive(fx[key]) > 0);
  }
  function activeClip(time, p = project) {
    return (p.background.clips || []).filter(c => time >= c.start && time < c.end)
      .sort((a, b) => a.start - b.start).at(-1) || null;
  }
  function activeLayers(time) {
    const layers = new Map();
    for (const c of [...(project.background.clips || [])].sort((a,b) => a.start-b.start)) if (time >= c.start && time < c.end && (c.opacity ?? 1)>0) {
      const track=c.track||0; const list=layers.get(track)||[]; list.push(c); layers.set(track,list);
    }
    return [...layers.entries()].sort((a,b)=>a[0]-b[0]).flatMap(entry=>{
      const list=entry[1], top=list.at(-1);
      return top.transition !== "cut" && (top.fadeIn>0 || top.opacity<1) ? list.slice(-2) : [top];
    });
  }
  function resource(asset, instance = asset?.id) {
    if (!asset?.id) return null;
    if (resources.has(instance)) {
      const value = resources.get(instance); resources.delete(instance); resources.set(instance, value); return value;
    }
    const element = document.createElement(asset.kind === "video" ? "video" : "img");
    const value = { element, error: null, ready: false };
    resources.set(instance, value);
    element.addEventListener("error", () => { value.error = `Cannot decode footage: ${asset.name}`; });
    element.addEventListener(asset.kind === "video" ? "loadeddata" : "load", () => { value.ready = true; });
    if (asset.kind === "video") { element.muted = true; element.playsInline = true; element.preload = "auto"; }
    element.src = asset.url || `/media/${encodeURIComponent(asset.id)}`;
    while (resources.size > 9) {
      const key = resources.keys().next().value, old = resources.get(key).element;
      old.pause?.(); old.removeAttribute("src"); old.load?.(); resources.delete(key);
    }
    return value;
  }
  async function waitReady(value) {
    if (!value) throw new Error("Footage asset is missing");
    const started = performance.now();
    while (!value.ready) {
      if (value.error) throw new Error(value.error);
      if (performance.now() - started > 20000) throw new Error("Footage took too long to load");
      await new Promise(resolve => setTimeout(resolve, 20));
    }
  }
  function sourceTime(clip, t, video) {
    const desired = clip.in + Math.max(0, t - clip.start) * clip.rate;
    return Math.max(0, Math.min(desired, Math.max(0, video.duration - .001)));
  }
  async function seekExact(video, time) {
    video.pause();
    if (Math.abs(video.currentTime - time) < .0005 && video.readyState >= 2) return;
    await new Promise((resolve, reject) => {
      let timer;
      const clean = () => { clearTimeout(timer); video.removeEventListener("seeked", done); video.removeEventListener("error", fail); };
      const done = () => { clean(); resolve(); };
      const fail = () => { clean(); reject(new Error("Footage seek failed")); };
      video.addEventListener("seeked", done); video.addEventListener("error", fail);
      timer = setTimeout(() => { clean(); reject(new Error("Footage seek timed out")); }, 15000);
      try { video.currentTime = time; } catch (error) { clean(); reject(error); }
    });
  }
  function syncVideo(source, target, rate, playing) {
    if (!playing) {
      if (!source.paused) source.pause();
      source.playbackRate = rate;
      if (!source.seeking && Math.abs(source.currentTime-target) > .008) source.currentTime = target;
      return;
    }
    const error = target-source.currentTime;
    // Seek for discontinuities, not ordinary clock drift: frequent seeks on
    // long-GOP video repeatedly discard the decoder's work. A proportional
    // clock correction actively converges instead of accepting a fixed lag.
    if (!source.seeking && (Math.abs(error) > .25 || (source.paused && Math.abs(error) > .015))) source.currentTime = target;
    const correction = source.seeking || Math.abs(error) < .004 ? 0 : Math.max(-.25, Math.min(.25, error*4));
    source.playbackRate = Math.max(.0625, Math.min(16, rate*(1+correction)));
    if (source.paused) source.play().catch(() => {});
  }
  function beat(t, amplitude) {
    const fx = project.background.effects || {}, bpm = positive(fx.bpm) || positive(project.timing?.bpm);
    const hits = project.background.effectOnsets || [];
    if (fx.trigger === "transient" && hits.length) {
      let lo=0, hi=hits.length;
      while (lo<hi) { const mid=(lo+hi)>>1; if (hits[mid]<=t) lo=mid+1; else hi=mid; }
      return lo>0 ? Math.exp(-Math.max(0,t-hits[lo-1])*24) : 0;
    }
    if (bpm > 0) {
      const phase = ((t - positive(project.timing?.beatOffset)) * bpm / 60 % 1 + 1) % 1;
      return Math.exp(-phase * 14);
    }
    return Math.max(0, Math.min(1, amplitude));
  }
  function drawBase(ctx, source, clip, t, amplitude, clear = true) {
    const w = ctx.canvas.width, h = ctx.canvas.height, fx = project.background.effects || {};
    ctx.save(); if (clear) { ctx.fillStyle = project.background.backgroundColor || "#080812"; ctx.fillRect(0, 0, w, h); }
    if (!source || !(source.videoWidth || source.naturalWidth || source.displayWidth || source.width)) { ctx.restore(); return; }
    const sw = source.videoWidth || source.naturalWidth || source.displayWidth || source.width;
    const sh = source.videoHeight || source.naturalHeight || source.displayHeight || source.height;
    const p = clip ? Math.max(0, Math.min(1, (t - clip.start) / Math.max(.01, clip.end - clip.start))) : 0;
    const lerp = (a, b) => positive(a) * (1 - p) + positive(b) * p;
    const angle = positive(fx.pendulum) * Math.sin(t * Math.PI * .8) * Math.PI / 180;
    const pulse = beat(t, amplitude), shake = positive(fx.shake) * pulse / 100;
    const zoom = clip ? lerp(clip.zoomStart ?? 1, clip.zoomEnd ?? 1) : 1;
    // Cover rotated corners, so effects never expose a torn black strip.
    const overscan = Math.abs(Math.cos(angle)) + Math.abs(Math.sin(angle)) * Math.max(w / h, h / w);
    const scale = Math.max(w / sw, h / sh) * Math.max(1, zoom) * (overscan + shake * 2) * (1 + positive(fx.drop)/100*pulse);
    const dw = sw * scale, dh = sh * scale;
    const x = clip ? lerp(clip.xStart, clip.xEnd) : 0, y = clip ? lerp(clip.yStart, clip.yEnd) : 0;
    ctx.translate(w / 2 + Math.sin(t * 83) * w * shake, h / 2 + Math.cos(t * 97) * h * shake);
    ctx.rotate(angle);
    ctx.filter = `grayscale(${Math.max(0, Math.min(1, positive(fx.bw) / 100))}) blur(${positive(project.background.blur) * Math.min(w, h) / 1080}px) brightness(${positive(project.background.brightness, 1)})`;
    ctx.drawImage(source, -dw / 2 + x * Math.max(0, dw - w) / 2, -dh / 2 + y * Math.max(0, dh - h) / 2, dw, dh);
    ctx.restore();
  }
  function drawOverlay(ctx, t, amplitude) {
    const fx = project.background.effects || {}, w = ctx.canvas.width, h = ctx.canvas.height;
    ctx.save();
    const light = positive(fx.pulse)/100 * beat(t,amplitude);
    if (light > 0) { ctx.globalAlpha=light; ctx.fillStyle=fx.color1 || "#a855f7"; ctx.fillRect(0,0,w,h); }
    const gradient = positive(fx.gradient) / 100;
    if (gradient > 0) {
      const fill = ctx.createLinearGradient(0, 0, w, h);
      fill.addColorStop(0, fx.color1 || "#6b21a8"); fill.addColorStop(1, fx.color2 || "#ec4899");
      ctx.globalAlpha = gradient; ctx.fillStyle = fill; ctx.fillRect(0, 0, w, h);
    }
    const flash = positive(fx.flash) / 100 * beat(t, amplitude);
    if (flash > 0) { ctx.globalAlpha = flash; ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, w, h); }
    const count = Math.round(positive(fx.particles) * 1.5);
    ctx.fillStyle = fx.color2 || "#ec4899";
    for (let i = 0; i < count; i++) {
      const hash = n => ((Math.sin(n * 127.1 + 311.7) * 43758.5453) % 1 + 1) % 1;
      const x = ((hash(i + 1) + t * (.007 + hash(i + 4) * .01)) % 1) * w;
      const y = ((hash(i + 73) - t * (.018 + hash(i + 11) * .025)) % 1 + 1) % 1 * h;
      ctx.globalAlpha = .25 + .5 * hash(i + 6);
      ctx.beginPath(); ctx.arc(x, y, (1 + hash(i + 2) * 2) * Math.min(w, h) / 540, 0, Math.PI * 2); ctx.fill();
    }
    if (positive(fx.spectrum) > 0) {
      const spectrum = window.__vfExportSpectrum || spectrumSnapshot() || [];
      const bins = Math.min(64, spectrum.length), base = h * .94;
      ctx.globalAlpha = .9; ctx.strokeStyle = fx.color1 || "#a855f7";
      ctx.lineWidth = Math.max(1, Math.min(w, h) / 270); ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = ctx.lineWidth * 3;
      ctx.beginPath();
      for (let i = 0; i <= bins; i++) {
        const x = w * (.04 + .92 * i / Math.max(1, bins));
        const y = base - Math.max(0, spectrum[Math.min(i, bins - 1)] || 0) * h * .18 * positive(fx.spectrum) / 100;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    ctx.restore();
  }
  function legacySource() {
    const bg = project.background;
    if (bg.type === "image") return els.backgroundImage;
    if (bg.type === "video") return els.backgroundVideo;
    return bg.visual === "scene3d" ? (window.__vfExportMode && window.__vfExportGLSnapshot || els.glCanvas) : els.visualCanvas;
  }
  const browserDecode = new Set();
  async function exportVideo(video, time, key) {
    const endpoint = window.__vfFootageFramesEndpoint;
    if (endpoint && !browserDecode.has(key)) {
      try {
        const frame = await window.VFFootageDecoder?.frame(key, time);
        if (frame) return frame;
      } catch (_) { /* Keep the established browser decoder as compatibility fallback. */ }
      browserDecode.add(key);
    }
    await seekExact(video, time);
    return video;
  }
  async function exportSource(t) {
    if (!enabled()) {
      const source = legacySource();
      if (source === els.backgroundVideo) {
        const asset = activeBackgroundAsset("video");
        const value = resource({ ...asset, kind: "video" }); await waitReady(value);
        return { source: await exportVideo(value.element, t % value.element.duration, "__legacy"), clip: null };
      }
      if (source === els.backgroundImage) {
        const value = resource({ ...activeBackgroundAsset("image"), kind: "image" }); await waitReady(value);
        return { source: value.element, clip: null };
      }
      return { source, clip: null };
    }
    const clip = activeClip(t);
    if (!clip) return { source: null, clip: null };
    const value = resource(clip.asset); await waitReady(value);
    if (clip.asset.kind === "video") await seekExact(value.element, sourceTime(clip, t, value.element));
    return { source: value.element, clip };
  }
  async function exportBase(ctx, t, amplitude) {
    if (!enabled()) { const { source, clip } = await exportSource(t); try { drawBase(ctx,source,clip,t,amplitude); } finally { source?.close?.(); } return; }
    drawBase(ctx,null,null,t,amplitude);
    for (const clip of activeLayers(t)) {
      let source;
      if (clip.asset.kind === "visual") source = VFVisualClips.render(clip,clip.in+(t-clip.start)*clip.rate,ctx.canvas.width,ctx.canvas.height);
      else { const value=resource(clip.asset,clip.id); await waitReady(value); source=value.element; if (clip.asset.kind === "video") source=await exportVideo(source,sourceTime(clip,t,source),clip.id); }
      try { drawLayer(ctx,source,clip,t,amplitude); } finally { source?.close?.(); }
    }
  }
  function drawLayer(ctx, source, clip, t, amplitude) {
    const duration=clip.end-clip.start, enter=clip.fadeIn > 0 ? Math.min(1,(t-clip.start)/Math.min(clip.fadeIn,duration)) : 1;
    const leave=clip.fadeOut > 0 ? Math.min(1,(clip.end-t)/Math.min(clip.fadeOut,duration)) : 1;
    ctx.save(); ctx.globalAlpha=positive(clip.opacity,1)*leave;
    if (clip.transition === "wipe") { ctx.beginPath(); ctx.rect(0,0,ctx.canvas.width*enter,ctx.canvas.height); ctx.clip(); }
    else if (clip.transition === "slide") ctx.translate(ctx.canvas.width*(1-enter),0);
    else if (clip.transition !== "cut") ctx.globalAlpha*=enter;
    drawBase(ctx,source,clip,t,amplitude,false); ctx.restore();
  }
  function preview(t, playing) {
    const canvas = document.getElementById("footageCanvas"), overlay = document.getElementById("effectsCanvas");
    const use = usesCanvas(); canvas.hidden = !use; overlay.hidden = !use;
    const world = !enabled() && project.background.type === "dynamic" && project.background.visual === "scene3d";
    els.glCanvas.style.opacity = use && world ? "0" : "";
    const status = document.getElementById("footagePreviewStatus"); if (status) status.hidden = true;
    if (!use) { for (const value of resources.values()) value.element.pause?.(); return; }
    const rect = els.stage.getBoundingClientRect();
    const width = Math.max(2, Math.round(rect.width)), height = Math.max(2, Math.round(rect.height));
    for (const el of [canvas, overlay]) if (el.width !== width || el.height !== height) { el.width = width; el.height = height; }
    let source = legacySource(), clip = null;
    const baseCtx = canvas.getContext("2d"), amplitude = project.audio?.url ? audioAmplitude() : 0;
    if (enabled()) {
      drawBase(baseCtx,null,null,t,amplitude);
      const activeVideos=new Set();
      // Each clip has its own decoder, even when it reuses the same asset.
      // Pre-roll a trimmed clip before its visible cut, so decoder startup and
      // clock convergence do not happen in the middle of a crossfade.
      const upcoming=(project.background.clips||[]).filter(c=>c.start>t&&c.start-t<1)
        .sort((a,b)=>a.start-b.start).slice(0,2);
      for (const next of upcoming) {
        if (next.asset.kind === "visual") continue;
        const value=resource(next.asset,next.id);
        if (next.asset.kind === "video" && value?.ready) {
          const v=value.element, target=Math.max(0,Math.min(next.in+(t-next.start)*next.rate,v.duration-.001));
          syncVideo(v,target,next.rate,playing&&target>0);
          activeVideos.add(v);
        }
      }
      for (const layer of activeLayers(t)) {
      clip=layer;
      if (clip.asset.kind === "visual") { source=VFVisualClips.render(clip,clip.in+(t-clip.start)*clip.rate,width,height); drawLayer(baseCtx,source,clip,t,amplitude); continue; }
      const value = resource(clip.asset,clip.id);
      if (status && value && !value.ready) { status.hidden = false; status.textContent = value.error || `${window.t("Preparing video…")} ${clip.asset.name}`; }
      source = value?.ready ? value.element : null;
      if (value?.error && !value.reported) { value.reported = true; toast(value.error, "error"); }
      if (source && clip.asset.kind === "video") {
        activeVideos.add(source);
        const target = sourceTime(clip, t, source);
        syncVideo(source, target, clip.rate, playing);
      }
      drawLayer(baseCtx,source,clip,t,amplitude);
      }
      for (const entry of resources.values()) if (!activeVideos.has(entry.element)) entry.element.pause?.();
    }
    else drawBase(baseCtx,source,clip,t,amplitude);
    const ctx = overlay.getContext("2d"); ctx.clearRect(0, 0, width, height); drawOverlay(ctx, t, amplitude);
  }
  return { enabled, usesCanvas, activeClip, preview, exportBase, drawOverlay, preload: resource, syncVideo };
})();
