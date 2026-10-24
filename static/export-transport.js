"use strict";

// Raw RGBA stays the fast default. A lossless PNG is used only if browser
// pixel readback fails, never as a retry after an encoder has consumed a frame.
window.VFFrameTransport = (() => {
  let scratch, mode = "raw", fallbackReason = null;
  async function send(source, endpoint) {
    scratch ||= document.createElement("canvas");
    if (scratch.width !== source.width || scratch.height !== source.height) {
      scratch.width = source.width; scratch.height = source.height;
    }
    let body, headers;
    if (mode === "raw") {
      try {
        const ctx = scratch.getContext("2d", { willReadFrequently: true });
        if (!ctx) throw new Error("Canvas pixel reader is unavailable");
        ctx.clearRect(0, 0, scratch.width, scratch.height);
        ctx.drawImage(source, 0, 0);
        body = ctx.getImageData(0, 0, scratch.width, scratch.height).data;
        if (body.byteLength !== source.width * source.height * 4) throw new Error("Incomplete canvas pixels");
      } catch (error) {
        mode = "png";
        fallbackReason = error?.message || String(error);
      }
    }
    if (mode === "png") {
      body = await new Promise((resolve, reject) => {
        try { source.toBlob(blob => blob ? resolve(blob) : reject(new Error("Canvas PNG encoding failed")), "image/png"); }
        catch (error) { reject(error); }
      });
      headers = { "Content-Type": "image/png" };
    }
    const response = await fetch(endpoint, { method: "POST", body, headers });
    if (!response.ok) throw new Error(`Canvas frame transport failed: ${response.status}`);
    return { mode, fallbackReason };
  }
  return { send };
})();
