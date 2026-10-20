"use strict";

const customFontLoads = new Map();
const customFontReady = new Set();

function lyricFontStack(style = project.style) {
  const fallback = fontStacks[style.fontPreset] || fontStacks.impact;
  return style.fontAssetId && customFontReady.has(style.fontAssetId)
    ? `"Phrasync-${style.fontAssetId}", ${fallback}` : fallback;
}

async function ensureCustomFont(id = project.style.fontAssetId) {
  if (!id) return;
  if (!customFontLoads.has(id)) {
    const load = (async () => {
      const response = await fetch(`/media/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error("The project's custom font is missing. Please upload it again.");
      const face = new FontFace(`Phrasync-${id}`, await response.arrayBuffer());
      try { await face.load(); }
      catch (_) { throw new Error("This browser cannot load the custom font. Choose a browser-compatible TTF or OTF font."); }
      document.fonts.add(face);
      customFontReady.add(id);
    })();
    customFontLoads.set(id, load);
  }
  await customFontLoads.get(id);
}

function applyCustomFont() {
  const id = project.style.fontAssetId;
  if (!id || customFontReady.has(id) || customFontLoads.has(id)) return;
  ensureCustomFont(id).then(() => {
    if (project.style.fontAssetId === id) { applyStageStyle(); restartLyricAnimation(); }
  }).catch(error => toast(`${error.message} Preview uses a fallback font.`, "error"));
}

async function refreshFontLibrary() {
  const select = document.getElementById("fontLibrary");
  try {
    const result = await api("/api/fonts");
    select.replaceChildren(new Option(t("Choose a saved font…"), ""));
    for (const font of result.fonts) select.add(new Option(`${font.name} · ${font.family}`, font.id));
  } catch (error) { toast(error.message, "error"); }
}

document.getElementById("fontLibrary").addEventListener("focus", refreshFontLibrary);
document.getElementById("fontLibrary").addEventListener("change", async event => {
  const id = event.target.value;
  if (!id) return;
  try {
    const asset = await api(`/api/fonts/${encodeURIComponent(id)}/select`, { method: "POST" });
    await useCustomFont(asset);
  } catch (error) { toast(error.message, "error"); }
});
document.getElementById("resetCustomFont").addEventListener("click", () => {
  project.style.fontAssetId = null; project.style.fontName = null;
  els.fontPick.textContent = t("Upload TTF/OTF");
  applyStageStyle(); restartLyricAnimation(); scheduleSave();
});

async function useCustomFont(asset) {
  project.style.fontAssetId = asset.id; project.style.fontName = asset.name;
  els.fontPick.textContent = asset.name;
  scheduleSave();
  try {
    await ensureCustomFont(asset.id);
    if (project.style.fontAssetId !== asset.id) return;
    applyStageStyle(); restartLyricAnimation();
    setAssetStatus(`Custom font ready for preview and export: ${asset.name}`, "success");
  } catch (error) {
    if (project.style.fontAssetId !== asset.id) return;
    applyStageStyle(); restartLyricAnimation();
    setAssetStatus(`${asset.name} is saved for export, but this browser cannot preview it. Try a TTF or OTF font.`, "error");
  }
}

document.getElementById("clearLyricsButton").addEventListener("click", () => {
  const dialog = document.createElement("dialog");
  const message = document.createElement("p"); message.textContent = t("Remove all lyrics? Save your project first to keep them.");
  const cancel = document.createElement("button"); cancel.textContent = t("Cancel");
  const remove = document.createElement("button"); remove.textContent = t("Clear all lyrics");
  cancel.onclick = () => dialog.close();
  remove.onclick = () => {
    project.cues = []; selectedCueId = null; selectedWordIndex = 0; tapQueue = [];
    renderCueList(); restartLyricAnimation(); updateDurationUI(); scheduleSave(); dialog.close();
  };
  dialog.append(message, cancel, remove); document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove()); dialog.showModal(); cancel.focus();
});

Object.assign(ITALIAN, {
  "Choose a saved font…": "Scegli un font salvato…", "Use preset font": "Usa il font predefinito",
  "Clear all lyrics": "Elimina tutti i testi",
  "Remove all lyrics? Save your project first to keep them.": "Eliminare tutti i testi? Salva prima il progetto per conservarli.",
  "Import replaces the current lyrics, including the English demo. Timed files keep their supplied timing; use Auto-align only if needed.": "L'importazione sostituisce i testi attuali, inclusa la demo inglese. I file temporizzati mantengono i loro tempi; usa Auto-align solo se necessario."
});
