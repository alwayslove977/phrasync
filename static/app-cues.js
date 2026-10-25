"use strict";

const CUE_PAGE_SIZE = 100;
let cueListPage = 0;
let cueListSelection = null;

function cueListText(en) {
  return typeof window !== "undefined" && typeof window.t === "function" ? window.t(en) : en;
}

function revealCueInList(id) {
  const index = project.cues.findIndex(cue => cue.id === id);
  if (index < 0) return;
  const page = Math.floor(index / CUE_PAGE_SIZE);
  if (page !== cueListPage) renderCueList({ page });
  const card = [...els.cueList.querySelectorAll(".cue-card")].find(item => item.dataset.id === id);
  card?.scrollIntoView({ block: "nearest" });
}

function cuePager(pageCount) {
  const nav = document.createElement("nav");
  nav.className = "timeline-tools cue-pagination";
  nav.setAttribute("aria-label", cueListText("Cue pages", "Pagine delle frasi"));
  Object.assign(nav.style, { position: "sticky", top: "0", zIndex: "2", flexWrap: "wrap",
    margin: "0 0 8px", padding: "8px 0", background: "var(--panel)" });
  const button = (label, action, disabled = false) => {
    const el = document.createElement("button");
    el.type = "button"; el.textContent = label; el.disabled = disabled;
    el.addEventListener("click", action); nav.append(el);
  };
  const go = page => { renderCueList({ page }); els.cueList.scrollTop = 0; };
  button(cueListText("Previous", "Precedente"), () => go(cueListPage - 1), cueListPage === 0);
  const label = document.createElement("span");
  label.textContent = `${cueListText("Page", "Pagina")} ${cueListPage + 1} / ${pageCount}`;
  label.setAttribute("aria-live", "polite");
  Object.assign(label.style, { alignSelf: "center", fontSize: "11px" });
  nav.append(label);
  button(cueListText("Next", "Successiva"), () => go(cueListPage + 1), cueListPage === pageCount - 1);
  const jump = document.createElement("input");
  jump.type = "number"; jump.min = "1"; jump.max = String(project.cues.length); jump.step = "1";
  jump.placeholder = cueListText("Cue #", "Frase n.");
  jump.setAttribute("aria-label", cueListText("Go to cue number", "Vai alla frase numero"));
  jump.style.width = "85px";
  const jumpTo = () => {
    if (!jump.value) return;
    const index = Math.min(project.cues.length - 1, Math.max(0, Math.trunc(Number(jump.value)) - 1));
    if (!Number.isFinite(index)) return;
    selectedCueId = project.cues[index].id;
    selectedWordIndex = 0; tapQueue = [];
    renderCueList({ page: Math.floor(index / CUE_PAGE_SIZE) });
    updateWordLabel(); revealCueInList(selectedCueId);
  };
  jump.addEventListener("change", jumpTo);
  jump.addEventListener("keydown", event => { if (event.key === "Enter") jumpTo(); });
  nav.append(jump);
  button(cueListText("Show selected", "Mostra selezionata"), () => revealCueInList(selectedCueId), !selectedCueId);
  return nav;
}

function renderCueList(options = {}) {
  const scrollTop = els.cueList.scrollTop || 0;
  normalizeCues();
  const pageCount = Math.max(1, Math.ceil(project.cues.length / CUE_PAGE_SIZE));
  const selectedIndex = project.cues.findIndex(cue => cue.id === selectedCueId);
  if (Number.isInteger(options.page)) cueListPage = options.page;
  else if (!options.preservePage && selectedCueId !== cueListSelection && selectedIndex >= 0) cueListPage = Math.floor(selectedIndex / CUE_PAGE_SIZE);
  cueListSelection = selectedCueId;
  cueListPage = Math.max(0, Math.min(pageCount - 1, cueListPage));
  els.cueList.textContent = "";
  if (pageCount > 1) els.cueList.append(cuePager(pageCount));
  const fragment = document.createDocumentFragment();
  const pageStart = cueListPage * CUE_PAGE_SIZE;
  project.cues.slice(pageStart, pageStart + CUE_PAGE_SIZE).forEach((cue, localIndex) => {
    const index = pageStart + localIndex;
    const card = document.createElement("article");
    card.className = `cue-card${cue.id === currentCueId ? " active" : ""}`
      + (cue.id === selectedCueId ? " selected" : "");
    card.dataset.id = cue.id;
    const number = document.createElement("button");
    number.type = "button";
    number.className = "cue-index";
    number.textContent = String(index + 1).padStart(2, "0");
    number.title = "Seek to cue";
    const content = document.createElement("div");
    content.className = "cue-content";
    const times = document.createElement("div");
    times.className = "cue-times";
    const start = document.createElement("input");
    start.type = "number"; start.min = "0"; start.step = ".01"; start.value = cue.start.toFixed(2); start.setAttribute("aria-label", "Cue start");
    const dash = document.createElement("span"); dash.textContent = "→";
    const end = document.createElement("input");
    end.type = "number"; end.min = "0"; end.step = ".01"; end.value = cue.end.toFixed(2); end.setAttribute("aria-label", "Cue end");
    times.append(start, dash, end);
    const text = document.createElement("textarea");
    text.className = "cue-text"; text.value = cue.text; text.rows = 2; text.setAttribute("aria-label", `Cue ${index + 1} lyric`);
    content.append(times, text);
    const remove = document.createElement("button");
    remove.type = "button"; remove.className = "cue-delete"; remove.textContent = "×"; remove.title = "Delete cue";
    card.append(number, content, remove);
    const duplicate = document.createElement("button");
    duplicate.type = "button"; duplicate.className = "cue-duplicate";
    duplicate.textContent = "⧉";
    duplicate.title = cueListText("Duplicate cue", "Duplica frase");
    duplicate.setAttribute("aria-label", duplicate.title);
    duplicate.addEventListener("click", event => { event.stopPropagation(); duplicateCue(cue.id); });
    card.append(duplicate);

    const select = () => {
      selectedCueId = cue.id;
      selectedWordIndex = 0;
      tapQueue = [];
      seekTo(cue.start + (project.timing.offset || 0));
      timeline?.focusTime(cue.start);
      updateWordLabel();
      $$(".cue-card", els.cueList).forEach(item => item.classList.toggle("selected", item.dataset.id === cue.id));
    };
    number.addEventListener("click", select);
    card.addEventListener("click", event => { if (!event.target.matches("input,textarea,button")) select(); selectedCueId = cue.id; });
    start.addEventListener("change", () => {
      cue.start = Math.max(0, Number(start.value) || 0);
      if (cue.end <= cue.start) cue.end = cue.start + .5;
      normalizeCues(); updateDurationUI(); renderCueList(); scheduleSave();
    });
    end.addEventListener("change", () => {
      cue.end = Math.max(cue.start + .05, Number(end.value) || cue.start + 2);
      updateDurationUI(); scheduleSave();
    });
    text.addEventListener("input", () => {
      cue.text = text.value;
      if (cue.id === currentCueId) renderLyric(true);
      scheduleSave();
    });
    remove.addEventListener("click", event => {
      event?.stopPropagation();
      project.cues = project.cues.filter(item => item.id !== cue.id);
      if (selectedCueId === cue.id) selectedCueId = project.cues[0]?.id || null;
      renderCueList(); updateDurationUI(); scheduleSave();
    });
    fragment.append(card);
  });
  els.cueList.append(fragment);
  els.cueList.scrollTop = scrollTop;
  els.cueCount.textContent = `${project.cues.length} cue${project.cues.length === 1 ? "" : "s"}`;
}

function duplicateCue(id = selectedCueId) {
  const source = project.cues.find(cue => cue.id === id);
  if (!source) return;
  const shift = source.end - source.start;
  const copy = { ...source, id: `cue-${crypto.randomUUID()}`, start: source.end,
    end: source.end + shift, manual: true,
    words: (source.words || []).map(word => ({ ...word, start: word.start + shift, end: word.end + shift })) };
  project.cues.push(copy); selectedCueId = copy.id; selectedWordIndex = 0; tapQueue = [];
  renderCueList(); updateDurationUI(); updateWordLabel(); timeline?.draw(); scheduleSave();
  const card = [...els.cueList.querySelectorAll(".cue-card")].find(item => item.dataset.id === copy.id);
  const text = card?.querySelector("textarea");
  text?.focus({ preventScroll: true }); text?.select();
}
document.addEventListener("phrasync-language-change", () => renderCueList({ page: cueListPage }));
async function createCuesFromLines(lines, replace) {
  lines = lines.map(line => line.trim()).filter(Boolean);
  if (!lines.length) return;
  let startAt = replace ? 0 : Math.max(0, ...project.cues.map(cue => cue.end));
  const availableDuration = replace ? projectDuration() : Math.max(lines.length * 3, 3);
  const slot = replace ? Math.max(.45, availableDuration / lines.length) : 3;
  const newCues = lines.map((text, index) => ({
    id: `cue-${Date.now()}-${index}`,
    start: startAt + index * slot,
    end: startAt + (index + 1) * slot - .03,
    text,
    words: [],
    manual: true
  }));
  project.cues = replace ? newCues : [...project.cues, ...newCues];
  normalizeCues();
  selectedCueId = newCues[0]?.id || selectedCueId;
  renderCueList(); updateDurationUI(); restartLyricAnimation(); scheduleSave();
  // Pasted and OCR'd text arrives with nothing but an even split across the
  // song. Snapping it to the detected vocal attacks is the whole point of the
  // tool, so it happens here rather than waiting to be asked.
  await runAutoAlign({ auto: true });
}
function nudgeSelected(delta) {
  const cue = project.cues.find(item => item.id === selectedCueId);
  if (!cue) return toast("Select a cue first.");
  const duration = cue.end - cue.start;
  cue.start = Math.max(0, cue.start + delta);
  cue.end = cue.start + duration;
  renderCueList(); seekTo(cue.start); scheduleSave();
}
