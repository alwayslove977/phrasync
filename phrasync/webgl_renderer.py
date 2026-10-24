from __future__ import annotations

import json
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
from .media import ffmpeg_exe
from .processes import background_flags
from .encoding import bitrate_bps, rate_control_args
from .diagnostics import log_event
from .footage import effects_enabled
from .audio_spectrum import SpectrumSource
from .storage import get_av_asset
from .frame_bridge import frame_bridge
from .hardware_encoding import can_use_nvenc, nvenc_args
from .footage_frames import footage_frame_bridge


ProgressCallback = Callable[[float, str], None]


def _browser_path() -> Path:
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
        reply = self.call("Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": True,
        })
        details = reply.get("exceptionDetails")
        if details:
            exception = details.get("exception") or {}
            raise RuntimeError("Export browser: " + str(exception.get("description")
                               or exception.get("value") or details.get("text") or "JavaScript evaluation failed"))
        result = reply.get("result", {})
        if result.get("subtype") == "error":
            raise RuntimeError(result.get("description") or "WebGL browser evaluation failed")
        return result.get("value")

    def close(self) -> None:
        self.socket.close()


def _needs_spectrum(project):
    bg = project.get("background") or {}
    settings = [(clip.get("asset") or {}).get("settings") or {} for clip in bg.get("clips") or []]
    return bool((bg.get("effects") or {}).get("spectrum", 0) > 0 or bg.get("sceneWave")
                or bg.get("visual") == "equalizer" or any(
                    spec.get("visual") == "equalizer" or spec.get("sceneWave") for spec in settings))


def _fallback_reason(project, frame_transform):
    if frame_transform is not None:
        return "single-pass flat text composition"
    if bitrate_bps(project) is not None:
        return "custom bitrate requested"
    if effects_enabled(project):
        return "shared footage and effects composition"
    if project.get("audioAssetId") and _needs_spectrum(project):
        return "offline audio spectrum"
    return None


def _encode_gpu_canvas(devtools, project, path, *, width, height, fps, frame_count,
                       envelope, progress=None, cancel_check=None):
    """Return false only when the hardware browser codec is unsupported."""
    audio = get_av_asset(project.get('audioAssetId')) if project.get('audioAssetId') else None
    start = float((project.get('exportRange') or {}).get('in', 0))
    spectrum = SpectrumSource(audio.path, fps, start_time=start) if audio and _needs_spectrum(project) else None
    rate = bitrate_bps(project)
    target = rate or int(max(2_000_000, width * height * fps * .14))
    started = time.monotonic()
    try:
        with path.open('wb') as output:
            def consume(data, index):
                if cancel_check and cancel_check():
                    raise RuntimeError('Render cancelled')
                output.write(data)
                # H.264 filler NAL units retain the user's requested CBR even
                # when a hardware encoder emits fewer bytes for a simple frame.
                missing = round((index + 1) * rate / (8 * fps)) - output.tell() if rate else 0
                if missing >= 6:
                    output.write(b'\x00\x00\x00\x01\x0c' + b'\xff' * (missing - 6) + b'\x80')
            with frame_bridge(_local_origin(project.get('__renderOrigin')), width, height,
                              consume, encoded=True) as (endpoint, state):
                supported = devtools.evaluate(f'VFGPUEncoder.prepare({width},{height},{fps},{target},{json.dumps(endpoint)})')
                if not supported:
                    return False
                log_event('info', 'render', f'GPU canvas H.264 encoder (hardware preferred): {width}x{height}, {fps} fps')
                try:
                    for first in range(0, frame_count, 16):
                        if cancel_check and cancel_check():
                            raise RuntimeError('Render cancelled')
                        end = min(frame_count, first + 16)
                        frames = [[start + index/fps, float(envelope[index]) if index < len(envelope) else 0,
                                   spectrum.read(index) if spectrum else []] for index in range(first, end)]
                        devtools.evaluate(f'VFGPUEncoder.batch({json.dumps(frames)},{fps},{first},{fps*2})')
                        if state['error'] or state['frames'] != end:
                            raise RuntimeError(state['error'] or f'GPU encoder returned {state["frames"]}/{end} frames')
                        if progress:
                            progress(.06+.82*end/frame_count, f'Rendering frame {end}/{frame_count} (GPU canvas encoder)')
                    devtools.evaluate('VFGPUEncoder.finish()')
                finally:
                    devtools.evaluate('VFGPUEncoder.abort()')
        log_event('info', 'render', f'GPU canvas encoding: {frame_count} frames in {time.monotonic()-started:.2f}s')
        return True
    finally:
        if spectrum:
            spectrum.close()


def _encode_canvas_ffmpeg(devtools, project, path, *, width, height, fps, frame_count,
                          envelope, progress=None, cancel_check=None, frame_transform=None):
    hardware = can_use_nvenc(width, height, fps)
    try:
        return _encode_canvas_stream(devtools, project, path, width=width, height=height, fps=fps,
            frame_count=frame_count, envelope=envelope, progress=progress, cancel_check=cancel_check,
            frame_transform=frame_transform, hardware=hardware)
    except HardwareEncoderError as error:
        log_event('warning', 'render', f'NVENC became unavailable; restarting the complete video pass with CPU: {error}')
        clean = dict(project); clean.pop('__renderOrigin', None)
        devtools.evaluate(f'VFExport.prepare({width},{height},{json.dumps(clean)})')
        return _encode_canvas_stream(devtools, project, path, width=width, height=height, fps=fps,
            frame_count=frame_count, envelope=envelope, progress=progress, cancel_check=cancel_check,
            frame_transform=frame_transform, hardware=False)


class HardwareEncoderError(RuntimeError):
    pass


def _encode_canvas_stream(devtools, project, path, *, width, height, fps, frame_count,
                          envelope, progress=None, cancel_check=None, frame_transform=None, hardware=False):
    """Lossless frame transport, bounded memory, no browser codec dependency."""
    started = time.monotonic()
    log_event("info", "render", f"FFmpeg canvas encoder: {width}x{height}, {fps} fps, bitrate={bitrate_bps(project) or 'CRF'}")
    audio = get_av_asset(project.get("audioAssetId")) if project.get("audioAssetId") else None
    start_time = float((project.get("exportRange") or {}).get("in", 0))
    spectrum = SpectrumSource(audio.path, fps, start_time=start_time) if audio and _needs_spectrum(project) else None
    png_reported = False
    codec_args = nvenc_args(project) if hardware else ['-c:v', 'libx264',
        '-preset', str(project.get('export', {}).get('preset', 'medium')), *rate_control_args(project)]
    log_event('info', 'render', 'Canvas video encoder: ' + ('NVIDIA NVENC' if hardware else 'CPU libx264'))
    with tempfile.TemporaryFile() as errors:
        encoder = subprocess.Popen([
            ffmpeg_exe(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s:v", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0", "-an",
            *codec_args, "-pix_fmt", "yuv420p",
            # Matroska's millisecond time base rounds 12/23/24 fps timestamps.
            # Keep exact frame ticks in the intermediate and stream-copy them.
            "-video_track_timescale", str(fps * 1024), "-f", "mp4", str(path),
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors, creationflags=background_flags())
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
                        "try{window.__vfExportFrequencyData=bands;window.__vfExportSpectrum=bands.slice(0,64);"
                        "await VFExport.renderFrame(time,amplitude);"
                        f"window.__vfTransport=await VFFrameTransport.send(VFExport.canvas(),{json.dumps(endpoint)});"
                        "}catch(error){throw new Error('Export frame at '+time.toFixed(3)+'s: '+(error?.stack||String(error)));}"
                        "}return window.__vfTransport;})()"
                    )
                    try:
                        transport = devtools.evaluate(script)
                    except RuntimeError:
                        if state['error']:
                            raise RuntimeError(state['error']) from None
                        raise
                    if isinstance(transport, dict) and transport.get('mode') == 'png' and not png_reported:
                        log_event('warning', 'render', 'Using lossless PNG compatibility transport after pixel readback failure: '
                                  + str(transport.get('fallbackReason') or 'unknown browser readback error'))
                        png_reported = True
                    if state['error'] or state['frames'] != batch_end:
                        raise RuntimeError(state['error'] or
                            f"Canvas frame was not received (received {state['frames']}/{batch_end}; "
                            f"timeline {start_time + batch_start / fps:.3f}s). See the export browser error in Diagnostics.")
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
        except Exception as error:
            failed_encoder = encoder.poll() not in (None, 0)
            if encoder.poll() is None:
                encoder.kill()
            encoder.wait(timeout=5)
            path.unlink(missing_ok=True)
            if hardware and failed_encoder and not (cancel_check and cancel_check()):
                errors.seek(0)
                raise HardwareEncoderError(errors.read().decode('utf-8', errors='replace') or str(error)) from error
            raise
        finally:
            if spectrum:
                spectrum.close()
            if encoder.stdin and not encoder.stdin.closed:
                encoder.stdin.close()


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
    encoded_path.unlink(missing_ok=True)

    clean_project = json.loads(json.dumps(project))
    clean_project.pop("__renderOrigin", None)
    clean_project["audio"] = None
    custom_bitrate = bitrate_bps(project)
    fallback_reason = _fallback_reason(project, frame_transform)
    bitrate = custom_bitrate or int(max(2_000_000, width * height * fps * 0.14))
    key_interval = max(1, fps * 2)

    with tempfile.TemporaryDirectory(prefix="phrasync-webgl-", ignore_cleanup_errors=True) as folder, \
            footage_frame_bridge(origin, project) as footage_endpoint:
        temp_dir = Path(folder)
        profile = temp_dir / "profile"
        download = temp_dir / "download"
        profile.mkdir()
        download.mkdir()
        flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags = subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(
            [
                str(browser), "--headless=new", "--hide-scrollbars", "--mute-audio",
                "--enable-webgl", "--enable-unsafe-swiftshader",
                f"--remote-debugging-port={port}", "--remote-allow-origins=*",
                f"--user-data-dir={profile}", f"--window-size={width},{height}", "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
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
            devtools.evaluate('window.__vfFootageFramesEndpoint=' + json.dumps(footage_endpoint))

            # The complete 3D composition, footage and offline spectrum can be
            # encoded directly on the GPU. Flat PIL typography still uses the
            # lossless canvas bridge; no text layer may be omitted for speed.
            if frame_transform is None:
                devtools.evaluate(f'VFExport.prepare({width},{height},{json.dumps(clean_project)})')
                try:
                    if _encode_gpu_canvas(devtools, project, encoded_path, width=width, height=height,
                            fps=fps, frame_count=frame_count, envelope=envelope,
                            progress=progress, cancel_check=cancel_check):
                        return 'h264-gpu'
                except Exception as error:
                    if cancel_check and cancel_check():
                        raise RuntimeError('Render cancelled') from error
                    log_event('warning', 'render', f'GPU canvas encoder unavailable; restarting lossless compatibility pass: {error}')
                encoded_path.unlink(missing_ok=True)

            setup = {
                "project": clean_project,
                "width": width,
                "height": height,
                "fps": fps,
                "startTime": float((project.get("exportRange") or {}).get("in", 0)),
                "frames": frame_count,
                "bitrate": bitrate,
                "ffmpeg": fallback_reason is not None,
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
                        reason = state.get("error") or fallback_reason or "browser H.264 unavailable"
                        log_event("info" if fallback_reason and not state.get("error") else "warning",
                                  "render", f"Using FFmpeg canvas export: {reason}")
                        # Prepare again after a browser codec error; keep the scene and dimensions intact.
                        devtools.evaluate("VFExport.prepare(" + str(width) + "," + str(height) + "," + json.dumps(clean_project) + ")")
                        _encode_canvas_ffmpeg(devtools, project, encoded_path, width=width, height=height,
                                              fps=fps, frame_count=frame_count, envelope=envelope,
                                              progress=progress, cancel_check=cancel_check, frame_transform=frame_transform)
                        return "mp4"
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
