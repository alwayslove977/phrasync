"use strict";

// Custom font support for the font selector: the pick/upload bindings that feed
// it, the `/api/fonts` listing, and the FontFace previews behind every option.
// Split out of app.js so each fragment stays under the 400-line limit;
// loadCustomFonts() keeps its name because app.js calls it on boot and after a
// project load.

function bindFontControls() {
  els.fontPick.addEventListener("click", () => els.fontInput.click());
  els.fontInput.addEventListener("change", () => handleFontFile(els.fontInput.files[0]));
  els.fontPreset.addEventListener("change", () => {
    const option = els.fontPreset.selectedOptions[0];
    if (option && option.dataset.fontPath) {
      project.style.fontPath = option.dataset.fontPath;
    } else {
      delete project.style.fontPath;
    }
    applyStageStyle();
    scheduleSave();
  });
}

async function loadCustomFonts() {
  try {
    const response = await fetch("/api/fonts", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const select = els.fontPreset;
    const fonts = Array.isArray(data.fonts) ? data.fonts : [];

    // 清理旧的动态选项，保留原有 12 个预设。
    select.querySelectorAll("option[data-custom-font]").forEach(option => option.remove());

    const group = document.createElement("optgroup");
    group.label = "Custom fonts · ~/phrasync/fonts";
    for (const [index, font] of fonts.entries()) {
      const option = document.createElement("option");
      option.value = `custom:${font.filename}`;
      option.textContent = font.name || font.filename;
      option.dataset.customFont = "true";
      option.dataset.fontPath = font.filename;
      option.title = font.filename;

      const family = `PhrasyncCustomFont${index}`;
      try {
        const face = new FontFace(
          family,
          `url("/api/fonts/file/${encodeURIComponent(font.filename)}")`
        );
        await face.load();
        document.fonts.add(face);
        option.dataset.fontFamily = `"${family}"`;
      } catch (error) {
        console.warn("Could not load preview font:", font.filename, error);
      }
      group.appendChild(option);
    }
    if (fonts.length) select.appendChild(group);

    if (project.style.fontPath) {
      const value = `custom:${project.style.fontPath}`;
      if ([...select.options].some(option => option.value === value)) {
        select.value = value;
      }
    }
  } catch (error) {
    console.warn("Could not load custom fonts:", error);
  }
}
