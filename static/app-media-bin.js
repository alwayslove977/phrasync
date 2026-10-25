"use strict";

// Library assets are separate from clip instances: importing never changes the edit.
const mediaImports = new Map();
let mediaBinSignature = "";
function libraryAssets() {
  const bg = project.background, library = bg.mediaLibrary ||= [];
  // Older local projects keep their footage and gain a reusable media bin.
  for (const clip of bg.clips || []) if (!library.some(a => a.id === clip.asset.id)) library.push(clone(clip.asset));
  return library;
}
function addMediaClip(assetId, time = currentPlaybackTime(), track = 0) {
  const asset = libraryAssets().find(a => a.id === assetId); if (!asset) return;
  if (!project.background.tracks?.length) project.background.tracks = ["V1"];
  track = Math.max(0, Math.min(project.background.tracks.length-1, track));
  const start = Math.max(0, Number(time) || 0);
  const clip = { id: crypto.randomUUID(), asset: clone(asset), start, end: start + (asset.duration || 5), in: 0, rate: 1,
    zoomStart: 1, zoomEnd: 1, xStart: 0, yStart: 0, xEnd: 0, yEnd: 0, track, opacity:1, fadeIn:0, fadeOut:0, transition:"cut" };
  (project.background.clips ||= []).push(clip); selectedFootageId = clip.id;
  project.background.footageEnabled = true;
  refreshFootageControls(); footageChanged();
  if (asset.kind !== "visual") VFMedia.preload?.(asset);
}
function beginMediaImport(file) {
  const id = crypto.randomUUID(), item = { name: file.name, percent: 0, phase: "upload", error: null };
  mediaImports.set(id, item); refreshMediaBin();
  const status = document.getElementById("footageImportStatus");
  const update = () => {
    status.hidden = false;
    status.textContent = `${item.name} · ${item.phase === "checking" ? t("Checking media…") : item.percent + "%"}`;
    const card = document.getElementById(`import-${id}`);
    if (card) {
      card.querySelector("progress").value = item.percent;
      card.querySelector("small").textContent = item.error || (item.phase === "checking" ? t("Checking media…") : item.percent + "%");
    }
  };
  update();
  return {
    progress: (percent, phase) => { item.percent = percent; item.phase = phase; update(); },
    done: () => { mediaImports.delete(id); status.hidden = true; mediaBinSignature = ""; },
    failed: message => { item.error = message; update(); }
  };
}
function refreshMediaBin() {
  const bin = document.getElementById("footageBin"); if (!bin) return;
  const assets = libraryAssets();
  const key = JSON.stringify([assets.map(a => [a.id,a.name]), [...mediaImports.keys()]]);
  if (key === mediaBinSignature) return; mediaBinSignature = key;
  bin.replaceChildren();
  if (!assets.length && !mediaImports.size) {
    const hint = document.createElement("span"); hint.className = "media-bin-empty";
    hint.textContent = t("Drop images or videos here"); bin.append(hint);
  }
  for (const asset of assets) {
    const card = document.createElement("article"); card.className = "media-card"; card.draggable = true;
    card.dataset.assetId = asset.id; card.title = asset.name;
    const preview = document.createElement(asset.kind === "image" ? "img" : "span"); preview.className = "media-thumb";
    if (asset.kind === "image") { preview.src = asset.url; preview.loading = "lazy"; preview.alt = ""; }
    else preview.textContent = asset.kind === "visual" ? "◇" : "▶"; // Avoid decoding large files for bin thumbnails.
    const name = document.createElement("strong"); name.textContent = asset.name;
    const meta = document.createElement("small"); meta.textContent = `${asset.kind.toUpperCase()} · ${asset.duration ? asset.duration.toFixed(1) + "s · " : ""}${formatByteCount(asset.size || 0)}`;
    const add = document.createElement("button"); add.type = "button"; add.textContent = "+"; add.title = t("Add at playhead"); add.setAttribute("aria-label", t("Add at playhead"));
    add.onclick = () => addMediaClip(asset.id);
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.title = t("Remove from bin"); remove.setAttribute("aria-label", t("Remove from bin"));
    remove.onclick = () => {
      // Removing a library entry never removes an existing clip or the original file.
      if ((project.background.clips || []).some(c => c.asset.id === asset.id)) return toast(t("This media is used on the timeline. Remove its clips first; original files are kept."));
      project.background.mediaLibrary = libraryAssets().filter(a => a.id !== asset.id);
      refreshMediaBin(); scheduleSave();
    };
    card.append(preview, name, meta, add, remove);
    card.addEventListener("dragstart", event => {
      event.dataTransfer.setData("application/x-phrasync-media", asset.id); event.dataTransfer.effectAllowed = "copy";
    });
    card.addEventListener("dblclick", () => addMediaClip(asset.id)); bin.append(card);
  }
  for (const [id, item] of mediaImports) {
    const card = document.createElement("article"); card.className = "media-card importing"; card.id = `import-${id}`;
    const name = document.createElement("strong"); name.textContent = item.name;
    const progress = document.createElement("progress"); progress.max = 100; progress.value = item.percent;
    const state = document.createElement("small"); state.textContent = item.error || (item.phase === "checking" ? t("Checking media…") : item.percent + "%");
    card.append(name, progress, state); bin.append(card);
  }
}
function initMediaBin() {
  const bin = document.getElementById("footageBin"), lane = document.getElementById("footageLane");
  const accepts = event => [...event.dataTransfer.types].some(type => type === "Files" || type === "application/x-phrasync-media");
  for (const target of [bin, lane]) {
    target.addEventListener("dragover", event => { if (!accepts(event)) return; event.preventDefault(); event.dataTransfer.dropEffect = "copy"; target.classList.add("drop-active"); });
    target.addEventListener("dragleave", () => target.classList.remove("drop-active"));
    target.addEventListener("drop", async event => {
      if (!accepts(event)) return; event.preventDefault(); target.classList.remove("drop-active");
      if (event.dataTransfer.files.length) { await importFootage([...event.dataTransfer.files]); return; }
      const id = event.dataTransfer.getData("application/x-phrasync-media");
      if (target === lane && id) {
        const x = event.clientX - lane.getBoundingClientRect().left;
        const track = Math.min((project.background.tracks?.length || 1) - 1, Math.max(0, Math.floor((event.clientY - lane.getBoundingClientRect().top)/38)));
        addMediaClip(id, timeline.xToTime(x) + (project.timing.offset || 0), track);
      }
    });
  }
  initNumericSliders();
  document.addEventListener("phrasync-language-change", () => { mediaBinSignature = ""; refreshMediaBin(); });
}

// Keep the existing precise inputs and their handlers; sliders drive that same path.
function syncNumericSliders() {
  for (const input of document.querySelectorAll('input[type="number"]')) {
    if (!input.id || !input.closest("label.field, .two-columns, .control-grid")) continue;
    let slider = document.getElementById(`${input.id}-slider`);
    if (!slider) {
      slider = document.createElement("input"); slider.type = "range"; slider.id = `${input.id}-slider`;
      slider.className = "numeric-slider"; slider.setAttribute("aria-label", input.getAttribute("aria-label") || input.id);
      input.insertAdjacentElement("afterend", slider);
      slider.addEventListener("input", () => {
        input.value = slider.value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
      input.addEventListener("input", () => { slider.value = input.value; });
    }
    slider.min = input.min || "0";
    slider.max = input.max || String(Math.max(100, Number(input.value) || 0, projectDuration(), selectedFootage()?.asset.duration || 0));
    slider.step = input.step && input.step !== "any" ? input.step : ".01";
    slider.value = input.value; slider.disabled = input.disabled;
    slider.style.setProperty("--range-fill", `${Math.max(0, Math.min(100, (Number(slider.value) - Number(slider.min)) / Math.max(.001, Number(slider.max) - Number(slider.min)) * 100))}%`);
  }
}
function initNumericSliders() {
  let pending = false;
  const schedule = () => { if (pending) return; pending = true; requestAnimationFrame(() => { pending = false; syncNumericSliders(); }); };
  new MutationObserver(records => { if (records.some(r => [...r.addedNodes].some(n => n.nodeType === 1 && (n.matches?.('input[type="number"]') || n.querySelector?.('input[type="number"]'))))) schedule(); }).observe(document.body, { childList: true, subtree: true });
  document.addEventListener("change", schedule);
  schedule();
}
