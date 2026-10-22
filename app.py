from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import platform
import re
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import uvicorn
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from phrasync import APP_NAME, APP_VERSION
from phrasync.cuda import configure_cuda_paths, cuda_diagnostics
from phrasync.diagnostics import install_exception_hooks, log_event, log_exception, support_report

CUDA_PATHS = configure_cuda_paths()

from phrasync.config import (
    ASSETS_DIR,
    DEFAULT_HOST,
    DEFAULT_PORT,
    PROJECTS_DIR,
    STATIC_DIR,
    UPLOADS_DIR,
    WORKSPACE,
)
from phrasync.align import align_cues, alignment_stats, estimate_offset
from phrasync.audio_analysis import AnalysisUnavailable, analyze_audio
from phrasync.font_utils import font_status, custom_font_catalog
from phrasync.jobs import manager
from phrasync.desktop_export import DesktopExportBridge
from phrasync.folder_picker import browser_folder_picker, available as folder_picker_available, FolderPickerUnavailable, FolderPickerBusy
from phrasync.media import ffmpeg_exe, probe_duration
from phrasync.ocr import OCRUnavailable, capability_status as ocr_status, ocr_image
from phrasync.qa import preflight_project
from phrasync.storage import delete_asset, get_asset, get_av_asset, list_assets, store_stream, store_chunks, store_path
from phrasync.store_updates import StoreUpdateUnavailable, check_updates, install_updates, package_identity, bind_window, update_progress, previous_update
from phrasync.server import (
    available_port,
    browser_host,
    install_windows_transport_error_filter,
    instance_url,
)
from phrasync.settings import apply_saved_settings, hf_token_status, remove_hf_token, save_hf_token
from phrasync.subtitles import (
    cues_to_ass,
    cues_to_enhanced_lrc,
    cues_to_lrc,
    cues_to_srt,
    cues_to_vtt,
    parse_lyrics_file,
)
from phrasync.transcribe import (
    TranscriptionUnavailable,
    capability_status as transcription_status,
    transcribe_audio,
)

apply_saved_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    install_windows_transport_error_filter(asyncio.get_running_loop())
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def log_server_errors(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        log_exception(f"http {request.url.path}", exc)
        raise
    if response.status_code >= 500:
        log_event("error", "http", f"{request.method} {request.url.path} returned {response.status_code}")
    return response


server: uvicorn.Server | None = None
desktop_export = DesktopExportBridge()
class RevalidatingStatic(StaticFiles):
    """Serve editor assets with must-revalidate.

    Without it a browser happily keeps a cached app.js after an update and the
    editor silently runs old code against new markup, which looks like a bug in
    the app rather than a stale file. ETags keep the revalidation cheap.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.mount("/static", RevalidatingStatic(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=UPLOADS_DIR), name="media")
app.mount("/bundled", StaticFiles(directory=ASSETS_DIR), name="bundled")


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    # Both the document and every asset URL change with the app version. An
    # in-place Store update must never combine yesterday's HTML with today's
    # JavaScript (which can stop all button handlers before they are bound).
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = re.sub(
        r'((?:src|href)="/static/[^"?]+)(")',
        lambda match: f"{match.group(1)}?v={APP_VERSION}{match.group(2)}",
        html,
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        ffmpeg = ffmpeg_exe()
        ffmpeg_ok = True
    except Exception as exc:
        ffmpeg = str(exc)
        ffmpeg_ok = False
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "workspace": str(WORKSPACE),
        "ffmpeg": {"available": ffmpeg_ok, "path": ffmpeg},
        "ocr": ocr_status(),
        "transcription": transcription_status(),
        "fonts": font_status(),
        "cudaPaths": CUDA_PATHS,
        "gpu": cuda_diagnostics(),
    }


@app.get("/api/instance")
def instance() -> dict[str, str]:
    """Lightweight identity check used by the cross-platform launcher."""
    return {"app": APP_NAME, "version": APP_VERSION}


@app.get("/api/store-updates/status")
def store_update_status(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    return {"version": APP_VERSION, "packaged": bool(package_identity()), "previous_update": previous_update()}


@app.get("/api/store-updates/progress")
def store_update_progress(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    return update_progress()


@app.post("/api/store-updates/check")
async def store_update_check(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    _require_same_origin(request)
    try:
        result = await check_updates()
    except StoreUpdateUnavailable as exc:
        log_event("warning", "updates", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    log_event("info", "updates", "Store update available" if result["available"] else "Store app up to date")
    return result


@app.post("/api/store-updates/install")
async def store_update_install(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    _require_same_origin(request)
    try:
        result = await install_updates()
    except StoreUpdateUnavailable as exc:
        log_event("error", "updates", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    log_event("info", "updates", f"Store installation state: {result['state']}")
    return result


@app.get("/api/diagnostics", response_class=PlainTextResponse)
def diagnostics_report(request: Request) -> PlainTextResponse:
    _require_local_request(request)
    return PlainTextResponse(support_report(), headers={"Cache-Control": "no-store"})


@app.post("/api/diagnostics/events")
def diagnostics_event(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, bool]:
    _require_local_request(request)
    level = str(payload.get("level") or "info")
    category = str(payload.get("category") or "frontend")
    message = str(payload.get("message") or "")
    if not message or len(message) > 4000:
        raise HTTPException(status_code=400, detail="Invalid diagnostic event")
    log_event(level, category, message)
    return {"recorded": True}


def _require_local_request(request: Request) -> None:
    try:
        is_local = ipaddress.ip_address(request.client.host).is_loopback if request.client else False
    except ValueError:
        is_local = False
    if not is_local:
        raise HTTPException(status_code=403, detail="Local settings are only available on this computer")


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin", "")
    expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if origin != expected:
        raise HTTPException(status_code=403, detail="This action must be started in Phrasync")


@app.post("/api/shutdown")
def shutdown(request: Request) -> dict[str, bool]:
    """Gracefully stop a locally launched server without killing a process."""
    _require_local_request(request)
    if server is None:
        raise HTTPException(status_code=409, detail="This server is not managed by the launcher")
    server.should_exit = True
    return {"stopping": True}


@app.get("/api/settings")
def settings_status(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    return {"huggingFace": hf_token_status(), "app": APP_NAME, "version": APP_VERSION}


@app.put("/api/settings/hugging-face")
def update_hugging_face_settings(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _require_local_request(request)
    try:
        return {"huggingFace": save_hf_token(str(payload.get("token") or ""))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/settings/hugging-face")
def delete_hugging_face_settings(request: Request) -> dict[str, Any]:
    _require_local_request(request)
    return {"huggingFace": remove_hf_token()}


@app.get("/api/assets")
def assets() -> dict[str, Any]:
    return {"assets": list_assets()}


@app.get("/api/fonts")
def custom_fonts() -> dict[str, Any]:
    return {"fonts": [{k: v for k, v in font.items() if k != "path"}
                      for font in custom_font_catalog().values()]}


@app.post("/api/fonts/{font_id}/select")
def select_custom_font(font_id: str) -> dict[str, Any]:
    font = custom_font_catalog().get(font_id)
    if not font:
        raise HTTPException(status_code=404, detail="Font not found. Refresh the saved font list.")
    return store_path("font", font["path"], font["name"]).public()


@app.post("/api/assets/{kind}")
def upload_asset(kind: str, file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        asset = store_stream(kind, file.filename or "asset", file.file)
        result = asset.public()
        if kind in {"audio", "video"}:
            result["duration"] = probe_duration(Path(asset.path))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc
    finally:
        file.file.close()


@app.delete("/api/assets/{asset_id}")
def remove_asset(asset_id: str) -> dict[str, bool]:
    return {"deleted": delete_asset(asset_id)}


@app.post("/api/assets/{kind}/stream")
async def upload_asset_stream(kind: str, request: Request, filename: str) -> dict[str, Any]:
    try:
        content_length = request.headers.get("content-length")
        asset = await store_chunks(kind, filename, request.stream(), int(content_length) if content_length else None)
        result = asset.public()
        if kind in {"audio", "video"}:
            result["duration"] = await run_in_threadpool(probe_duration, Path(asset.path))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail="Unable to save the import. Check available disk space and folder access.") from exc


@app.post("/api/ocr")
async def run_ocr(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    asset = get_asset(payload.get("assetId"), "image")
    if not asset:
        raise HTTPException(status_code=404, detail="OCR image asset not found")
    try:
        return await run_in_threadpool(
            ocr_image, Path(asset.path), str(payload.get("language", "auto"))
        )
    except OCRUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc


@app.post("/api/transcribe")
async def run_transcription(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    asset = get_av_asset(payload.get("assetId"))
    if not asset:
        raise HTTPException(status_code=404, detail="Audio or video source not found")
    try:
        result = await run_in_threadpool(
            transcribe_audio,
            Path(asset.path),
            str(payload.get("model", "base")),
            str(payload.get("language", "auto")),
            bool(payload.get("vadFilter", False)),
            None,
            None,
            payload.get("languageSpans") or None,
        )
        if payload.get("align", True):
            try:
                analysis = await run_in_threadpool(analyze_audio, Path(asset.path), True)
                aligned = await run_in_threadpool(align_cues, result["cues"], analysis)
                result["cues"] = aligned["cues"]
                result["alignment"] = aligned["report"]
                result["alignmentStats"] = alignment_stats(aligned["cues"], analysis)
            except Exception as exc:  # alignment is a bonus pass, never fatal
                result["alignment"] = {"error": str(exc)}
        return result
    except TranscriptionUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc


@app.post("/api/transcriptions")
def create_transcription_job(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    asset = get_av_asset(payload.get("assetId"))
    if not asset:
        raise HTTPException(status_code=404, detail="Audio or video source not found")
    job = manager.create_transcription(
        Path(asset.path),
        str(payload.get("model", "base")),
        str(payload.get("language", "auto")),
        bool(payload.get("vadFilter", False)),
        bool(payload.get("align", True)),
        payload.get("languageSpans") or None,
    )
    return JSONResponse(job.public(), status_code=202)


@app.get("/api/transcriptions/{job_id}")
def get_transcription_job(job_id: str) -> dict[str, Any]:
    job = manager.get(job_id)
    if not job or job.kind != "transcription":
        raise HTTPException(status_code=404, detail="Transcription job not found")
    return job.public()


@app.post("/api/transcriptions/{job_id}/cancel")
def cancel_transcription(job_id: str) -> dict[str, bool]:
    job = manager.get(job_id)
    if not job or job.kind != "transcription":
        raise HTTPException(status_code=404, detail="Transcription job not found")
    return {"cancelled": manager.cancel(job_id)}


@app.post("/api/analyze")
async def analyze(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    asset = get_av_asset(payload.get("assetId"))
    if not asset:
        raise HTTPException(status_code=404, detail="Audio or video source not found")
    try:
        return await run_in_threadpool(
            analyze_audio, Path(asset.path), not bool(payload.get("refresh"))
        )
    except AnalysisUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.post("/api/align")
async def align(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    cues = payload.get("cues") or []
    if not cues:
        raise HTTPException(status_code=400, detail="No cues to align")
    analysis = payload.get("analysis")
    if not analysis:
        asset = get_av_asset(payload.get("assetId"))
        if not asset:
            raise HTTPException(status_code=400, detail="Provide analysis data or an audio/video assetId")
        analysis = await run_in_threadpool(analyze_audio, Path(asset.path), True)
    options = payload.get("options") or {}
    result = await run_in_threadpool(
        align_cues,
        cues,
        analysis,
        offset=options.get("offset"),
        snap_words=bool(options.get("snapWords", True)),
        word_window=float(options.get("wordWindow", 0.14)),
        word_strength=float(options.get("wordStrength", 0.85)),
        snap_phrases=bool(options.get("snapPhrases", False)),
        phrase_grid=str(options.get("phraseGrid", "beat")),
        auto_offset=bool(options.get("autoOffset", True)),
    )
    result["stats"] = alignment_stats(result["cues"], analysis)
    return result


@app.post("/api/align/offset")
async def align_offset(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    cues = payload.get("cues") or []
    analysis = payload.get("analysis") or {}
    if not analysis:
        asset = get_av_asset(payload.get("assetId"))
        if not asset:
            raise HTTPException(status_code=400, detail="Provide analysis data or an audio/video assetId")
        analysis = await run_in_threadpool(analyze_audio, Path(asset.path), True)
    return await run_in_threadpool(estimate_offset, cues, analysis.get("onsets") or [])


@app.post("/api/lyrics/import")
def import_lyrics(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    asset = get_asset(payload.get("assetId"), "lyrics")
    if not asset:
        raise HTTPException(status_code=404, detail="Lyrics asset not found")
    try:
        cues = parse_lyrics_file(Path(asset.path), duration=payload.get("duration"))
        return {"cues": cues}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse lyrics: {exc}") from exc


@app.post("/api/lyrics/export/{format_name}")
def export_lyrics(format_name: str, payload: dict[str, Any] = Body(...)):
    cues = payload.get("cues") or []
    if format_name == "srt":
        return PlainTextResponse(cues_to_srt(cues), media_type="application/x-subrip")
    if format_name == "lrc":
        return PlainTextResponse(cues_to_lrc(cues), media_type="text/plain")
    if format_name == "vtt":
        return PlainTextResponse(cues_to_vtt(cues), media_type="text/vtt")
    if format_name == "elrc":
        return PlainTextResponse(cues_to_enhanced_lrc(cues), media_type="text/plain")
    if format_name == "ass":
        # Carries the per-word timing into Aegisub, mpv, ffmpeg and the NLEs.
        return PlainTextResponse(
            cues_to_ass(cues, payload.get("style") or {}, payload.get("canvas") or {}),
            media_type="text/x-ssa",
        )
    raise HTTPException(
        status_code=400,
        detail="Supported lyric formats: srt, vtt, lrc, elrc, ass",
    )


@app.post("/api/preflight")
def preflight(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    project = payload.get("project", payload)
    return preflight_project(project).public()


@app.get("/api/export-folder")
def export_folder_status(request: Request) -> dict[str, Any]:
    _require_local_folder_request(request)
    attached = desktop_export._window is not None
    return {"available": attached or folder_picker_available(),
            "directory": desktop_export.get_selected_render_directory() if attached else browser_folder_picker.selected()}


@app.post("/api/export-folder/choose")
async def choose_browser_export_folder(request: Request) -> dict[str, Any]:
    _require_local_folder_request(request)
    _require_same_origin(request)
    try:
        choose = desktop_export.choose_render_directory if desktop_export._window is not None else browser_folder_picker.choose
        directory = await run_in_threadpool(choose)
        return {"directory": directory, "cancelled": directory is None}
    except FolderPickerBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FolderPickerUnavailable, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _require_local_folder_request(request: Request) -> None:
    _require_local_request(request)
    # Also reject DNS-rebinding Host names before opening a native window.
    host = request.url.hostname or ""
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(status_code=403, detail="Folder selection is only available through localhost")


@app.post("/api/render")
def create_render(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    project = payload.get("project")
    if not isinstance(project, dict):
        raise HTTPException(status_code=400, detail="Missing project payload")
    title = str(payload.get("title") or project.get("title") or "phrasync_export")
    destination = desktop_export.get_selected_render_directory() if desktop_export._window else payload.get("outputDirectory")
    if not destination:
        raise HTTPException(status_code=400, detail="Choose where to save your exports before starting a render.")
    output_dir = Path(str(destination)).expanduser()
    if not output_dir.is_absolute() or not output_dir.is_dir():
        raise HTTPException(status_code=400, detail="Choose an existing absolute export folder.")
    from phrasync.encoding import bitrate_bps
    try:
        bitrate_bps(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = manager.create_render(project, title, output_dir)
    return JSONResponse(job.public(), status_code=202)


@app.get("/api/render/{job_id}")
def render_status(job_id: str) -> dict[str, Any]:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    return job.public()


@app.post("/api/render/{job_id}/show")
def show_render_file(job_id: str) -> dict[str, str]:
    try:
        return {"path": desktop_export.show_render_file(job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/render/{job_id}/cancel")
def cancel_render(job_id: str) -> dict[str, bool]:
    return {"cancelled": manager.cancel(job_id)}


@app.get("/api/render/{job_id}/download")
def download_render(job_id: str) -> FileResponse:
    path = manager.output_path(job_id)
    if not path:
        raise HTTPException(status_code=404, detail="Rendered file is not ready")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.post("/api/projects/save")
def save_project(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    project = payload.get("project", payload)
    title = str(project.get("title") or "untitled")
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in title)[:64] or "untitled"
    path = PROJECTS_DIR / f"{safe}.phrasync.json"
    path.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"saved": True, "path": str(path), "filename": path.name}


def _open_browser(host: str, port: int) -> None:
    time.sleep(0.9)
    webbrowser.open(f"http://{browser_host(host)}:{port}")


def _wait_for_server(host: str, port: int, timeout: float = 15.0) -> str:
    """Wait until the local API is ready before displaying the desktop shell."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        url = instance_url(host, port)
        if url:
            return url
        time.sleep(0.1)
    raise RuntimeError(f"{APP_NAME} could not start its local interface on port {port}.")


def _open_desktop_window(url: str) -> None:
    """Host the local editor in a real Windows application window."""
    # WebView2 normally enables acceleration automatically, but explicitly
    # retain its GPU compositor/raster path for Store-packaged desktop builds.
    # Preserve caller-provided switches (useful for diagnostics) and avoid
    # replacing a remote-debugging port supplied by a release smoke test.
    gpu_switches = (
        "--enable-gpu",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--enable-features=CanvasOopRasterization",
    )
    existing_switches = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "").strip()
    present = set(existing_switches.split())
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = " ".join(
        [existing_switches, *(switch for switch in gpu_switches if switch not in present)]
    ).strip()
    try:
        import webview
    except Exception as exc:  # pragma: no cover - packaging/runtime failure
        raise RuntimeError(
            "The desktop interface is unavailable. Reinstall Phrasync from Microsoft Store."
        ) from exc

    if os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Phrasync.Desktop")
    # A new document URL bypasses WebView2's persisted HTML cache after an
    # MSIX in-place upgrade. Query parameters do not change the local route.
    document_url = f"{url}{'&' if '?' in url else '?'}desktop=1&app_version={APP_VERSION}"
    desktop_export._window = webview.create_window(
        APP_NAME,
        document_url,
        width=1480,
        height=940,
        min_size=(1100, 720),
        resizable=True,
        background_color="#0b0912",
        js_api=desktop_export,
    )
    bind_window(desktop_export._window)
    # Edge Chromium uses the Windows WebView2 runtime and keeps Phrasync inside
    # its own app window instead of exposing a browser tab to the user.
    webview.start(gui="edgechromium", debug=False, private_mode=False, icon=str(ASSETS_DIR / "Phrasync.ico"))


def main() -> None:
    global server
    install_exception_hooks()
    log_event("info", "startup", f"Phrasync {APP_VERSION} launcher starting")
    parser = argparse.ArgumentParser(description=f"Run {APP_NAME}")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--external-browser",
        action="store_true",
        help="open the editor in the default browser instead of the desktop window",
    )
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--strict-port",
        action="store_true",
        help="fail instead of selecting another port when the requested port is busy",
    )
    args = parser.parse_args()

    existing = instance_url(args.host, args.port)
    if existing and not args.reload and (args.no_browser or args.external_browser):
        print(f"{APP_NAME} is already running at {existing}")
        if not args.no_browser:
            if args.external_browser:
                webbrowser.open(existing)
            else:
                _open_desktop_window(existing)
        return

    selected_port = args.port
    if not args.strict_port:
        selected_port = available_port(args.host, args.port)
        if selected_port != args.port:
            print(f"Port {args.port} is in use; starting {APP_NAME} on port {selected_port}.")
    if args.external_browser and not args.no_browser and not args.reload:
        threading.Thread(target=_open_browser, args=(args.host, selected_port), daemon=True).start()

    if args.reload:
        # Reload needs an import string so Uvicorn can recreate the application.
        uvicorn.run("app:app", host=args.host, port=selected_port, reload=True, log_level="info")
        return

    # Passing the app object keeps this module's server reference available to
    # the local /api/shutdown endpoint.
    config = uvicorn.Config(
        app,
        host=args.host,
        port=selected_port,
        log_level="warning",
        access_log=False,
        # A Windows GUI executable intentionally has no stdout/stderr streams.
        # Uvicorn's default colour formatter probes stderr.isatty(), which would
        # otherwise prevent the packaged application from starting.
        log_config=None,
    )
    server = uvicorn.Server(config)
    if args.no_browser or args.external_browser:
        server.run()
        return

    server_thread = threading.Thread(target=server.run, name="phrasync-server", daemon=True)
    server_thread.start()
    try:
        url = _wait_for_server(args.host, selected_port)
        _open_desktop_window(url)
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
