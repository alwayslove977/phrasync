"use strict";

// Encode the composited GPU canvas without an RGBA round trip to Python.
// Output is streamed with bounded queues; no full-video Blob is retained.
window.VFGPUEncoder = (() => {
  let encoder, writes, failure, endpoint;
  async function prepare(width, height, fps, bitrate, destination) {
    if (!window.VideoEncoder || !window.VideoFrame) return false;
    let config;
    for (const codec of ["avc1.640034", "avc1.640033", "avc1.640028", "avc1.420034"]) {
      const candidate = {codec, width, height, framerate: fps, bitrate,
        bitrateMode: "constant", hardwareAcceleration: "prefer-hardware",
        avc: {format: "annexb"}, latencyMode: "quality"};
      try { if ((await VideoEncoder.isConfigSupported(candidate)).supported) { config = candidate; break; } }
      catch (_) { /* Try another supported H.264 level before compatibility mode. */ }
    }
    if (!config) return false;
    endpoint = destination; writes = Promise.resolve(); failure = null;
    encoder = new VideoEncoder({
      output(chunk) {
        const data = new Uint8Array(chunk.byteLength); chunk.copyTo(data);
        writes = writes.then(async () => {
          if (failure) return;
          const response = await fetch(endpoint, {method: "POST", body: data});
          if (!response.ok) throw new Error(`Encoded frame transport failed: ${response.status}`);
        }).catch(error => { failure ||= error; });
      },
      error(error) { failure ||= error; }
    });
    encoder.configure(config);
    return true;
  }
  async function batch(frames, fps, first, keyInterval) {
    for (let i = 0; i < frames.length; i++) {
      if (failure) throw failure;
      const [time, amplitude, bands] = frames[i];
      window.__vfExportFrequencyData = bands; window.__vfExportSpectrum = bands.slice(0, 64);
      await VFExport.renderFrame(time, amplitude);
      const frame = new VideoFrame(VFExport.canvas(), {
        timestamp: Math.round((first+i)*1000000/fps), duration: Math.round(1000000/fps)});
      try { encoder.encode(frame, {keyFrame: (first+i)%keyInterval === 0}); }
      finally { frame.close(); }
    }
    // A bounded batch flush also propagates delayed device failures promptly.
    await encoder.flush(); await writes;
    if (failure) throw failure;
  }
  async function finish() {
    try { await encoder.flush(); await writes; if (failure) throw failure; }
    finally { if (encoder?.state !== "closed") encoder.close(); }
  }
  async function abort() {
    if (encoder && encoder.state !== "closed") encoder.close();
    await writes;
  }
  return {prepare, batch, finish, abort};
})();
