"use strict";

// Feed compressed packets in decode order. Retain a small look-ahead, never
// a whole decoded video in GPU memory. Unsupported sources use HTML video.
window.VFFootageDecoder = (() => {
  const readers = new Map();
  const bytes = text => Uint8Array.from(atob(text), c => c.charCodeAt(0));
  async function request(key, action, time=0) {
    const response = await fetch(`${window.__vfFootageFramesEndpoint}?id=${encodeURIComponent(key)}&action=${action}&time=${time}`);
    if (!response.ok || response.status === 204) throw new Error("Use browser video decoder");
    return response.json();
  }
  function close(reader) {
    if (reader.decoder.state !== "closed") reader.decoder.close();
    for (const frame of reader.frames) frame.close();
    reader.frames = [];
  }
  async function open(key, time) {
    if (readers.has(key)) close(readers.get(key));
    const config = await request(key, "open", time);
    config.description = bytes(config.description);
    config.hardwareAcceleration = "prefer-hardware";
    if (!(await VideoDecoder.isConfigSupported(config)).supported) throw new Error("Unsupported GPU video decoder");
    const reader = {frames: [], eof: false, last: time, target: time, failure: null};
    reader.decoder = new VideoDecoder({output(frame) {
      reader.frames.push(frame); reader.frames.sort((a,b)=>a.timestamp-b.timestamp);
      while (reader.frames.length > 1 && reader.frames[1].timestamp <= reader.target*1000000+1) reader.frames.shift().close();
    }, error(error) { reader.failure = error; }});
    reader.decoder.configure(config);
    readers.set(key, reader);
    while (readers.size > 8) { const oldest=readers.keys().next().value; close(readers.get(oldest)); readers.delete(oldest); }
    return reader;
  }
  async function frame(key, time) {
    if (!window.VideoDecoder || !window.__vfFootageFramesEndpoint) return null;
    let reader = readers.get(key);
    try {
      if (!reader || time < reader.last-.000001 || time-reader.last > 3) reader = await open(key, time);
      readers.delete(key); readers.set(key, reader);
      reader.last = time; reader.target = time;
      while (reader.frames.length > 1 && reader.frames[1].timestamp <= time*1000000+1) reader.frames.shift().close();
      const deadline = performance.now()+15000;
      while (!reader.eof && (!reader.frames.length || reader.frames.at(-1).timestamp <= time*1000000+1)) {
        if (reader.failure) throw reader.failure;
        if (performance.now()>deadline) throw new Error("Sequential footage decode timed out");
        const data = await request(key, "read");
        for (const packet of data.packets) reader.decoder.decode(new EncodedVideoChunk({...packet,data:bytes(packet.data)}));
        if (data.eof) { await reader.decoder.flush(); reader.eof = true; }
        else {
          while (reader.decoder.decodeQueueSize > 0) {
            if (reader.failure) throw reader.failure;
            if (performance.now()>deadline) throw new Error("Sequential footage decode timed out");
            await new Promise(resolve=>setTimeout(resolve,0));
          }
          await new Promise(resolve=>setTimeout(resolve,0));
        }
      }
      if (reader.failure) throw reader.failure;
      if (!reader.frames.length) throw new Error("No decoded footage frame");
      return reader.frames[0].clone();
    } catch (_) {
      if (reader) close(reader);
      readers.delete(key);
      return null;
    }
  }
  return {frame};
})();
