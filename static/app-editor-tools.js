"use strict";

function initEditorTools() {
  const fileMenu = document.getElementById("projectMenu");
  fileMenu.addEventListener("click", event => { if (event.target.closest("button")) fileMenu.open = false; });
  document.addEventListener("pointerdown", event => { if (!fileMenu.contains(event.target)) fileMenu.open = false; });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") fileMenu.open = false;
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || document.querySelector("dialog[open]")) return;
    const id = { s: "saveProjectButton", o: "loadProjectButton", n: "resetProjectButton" }[event.key.toLowerCase()];
    if (id) { event.preventDefault(); document.getElementById(id).click(); }
  });
  document.addEventListener("click", async event => {
    const link = event.target.closest("a[data-external]");
    if (!link || !IS_DESKTOP_HOST) return;
    event.preventDefault();
    try {
      const bridge = window.pywebview?.api;
      if (!bridge?.open_external_url) throw new Error("Desktop links are not ready. Please try again.");
      const opened = await bridge.open_external_url(link.href);
      if (!opened) toast("Could not open your browser.", "error");
    } catch (error) { toast(error.message, "error"); }
  });
  initClipContextMenu();
}
function initClipContextMenu() {
  const lane = document.getElementById("footageLane");
  const menu = document.createElement("div"); menu.id = "clipContextMenu"; menu.className = "clip-context-menu";
  menu.hidden = true; menu.setAttribute("role", "dialog"); menu.setAttribute("aria-label", "Clip quick controls");
  document.body.append(menu);
  let contextId = null, contextTime = 0, opener = null;
  const close = () => { menu.hidden = true; };
  const current = () => (project.background.clips || []).find(c => c.id === contextId);
  const commit = () => { const clip = current(); if (!clip) return close(); constrainFootage(clip); refreshFootageControls(); footageChanged(); };
  const command = (label, handler, disabled = false) => {
    const button = document.createElement("button"); button.type = "button"; button.textContent = t(label); button.disabled = disabled;
    button.onclick = () => { if (!current()) return close(); selectedFootageId = contextId; handler(); close(); };
    menu.append(button);
  };
  const adjustment = (name, value, min, max, step, handler) => {
    const label = document.createElement("label"), title = document.createElement("span"); title.textContent = t(name);
    const slider = document.createElement("input"); slider.type = "range"; slider.min = min; slider.max = max; slider.step = step; slider.value = value;
    const number = document.createElement("input"); number.type = "number"; number.min = min; number.max = max; number.step = step; number.value = value;
    for (const input of [slider,number]) input.setAttribute("aria-label", t(name));
    const update = event => { const v = Math.max(min, Math.min(max, Number(event.target.value) || min)); slider.value = number.value = v; const clip = current(); if (clip) { handler(clip, v); commit(); } };
    slider.oninput = update; number.onchange = update;
    label.append(title, number, slider); menu.append(label);
  };
  lane.addEventListener("contextmenu", event => {
    const block = event.target.closest(".footage-block"); if (!block) return close();
    event.preventDefault(); contextId = block.dataset.id; selectedFootageId = contextId;
    opener = block; const clip = current(); if (!clip) return;
    contextTime = timeline.xToTime(event.clientX - lane.getBoundingClientRect().left) + (project.timing.offset || 0);
    refreshFootageControls(); menu.replaceChildren();
    const title = document.createElement("strong"); title.textContent = clip.asset.name; menu.append(title);
    command("Edit clip", () => { document.getElementById("footageSection").open = true; document.getElementById("clip-rate").focus(); });
    command("Split here", () => { seekTo(contextTime); document.getElementById("footageSplit").click(); }, contextTime <= clip.start + .05 || contextTime >= clip.end - .05);
    command("Split at playhead", () => document.getElementById("footageSplit").click(), currentPlaybackTime() <= clip.start + .05 || currentPlaybackTime() >= clip.end - .05);
    command("Duplicate clip", () => document.getElementById("footageDuplicate").click());
    command("Move to playhead", () => { const c = current(), length = c.end - c.start; c.start = Math.max(0, currentPlaybackTime()); c.end = c.start + length; commit(); });
    adjustment("Speed", clip.rate, .25, 4, .05, (c,v) => { c.rate = v; });
    adjustment("Zoom", clip.zoomStart, 1, 4, .01, (c,v) => { c.zoomStart = c.zoomEnd = v; });
    adjustment("Clip opacity", clip.opacity ?? 1, 0, 1, .01, (c,v) => { c.opacity = v; });
    adjustment("Transition in (s)", clip.fadeIn || 0, 0, 5, .05, (c,v) => { c.fadeIn=v; if(v>0) c.transition="fade"; });
    command("Reset pan & zoom", () => { Object.assign(current(), {zoomStart:1,zoomEnd:1,xStart:0,xEnd:0,yStart:0,yEnd:0}); commit(); });
    command("Remove clip", () => document.getElementById("footageRemove").click());
    menu.hidden = false;
    menu.style.left = `${Math.max(8, Math.min(event.clientX, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(event.clientY, innerHeight - menu.offsetHeight - 8))}px`;
    menu.querySelector("button:not(:disabled)")?.focus({preventScroll:true});
  });
  document.addEventListener("pointerdown", event => { if (!menu.contains(event.target)) close(); });
  document.addEventListener("keydown", event => {
    if (menu.hidden) return;
    if (event.key === "Escape") { event.preventDefault(); close(); opener?.focus?.(); }
    if (event.key === "Tab") {
      const fields = [...menu.querySelectorAll("button:not(:disabled),input")];
      const i = fields.indexOf(document.activeElement), next = (i + (event.shiftKey ? -1 : 1) + fields.length) % fields.length;
      event.preventDefault(); fields[next]?.focus();
    }
  });
  window.addEventListener("resize", close);
  document.addEventListener("wheel", event => { if (!menu.contains(event.target)) close(); }, {passive:true});
}
