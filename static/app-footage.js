"use strict";

let selectedFootageId = null;
let footageDrag = null;
let footageViewKey = "";
const footageClipFields = [
  ["start", "Timeline start (s)", 0, null, .01], ["end", "Timeline end (s)", .05, null, .01],
  ["in", "Source in (s)", 0, null, .01], ["rate", "Playback speed", .25, 4, .05],
  ["zoomStart", "Zoom start", 1, 4, .01], ["zoomEnd", "Zoom end", 1, 4, .01],
  ["xStart", "Pan start X", -1, 1, .01], ["yStart", "Pan start Y", -1, 1, .01],
  ["xEnd", "Pan end X", -1, 1, .01], ["yEnd", "Pan end Y", -1, 1, .01],
  ["opacity", "Clip opacity", 0, 1, .01], ["fadeIn", "Transition in (s)", 0, 5, .05], ["fadeOut", "Transition out (s)", 0, 5, .05]
];
const footageEffects = [
  ["bw", "Black & white", 100], ["pendulum", "Pendulum (degrees)", 15],
  ["shake", "Beat shake (%)", 8], ["flash", "Beat flash (%)", 60],
  ["gradient", "Gradient opacity (%)", 80], ["particles", "Particles", 100],
  ["spectrum", "Spectrum intensity (%)", 150], ["bpm", "Effect tempo (BPM, 0 = audio analysis)", 300],
  ["drop", "Beat drop zoom (%)", 30], ["pulse", "Beat light pulse (%)", 40]
];
function selectedFootage() { return (project.background.clips || []).find(c => c.id === selectedFootageId); }
function constrainFootage(clip) {
  clip.start = Math.max(0, Number(clip.start) || 0);
  clip.rate = Math.max(.25, Math.min(4, Number(clip.rate) || 1));
  clip.in = Math.max(0, Number(clip.in) || 0);
  clip.end = Math.max(clip.start + .05, Number(clip.end) || clip.start + 5);
  if (clip.asset.kind === "video" && clip.asset.duration > 0) {
    clip.in = Math.min(clip.in, Math.max(0, clip.asset.duration - .05 * clip.rate));
    clip.end = Math.min(clip.end, clip.start + (clip.asset.duration - clip.in) / clip.rate);
  }
  for (const key of ["zoomStart", "zoomEnd"]) clip[key] = Math.max(1, Math.min(4, Number(clip[key]) || 1));
  for (const key of ["xStart", "yStart", "xEnd", "yEnd"]) clip[key] = Math.max(-1, Math.min(1, Number(clip[key]) || 0));
  clip.opacity = Math.max(0, Math.min(1, Number(clip.opacity ?? 1)));
  for (const key of ["fadeIn", "fadeOut"]) clip[key] = Math.max(0, Math.min(5, Number(clip[key]) || 0));
}
function refreshFootageControls() {
  if (!document.getElementById("footageEnable")) return;
  const bg = project.background, select = document.getElementById("footageSelect");
  document.getElementById("footageEnable").checked = Boolean(bg.footageEnabled);
  const clips = bg.clips || [];
  if (!clips.some(c => c.id === selectedFootageId)) selectedFootageId = null;
  select.textContent = "";
  if (!clips.length) { const option = document.createElement("option"); option.textContent = t("Select a clip"); select.append(option); }
  for (const clip of [...clips].sort((a, b) => a.start - b.start)) {
    const option = document.createElement("option"); option.value = clip.id;
    option.textContent = `${clip.start.toFixed(2)}s · ${clip.asset.name}`; select.append(option);
  }
  select.value = selectedFootageId || "";
  const clip = selectedFootage();
  document.getElementById("footageTools").hidden = !clip;
  document.getElementById("footageClipEditor").hidden = !clip;
  document.getElementById("clipLayerSettings").hidden = !clip;
  refreshVisualTrackControls(clip);
  for (const [key] of footageClipFields) if (clip) document.getElementById(`clip-${key}`).value = clip[key] ?? (key === "opacity" ? 1 : 0);
  for (const [key] of footageEffects) document.getElementById(`fx-${key}`).value = bg.effects?.[key] || 0;
  for (const key of ["color1", "color2"]) document.getElementById(`fx-${key}`).value = bg.effects?.[key] || (key === "color1" ? "#6b21a8" : "#ec4899");
  refreshMediaBin(); syncNumericSliders();
  footageViewKey = ""; renderFootageLane();
}
function footageChanged() {
  window.__mediaErrorShown = false;
  footageViewKey = ""; renderFootageLane(); updateDurationUI(); scheduleSave();
}
async function importFootage(files) {
  const button = document.getElementById("footageAdd"); button.disabled = true;
  try {
    for (const file of files) {
      const kind = file.type.startsWith("image/") || /\.(png|jpg|jpeg|webp|bmp)$/i.test(file.name) ? "image" : "video";
      const status = beginMediaImport(file);
      try {
        const asset = await uploadAsset(kind, file, status.progress); asset.kind = kind;
        if (kind === "video" && !(asset.duration > 0)) throw new Error("Cannot read video duration. Use MP4 or WebM.");
        (project.background.mediaLibrary ||= []).push(asset);
        status.done(); refreshFootageControls(); scheduleSave();
      } catch (error) { status.failed(error.message); throw error; }
    }
    setAssetStatus(t("Ready. Drag media onto the timeline."), "success");
  } catch (error) { toast(error.message, "error"); setAssetStatus(error.message, "error"); }
  finally { button.disabled = false; document.getElementById("footageInput").value = ""; }
}
function initFootage() {
  initMediaBin();
  initVisualTracks();
  const editor = document.getElementById("footageClipEditor"), controls = document.getElementById("footageEffects");
  const field = (key, label, min, max, step, root, prefix) => {
    const wrapper = document.createElement("label"); wrapper.className = "field";
    const title = document.createElement("span"); title.textContent = t(label);
    const input = document.createElement("input"); input.id = `${prefix}-${key}`; input.type = "number";
    input.min = String(min); if (max !== null) input.max = String(max); input.step = String(step);
    input.setAttribute("aria-label", t(label)); wrapper.append(title, input); root.append(wrapper);
    input.addEventListener("change", () => {
      if (prefix === "clip") {
        const clip = selectedFootage(); if (!clip) return;
        clip[key] = Number(input.value); constrainFootage(clip); refreshFootageControls();
      } else {
        const value = Math.max(min, Math.min(max, Number(input.value) || 0));
        (project.background.effects ||= {})[key] = value; input.value = value;
      }
      footageChanged();
    });
  };
  footageClipFields.forEach(args => field(...args, editor, "clip"));
  footageEffects.forEach(([key, label, max]) => field(key, label, 0, max, 1, controls, "fx"));
  for (const key of ["color1", "color2"]) {
    const label = document.createElement("label"); label.className = "field";
    const span = document.createElement("span"); span.textContent = t(key === "color1" ? "Color 1" : "Color 2");
    const input = document.createElement("input"); input.type = "color"; input.id = `fx-${key}`;
    input.addEventListener("input", () => { (project.background.effects ||= {})[key] = input.value; scheduleSave(); });
    label.append(span, input); controls.append(label);
  }
  document.getElementById("footageEnable").addEventListener("change", event => { project.background.footageEnabled = event.target.checked; footageChanged(); });
  document.getElementById("footageAdd").addEventListener("click", () => document.getElementById("footageInput").click());
  document.getElementById("footageInput").addEventListener("change", event => importFootage([...event.target.files]));
  document.getElementById("footageSelect").addEventListener("change", event => { selectedFootageId = event.target.value; refreshFootageControls(); });
  document.getElementById("footageRemove").addEventListener("click", () => {
    project.background.clips = (project.background.clips || []).filter(c => c.id !== selectedFootageId);
    refreshFootageControls(); footageChanged();
  });
  document.getElementById("footageSplit").addEventListener("click", () => {
    const clip = selectedFootage(), time = currentPlaybackTime();
    if (!clip || time <= clip.start + .05 || time >= clip.end - .05) return toast(t("Move the playhead inside the selected clip."));
    const copy = clone(clip), p = (time - clip.start) / (clip.end - clip.start);
    copy.fadeIn = 0; clip.fadeOut = 0;
    copy.id = crypto.randomUUID(); copy.start = time;
    if (clip.asset.kind === "video") copy.in = clip.in + (time - clip.start) * clip.rate;
    for (const axis of ["x", "y", "zoom"]) {
      const value = clip[`${axis}Start`] * (1 - p) + clip[`${axis}End`] * p;
      clip[`${axis}End`] = value; copy[`${axis}Start`] = value;
    }
    clip.end = time; project.background.clips.push(copy); selectedFootageId = copy.id;
    refreshFootageControls(); footageChanged();
  });
  document.getElementById("footageDuplicate").addEventListener("click", () => {
    const clip = selectedFootage(); if (!clip) return;
    const copy = clone(clip), duration = copy.end - copy.start;
    copy.id = crypto.randomUUID(); copy.start = Math.max(...project.background.clips.map(c => c.end)); copy.end = copy.start + duration;
    project.background.clips.push(copy); selectedFootageId = copy.id; refreshFootageControls(); footageChanged();
  });
  const lane = document.getElementById("footageLane");
  lane.addEventListener("pointerdown", event => {
    if (event.button === 1) {
      event.preventDefault(); lane.setPointerCapture(event.pointerId);
      footageDrag = { pan: true, x: event.clientX, viewStart: timeline.viewStart }; timeline.follow = false; return;
    }
    if (event.button !== 0) return;
    const block = event.target.closest(".footage-block");
    if (!block) { const x = event.clientX - lane.getBoundingClientRect().left; seekTo(timeline.xToTime(x) + (project.timing.offset || 0)); return; }
    selectedFootageId = block.dataset.id; const clip = selectedFootage();
    document.getElementById("footageSection").open = true;
    refreshFootageControls(); lane.setPointerCapture(event.pointerId);
    footageDrag = { id: clip.id, x: event.clientX, original: clone(clip), mode: event.target.dataset.edge || "move" };
  });
  lane.addEventListener("pointermove", event => {
    if (!footageDrag) return;
    const delta = (event.clientX - footageDrag.x) / Math.max(1, lane.clientWidth) * timeline.viewSpan;
    if (footageDrag.pan) { timeline.setView(footageDrag.viewStart - delta, timeline.viewSpan); return; }
    const clip = selectedFootage(), original = footageDrag.original;
    if (!clip) return;
    if (footageDrag.mode === "move") {
      clip.start = Math.max(0, original.start + delta); clip.end = clip.start + original.end - original.start;
      clip.track = Math.max(0, Math.min((project.background.tracks?.length || 1)-1, Math.floor((event.clientY-lane.getBoundingClientRect().top)/38)));
    }
    else if (footageDrag.mode === "start") {
      const bound = original.asset.kind === "video" ? -original.in / original.rate : -original.start;
      const shift = Math.max(-original.start, Math.max(bound, Math.min(delta, original.end - original.start - .05)));
      clip.start = original.start + shift;
      if (original.asset.kind === "video") clip.in = original.in + shift * original.rate;
    } else clip.end = Math.max(clip.start + .05, original.end + delta);
    constrainFootage(clip);
    const element = lane.querySelector(`[data-id="${clip.id}"]`); if (element) { positionFootageBlock(element, clip); element.style.top = `${3+(clip.track||0)*38}px`; }
  });
  const release = () => { if (!footageDrag) return; footageDrag = null; refreshFootageControls(); footageChanged(); };
  lane.addEventListener("pointerup", release); lane.addEventListener("pointercancel", release); lane.addEventListener("lostpointercapture", release);
  lane.addEventListener("auxclick", event => { if (event.button === 1) event.preventDefault(); });
  lane.addEventListener("wheel", event => {
    event.preventDefault(); timeline.follow = false;
    if (event.ctrlKey) timeline.zoomAt(event.deltaY > 0 ? 1.18 : .85, event.clientX - lane.getBoundingClientRect().left);
    else timeline.setView(timeline.viewStart + (event.deltaX || event.deltaY) / 400 * timeline.viewSpan, timeline.viewSpan);
  }, { passive: false });
  lane.addEventListener("dblclick", () => { document.getElementById("footageSection").open = true; document.getElementById("footageSelect").focus(); });
  document.addEventListener("phrasync-language-change", () => {
    for (const [key, label] of [...footageClipFields, ...footageEffects]) {
      const input = document.getElementById(`${footageClipFields.some(a => a[0] === key) ? "clip" : "fx"}-${key}`);
      if (input) { input.closest("label").querySelector("span").textContent = t(label); input.setAttribute("aria-label", t(label)); }
    }
    refreshFootageControls();
  });
  refreshFootageControls();
}
function positionFootageBlock(element, clip) {
  const lane = document.getElementById("footageLane"), offset = project.timing.offset || 0;
  element.style.left = `${(clip.start - offset - timeline.viewStart) / timeline.viewSpan * lane.clientWidth}px`;
  element.style.width = `${Math.max(4, (clip.end - clip.start) / timeline.viewSpan * lane.clientWidth)}px`;
}
function renderFootageLane() {
  const lane = document.getElementById("footageLane"); if (!lane || !timeline || footageDrag && !footageDrag.pan) return;
  const clips = project.background.clips || [];
  lane.style.height = `${(project.background.tracks?.length || 1) * 38}px`;
  document.getElementById("timelineDock").style.minHeight = `${326 + ((project.background.tracks?.length || 1)-1)*38}px`;
  const key = `${timeline.viewStart}:${timeline.viewSpan}:${lane.clientWidth}:${selectedFootageId}:${JSON.stringify(clips.map(c => [c.id,c.start,c.end,c.track]))}`;
  if (key === footageViewKey) return; footageViewKey = key;
  lane.textContent = "";
  (project.background.tracks || ["V1"]).forEach((track,i) => {
    const label=document.createElement("span"); label.className="footage-track-label"; label.style.top=`${i*38+11}px`; label.textContent=track; lane.append(label);
  });
  if (!clips.length) { lane.textContent = t("Drag media here"); return; }
  const offset = project.timing.offset || 0;
  for (const clip of clips.filter(c => c.end - offset > timeline.viewStart && c.start - offset < timeline.viewStart + timeline.viewSpan)) {
    const block = document.createElement("div"); block.className = `footage-block${clip.id === selectedFootageId ? " selected" : ""}`;
    block.style.top = `${3 + (clip.track || 0) * 38}px`;
    block.dataset.id = clip.id; block.title = `${clip.asset.name} · ${clip.start.toFixed(2)}–${clip.end.toFixed(2)}s`;
    const name = document.createElement("span"); name.textContent = `V${(clip.track||0)+1} · ${clip.asset.kind === "visual" ? "◇" : clip.asset.kind === "image" ? "▧" : "▶"} ${clip.asset.name}`;
    const handles = ["start", "end"].map(edge => { const handle = document.createElement("i"); handle.dataset.edge = edge; handle.className = `footage-edge ${edge}`; return handle; });
    block.append(...handles, name); positionFootageBlock(block, clip); lane.append(block);
  }
}
