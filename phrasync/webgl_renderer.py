from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from websockets.sync.client import connect
from .config import ASSETS_DIR, discard, scratch_dir
from .media import ffmpeg_exe
from .processes import background_flags, track
from .encoding import bitrate_bps, rate_control_args
from .diagnostics import log_event
from .footage import effects_enabled
from .audio_spectrum import SpectrumSource
from .storage import get_av_asset
from .frame_bridge import frame_bridge


ProgressCallback = Callable[[float, str], None]

#: Architecture suffix used by the bundled ``chrome-headless-shell`` folder.
#: One bundle only carries the runtime matching its own architecture, so an
#: x86_64 build never picks up an arm64 runtime and the other way round.
_HOST_ARCH = "arm64" if platform.machine() == "arm64" else "x64"


def _bundled_browsers() -> list[Path]:
    """Browser runtimes shipped inside the application bundle.

    A bundled runtime makes the Odyssey export work on a Mac without Chrome or
    Edge installed. ``PHRASYNC_BROWSER`` always wins so a build can be pinned to
    a specific binary while debugging.
    """
    candidates: list[Path] = []
    override = os.environ.get("PHRASYNC_BROWSER")
    if override:
        candidates.append(Path(override).expanduser())
    browser_dir = os.environ.get("PHRASYNC_BROWSER_DIR")
    roots = [Path(browser_dir).expanduser()] if browser_dir else [ASSETS_DIR / "browser"]
    for root in roots:
        candidates += [
            root / "PhrasyncBrowser.app" / "Contents" / "MacOS" / "PhrasyncBrowser",
            root / "Google Chrome for Testing.app" / "Contents" / "MacOS" / "Google Chrome for Testing",
            root / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
            root / f"chrome-headless-shell-mac-{_HOST_ARCH}" / "chrome-headless-shell",
            root / "chrome-headless-shell",
        ]
    return candidates


def _browser_path() -> Path:
    for candidate in _bundled_browsers():
        if candidate.is_file():
            return candidate
    if os.environ.get("PHRASYNC_REQUIRE_BUNDLED_BROWSER") == "1":
        # Diagnostic switch used by the acceptance tests: proves the export never
        # silently falls back to a browser installed on the machine.
        raise RuntimeError("The bundled export browser is missing from this build.")
    candidates = (
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("microsoft-edge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError("Chrome or Edge is required to export Odyssey WebGL video.")


def browser_status() -> dict[str, Any]:
    """Describe where the export browser comes from, for health reporting."""
    for candidate in _bundled_browsers():
        if candidate.is_file():
            return {"available": True, "bundled": True, "path": str(candidate)}
    try:
        path = _browser_path()
    except RuntimeError:
        return {"available": False, "bundled": False, "path": ""}
    return {"available": True, "bundled": False, "path": str(path)}


def _free_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _local_origin(value: Any) -> str:
    parsed = urlparse(str(value or ""))
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The WebGL export origin must be the running local Phrasync server.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _target_socket(port: int) -> str:
    endpoint = f"http://127.0.0.1:{port}/json/list"
    for _ in range(100):
        try:
            with urllib.request.urlopen(endpoint, timeout=0.5) as response:
                targets = json.load(response)
            return next(item["webSocketDebuggerUrl"] for item in targets if item.get("type") == "page")
        except (OSError, StopIteration, KeyError):
            time.sleep(0.1)
    raise RuntimeError("The WebGL export browser did not become ready.")


class _DevTools:
    def __init__(self, url: str, port: int):
        self.socket = connect(url, origin=f"http://localhost:{port}", max_size=None)
        self.counter = 0

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        request_id = self.counter
        self.socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            reply = json.loads(self.socket.recv())
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                raise RuntimeError(f"Chrome {method}: {reply['error']}")
            return reply.get("result", {})

    def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        result = self.call("Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": True,
        }).get("result", {})
        if result.get("subtype") == "error":
            raise RuntimeError(result.get("description") or "WebGL browser evaluation failed")
        return result.get("value")

    def close(self) -> None:
        self.socket.close()


def _encode_canvas_ffmpeg(devtools, project, path, *, width, height, fps, frame_count,
                          envelope, progress=None, cancel_check=None, frame_transform=None):
    """Lossless frame transport, bounded memory, no browser codec dependency."""
    started = time.monotonic()
    log_event("info", "render", f"FFmpeg canvas encoder: {width}x{height}, {fps} fps, bitrate={bitrate_bps(project) or 'CRF'}")
    audio = get_av_asset(project.get("audioAssetId")) if project.get("audioAssetId") else None
    bg = project.get("background") or {}
    visual_settings = [(clip.get("asset") or {}).get("settings") or {} for clip in bg.get("clips") or []]
    needs_spectrum = (bg.get("effects") or {}).get("spectrum", 0) > 0 or bg.get("sceneWave") or bg.get("visual") == "equalizer" or any(
        spec.get("visual") == "equalizer" or spec.get("sceneWave") for spec in visual_settings)
    start_time = float((project.get("exportRange") or {}).get("in", 0))
    spectrum = SpectrumSource(audio.path, fps, start_time=start_time) if audio and needs_spectrum else None
    # A named log file instead of TemporaryFile: opening an anonymous temporary
    # file unlinks it immediately, which locked-down accounts refuse.
    error_log = scratch_dir() / f"phrasync-ffmpeg-{os.getpid()}-{int(time.monotonic() * 1e6)}.log"
    with open(error_log, "w+b") as errors:
        encoder = track(subprocess.Popen([
            ffmpeg_exe(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s:v", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
            "-preset", str(project.get("export", {}).get("preset", "medium")),
            *rate_control_args(project), "-pix_fmt", "yuv420p", "-f", "matroska", str(path),
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors, creationflags=background_flags()))
        try:
            def consume(data, index):
                if cancel_check and cancel_check():
                    raise RuntimeError("Render cancelled")
                if frame_transform:
                    data = frame_transform(data, start_time + index / fps)
                if len(data) != width * height * 4:
                    raise RuntimeError("Invalid transformed canvas frame size")
                encoder.stdin.write(data)

            with frame_bridge(_local_origin(project.get('__renderOrigin')), width, height, consume) as (endpoint, state):
                for batch_start in range(0, frame_count, 8):
                    if cancel_check and cancel_check():
                        raise RuntimeError("Render cancelled")
                    batch_end = min(frame_count, batch_start + 8)
                    frames = [[start_time + index / fps,
                               float(envelope[index]) if index < len(envelope) else 0.0,
                               spectrum.read(index) if spectrum else []]
                              for index in range(batch_start, batch_end)]
                    script = (
                        f"(async()=>{{const frames={json.dumps(frames)};for(const [time,amplitude,bands] of frames){{"
                        "window.__vfExportSpectrum=bands;await VFExport.renderFrame(time,amplitude);"
                        "const source=VFExport.canvas();"
                        "window.__vfRawCanvas ||= document.createElement('canvas');"
                        f"const c=window.__vfRawCanvas;if(c.width!=={width}||c.height!=={height}){{c.width={width};c.height={height};}}"
                        "const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(source,0,0,c.width,c.height);"
                        "const pixels=ctx.getImageData(0,0,c.width,c.height).data;"
                        f"const response=await fetch({json.dumps(endpoint)},{{method:'POST',body:pixels}});"
                        "if(!response.ok)throw new Error('Canvas frame transport failed: '+response.status);}})()"
                    )
                    try:
                        devtools.evaluate(script)
                    except RuntimeError:
                        if state['error']:
                            raise RuntimeError(state['error']) from None
                        raise
                    if state['error'] or state['frames'] != batch_end:
                        raise RuntimeError(state['error'] or 'Canvas frame was not received')
                    if progress:
                        progress(.06 + .82 * batch_end / frame_count,
                                 f"Rendering frame {batch_end}/{frame_count} (single-pass encoder)")
            encoder.stdin.close()
            if encoder.wait() != 0:
                errors.seek(0)
                raise RuntimeError(f"FFmpeg canvas export failed: {errors.read().decode('utf-8', errors='replace')}")
            elapsed = time.monotonic() - started
            log_event("info", "render", f"Single-pass canvas encoding: {frame_count} frames in {elapsed:.2f}s "
                      f"({frame_count / max(elapsed, .001):.1f} fps); flat lyrics={frame_transform is not None}")
        except Exception:
            if encoder.poll() is None:
                encoder.kill()
            encoder.wait(timeout=5)
            discard(path)
            raise
        finally:
            if spectrum:
                spectrum.close()
            if encoder.stdin and not encoder.stdin.closed:
                encoder.stdin.close()
    try:
        error_log.unlink()
    except OSError:
        pass  # the platform refused the delete; the file stays in the workspace


def render_webgl_video(
    project: dict[str, Any],
    encoded_path: Path,
    *,
    width: int,
    height: int,
    fps: int,
    frame_count: int,
    envelope: list[float],
    progress: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
    frame_transform=None,
) -> str:
    """Render the real Odyssey WebGL canvas through Chromium WebCodecs."""
    origin = _local_origin(project.get("__renderOrigin"))
    port = _free_port()
    browser = _browser_path()
    log_event("info", "render", f"Export browser: {browser} "
              f"(bundled={any(browser == item for item in _bundled_browsers())})")
    discard(encoded_path)

    clean_project = json.loads(json.dumps(project))
    clean_project.pop("__renderOrigin", None)
    clean_project["audio"] = None
    custom_bitrate = bitrate_bps(project)
    bitrate = custom_bitrate or int(max(2_000_000, width * height * fps * 0.14))
    key_interval = max(1, fps * 2)

    with tempfile.TemporaryDirectory(prefix="phrasync-webgl-", dir=scratch_dir(),
                                     ignore_cleanup_errors=True) as folder:
        temp_dir = Path(folder)
        profile = temp_dir / "profile"
        download = temp_dir / "download"
        profile.mkdir()
        download.mkdir()
        flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags = subprocess.CREATE_NO_WINDOW
        # chrome-headless-shell is headless by construction and rejects the
        # ``--headless=new`` switch. It also ships without the helper-app sandbox
        # profile, so its GPU process needs the sandbox switches below before
        # SwiftShader can create a WebGL2 context. The full runtime keeps the
        # platform's default sandbox.
        headless_shell = "headless-shell" in browser.name
        headless_flags = ["--no-sandbox", "--disable-gpu-sandbox"] if headless_shell else ["--headless=new"]
        process = track(subprocess.Popen(
            [
                str(browser), *headless_flags, "--hide-scrollbars", "--mute-audio",
                "--enable-webgl", "--enable-unsafe-swiftshader", "--no-first-run",
                "--disable-background-networking", "--disable-sync",
                f"--remote-debugging-port={port}", "--remote-allow-origins=*",
                f"--user-data-dir={profile}", f"--window-size={width},{height}", "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        ))
        devtools: _DevTools | None = None
        try:
            devtools = _DevTools(_target_socket(port), port)
            devtools.call("Page.enable")
            devtools.call("Runtime.enable")
            devtools.call("Browser.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": str(download), "eventsEnabled": True,
            })
            devtools.call("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
            })
            devtools.call("Page.navigate", {"url": origin})
            time.sleep(1.0)
            devtools.evaluate(
                "localStorage.setItem('phrasync.project.v1', "
                + json.dumps(json.dumps(clean_project)) + "); true"
            )
            devtools.call("Page.reload")

            ready = False
            for _ in range(120):
                ready = bool(devtools.evaluate(
                    "Boolean(window.VFSceneGL?.ready && window.VFExport && typeof project !== 'undefined')",
                    await_promise=False,
                ))
                if ready:
                    break
                time.sleep(0.1)
            if not ready:
                raise RuntimeError("Odyssey WebGL did not initialize in the export browser.")
            graphics = devtools.evaluate("""(() => {
              const canvas=document.getElementById('glCanvas');
              const gl=canvas?.getContext('webgl2') || canvas?.getContext('webgl');
              const debug=gl?.getExtension('WEBGL_debug_renderer_info');
              return debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : 'browser-selected renderer';
            })()""")
            log_event("info", "render", f"Export graphics: {graphics}")

            setup = {
                "project": clean_project,
                "width": width,
                "height": height,
                "fps": fps,
                "startTime": float((project.get("exportRange") or {}).get("in", 0)),
                "frames": frame_count,
                "bitrate": bitrate,
                "ffmpeg": frame_transform is not None or custom_bitrate is not None or effects_enabled(project),
                "keyInterval": key_interval,
                "envelope": envelope,
            }
            script = """
            (() => {
              const cfg = %s;
              window.__vfEncodeState = { progress: 0, done: false, error: null };
              (async () => {
                try {
                  await VFExport.prepare(cfg.width, cfg.height, cfg.project);
                  if (cfg.ffmpeg || !window.VideoEncoder || !window.VideoFrame) {
                    window.__vfEncodeState.fallback = true;
                    window.__vfEncodeState.done = true; return;
                  }
                  const encoderConfig = {
                    codec: 'avc1.640034', width: cfg.width, height: cfg.height,
                    bitrate: cfg.bitrate, framerate: cfg.fps,
                    avc: { format: 'annexb' }, latencyMode: 'quality'
                  };
                  let supported = false;
                  for (const codec of ['avc1.640034', 'avc1.640033', 'avc1.640028', 'avc1.420034']) {
                    encoderConfig.codec = codec;
                    try { if ((await VideoEncoder.isConfigSupported(encoderConfig)).supported) { supported = true; break; } }
                    catch (_) {}
                  }
                  if (!supported) {
                    window.__vfEncodeState.fallback = true;
                    window.__vfEncodeState.done = true; return;
                  }
                  const chunks = [];
                  const encoder = new VideoEncoder({
                    output(chunk) {
                      const bytes = new Uint8Array(chunk.byteLength);
                      chunk.copyTo(bytes);
                      chunks.push(bytes);
                    },
                    error(error) { window.__vfEncodeState.error = String(error); }
                  });
                  encoder.configure(encoderConfig);
                  const duration = Math.round(1000000 / cfg.fps);
                  for (let index = 0; index < cfg.frames; index += 1) {
                    if (window.__vfEncodeState.cancel) throw new Error('Render cancelled');
                    await VFExport.renderFrame(cfg.startTime + index / cfg.fps, cfg.envelope[index] || 0);
                    const frame = new VideoFrame(VFExport.canvas(), {
                      timestamp: Math.round(index * 1000000 / cfg.fps), duration
                    });
                    encoder.encode(frame, { keyFrame: index %% cfg.keyInterval === 0 });
                    frame.close();
                    while (encoder.encodeQueueSize > 10) {
                      await new Promise(resolve => setTimeout(resolve, 0));
                    }
                    window.__vfEncodeState.progress = (index + 1) / cfg.frames;
                    if (index %% 6 === 0) await new Promise(resolve => requestAnimationFrame(resolve));
                  }
                  await encoder.flush();
                  encoder.close();
                  if (window.__vfEncodeState.error) throw new Error(window.__vfEncodeState.error);
                  const link = document.createElement('a');
                  link.download = 'odyssey.h264';
                  link.href = URL.createObjectURL(new Blob(chunks, { type: 'video/h264' }));
                  document.body.append(link);
                  link.click();
                  window.__vfEncodeState.done = true;
                } catch (error) {
                  window.__vfEncodeState.error = error?.stack || String(error);
                  window.__vfEncodeState.done = true;
                }
              })();
              return true;
            })()
            """ % json.dumps(setup, separators=(",", ":"))
            devtools.evaluate(script, await_promise=False)

            while True:
                if cancel_check and cancel_check():
                    devtools.evaluate("window.__vfEncodeState.cancel = true", await_promise=False)
                    raise RuntimeError("Render cancelled")
                state = devtools.evaluate("window.__vfEncodeState", await_promise=False) or {}
                value = float(state.get("progress") or 0)
                if progress:
                    progress(0.06 + value * 0.82, f"Rendering WebGL frame {max(1, int(value * frame_count))}/{frame_count}")
                if state.get("done"):
                    if state.get("fallback") or state.get("error"):
                        reason = state.get("error") or ("custom bitrate requested" if custom_bitrate else "browser H.264 unavailable")
                        log_event("info" if custom_bitrate else "warning", "render", f"Using FFmpeg canvas export: {reason}")
                        # Prepare again after a browser codec error; keep the scene and dimensions intact.
                        devtools.evaluate("VFExport.prepare(" + str(width) + "," + str(height) + "," + json.dumps(clean_project) + ")")
                        _encode_canvas_ffmpeg(devtools, project, encoded_path, width=width, height=height,
                                              fps=fps, frame_count=frame_count, envelope=envelope,
                                              progress=progress, cancel_check=cancel_check, frame_transform=frame_transform)
                        return "matroska"
                    break
                time.sleep(0.25)

            downloaded = download / "odyssey.h264"
            for _ in range(120):
                partials = list(download.glob("*.crdownload"))
                if downloaded.exists() and downloaded.stat().st_size > 0 and not partials:
                    break
                time.sleep(0.1)
            if not downloaded.exists() or downloaded.stat().st_size == 0:
                raise RuntimeError("Chrome did not produce the encoded Odyssey video stream.")
            shutil.copyfile(downloaded, encoded_path)
            return "h264"
        finally:
            if devtools:
                devtools.close()
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)
