"""macOS entry point for the packaged Phrasync application.

The editor is a local FastAPI/uvicorn application. This launcher:

1. starts the bundled server on loopback (reusing an instance that is already
   running instead of fighting over the port),
2. waits until the API actually answers,
3. hosts the editor in a native Cocoa/WKWebView window,
4. stops only the server process it started when that window closes.

Everything the launcher writes goes to ``~/Library/Logs/Phrasync/launcher.log``
because a windowed app bundle has no stdout or stderr.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

WINDOW_WIDTH = 1480
WINDOW_HEIGHT = 940
MIN_SIZE = (1100, 720)
STARTUP_TIMEOUT = 45.0
# How long a closing window waits for a render or transcription to stop itself.
SHUTDOWN_JOB_GRACE = 8.0
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
# Read-only source trees that may still hold fonts from the manual installs.
LEGACY_FONT_DIRS = ("phrasync/fonts", ".phrasync/fonts", ".verseframe/fonts")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Repository root when running from source (packaging/macos/launcher.py)."""
    return Path(__file__).resolve().parents[2]


def log_dir() -> Path:
    root = Path.home() / "Library" / "Logs" / "Phrasync"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _configure_streams() -> None:
    """Give a windowed bundle somewhere to write instead of devnull."""
    if not is_frozen():
        return
    stream = open(log_dir() / "launcher.log", "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = stream
    sys.stderr = stream


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"{stamp} | {message}", flush=True)
    except Exception:  # a logging failure must never stop the app
        pass


def log_exception(context: str, exc: BaseException) -> None:
    log(f"ERROR {context}: {type(exc).__name__}: {exc}")
    for line in traceback.format_exc().rstrip().splitlines():
        log(f"    {line}")


def _alert(message: str) -> None:
    """Last-resort native dialog, used only when the window cannot be created."""
    safe = message.replace("\\", "/").replace('"', "'")
    try:
        subprocess.run(
            ["osascript", "-e", f'display alert "Phrasync" message "{safe}" as critical'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def _reveal(path: Path, select: bool) -> None:
    args = ["open", "-R", str(path)] if select else ["open", str(path)]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def migrate_custom_fonts(target: Path) -> list[str]:
    """Copy legacy custom fonts into the writable folder without overwriting.

    The original files are left untouched; existing files in *target* always win
    so a user's curated font folder is never silently replaced.
    """
    copied: list[str] = []
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"WARN cannot create font folder {target}: {exc}")
        return copied
    for relative in LEGACY_FONT_DIRS:
        source = Path.home() / relative
        if not source.is_dir():
            continue
        try:
            entries = sorted(source.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            log(f"WARN cannot read legacy font folder {source}: {exc}")
            continue
        for path in entries:
            if not path.is_file() or path.suffix.lower() not in FONT_EXTENSIONS:
                continue
            destination = target / path.name
            if destination.exists():
                continue
            try:
                shutil.copy2(path, destination)
                copied.append(path.name)
            except OSError as exc:
                log(f"WARN cannot copy font {path}: {exc}")
    return copied


def _desktop_bridge_class():
    from phrasync.desktop_export import DesktopExportBridge
    from phrasync.config import RENDERS_DIR
    from phrasync.jobs import manager

    class MacDesktopExport(DesktopExportBridge):
        """Finder equivalents for the Windows-only bridge operations."""

        def show_render_file(self, job_id: str) -> str:
            source = manager.output_path(job_id)
            if source is None:
                raise FileNotFoundError("Rendered MP4 is not ready")
            _reveal(source, select=True)
            return str(source)

        def open_render_directory(self, job_id: str | None = None) -> str:
            path = manager.output_path(job_id) if job_id else None
            if path is None and self.get_selected_render_directory() is None:
                raise RuntimeError("Choose where to save your exports before starting a render.")
            directory = path.parent if path else Path(self.get_render_directory())
            directory.mkdir(parents=True, exist_ok=True)
            _reveal(directory, select=False)
            return str(directory)

        def open_default_render_directory(self) -> str:
            RENDERS_DIR.mkdir(parents=True, exist_ok=True)
            _reveal(RENDERS_DIR, select=False)
            return str(RENDERS_DIR)

        def open_store_updates(self) -> bool:
            raise RuntimeError("Microsoft Store updates are only available in the Windows app.")

    return MacDesktopExport


def _run_server(server) -> None:
    try:
        server.run()
    except BaseException as exc:  # noqa: BLE001 - surfaced to the launcher log
        log_exception("server", exc)


def _start_server(app_module, host: str, port: int):
    import uvicorn

    config = uvicorn.Config(
        app_module.app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        # A windowed bundle has no stderr; uvicorn's colour formatter probes it.
        log_config=None,
    )
    server = uvicorn.Server(config)
    # The /api/shutdown endpoint only works when the launcher owns the server.
    app_module.server = server
    thread = threading.Thread(target=_run_server, args=(server,), name="phrasync-server", daemon=True)
    thread.start()
    return server, thread


def _wait_ready(host: str, port: int, thread: threading.Thread, timeout: float = STARTUP_TIMEOUT) -> str:
    from phrasync.server import instance_url

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        url = instance_url(host, port)
        if url:
            return url
        if not thread.is_alive():
            raise RuntimeError("The Phrasync server exited during startup; see the launcher log.")
        time.sleep(0.15)
    raise RuntimeError(f"Phrasync did not start its local interface on port {port} within {timeout:.0f}s.")


def _thread_report() -> str:
    """Name the threads that are still running, for the launcher log."""
    names = [
        f"{item.name}{'(daemon)' if item.daemon else ''}"
        for item in threading.enumerate()
        if item.is_alive() and item is not threading.current_thread()
    ]
    return ", ".join(names) or "none"


def _exit_process(code: int) -> None:
    """Leave deterministically once the window and the server are finished.

    Interpreter shutdown joins every worker thread, so a render or an inference
    library that is still finishing native work can keep the process alive after
    the window disappears, leaving an invisible app in Activity Monitor that
    also holds its port. Unfinished jobs are given a bounded chance to stop, the
    helpers they started are reaped, and then the exit is forced.
    """
    try:
        from phrasync.jobs import manager
        from phrasync.processes import terminate_tracked

        active = manager.wait_idle(SHUTDOWN_JOB_GRACE)
        if active:
            log(f"WARN {active} job(s) still running after {SHUTDOWN_JOB_GRACE:.0f}s; stopping their helpers")
        stopped = terminate_tracked()
        if stopped:
            log(f"Stopped {stopped} media helper process(es) left by the job")
        manager.shutdown()
    except Exception as exc:  # noqa: BLE001 - the exit must not depend on cleanup
        log_exception("exit", exc)
    log(f"Exiting with status {code}; threads still alive: {_thread_report()}")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:  # noqa: BLE001 - a flush failure must not block the exit
            pass
    os._exit(code)


def _stop_server(server, thread) -> None:
    if server is None:
        return
    log("Stopping the local server started by this window")
    try:
        from phrasync.jobs import manager
        requested = manager.cancel_all("Stopping because Phrasync is closing")
        if requested:
            log(f"Asking {requested} unfinished job(s) to stop")
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        log_exception("shutdown", exc)
    server.should_exit = True
    if thread is not None:
        thread.join(timeout=10)
        if thread.is_alive():
            log("WARN server thread did not stop within 10s")
    log(f"Threads still alive after the server stopped: {_thread_report()}")


SMOKE_PROBE_JS = """(function () {
  var canvas = document.querySelector('canvas');
  var root = document.querySelector('#app, main, .app-shell, body');
  var rect = root ? root.getBoundingClientRect() : null;
  var style = window.getComputedStyle(document.body);
  return JSON.stringify({
    title: document.title,
    ready: document.readyState,
    styles: document.styleSheets.length,
    scripts: document.scripts.length,
    canvases: document.querySelectorAll('canvas').length,
    canvasSize: canvas ? [canvas.width, canvas.height] : null,
    kinetic: typeof window.VFKinetic,
    locale: document.documentElement.lang || '',
    bodyBackground: style.backgroundColor,
    bodyFont: style.fontFamily,
    viewport: [window.innerWidth, window.innerHeight],
    layout: rect ? [Math.round(rect.width), Math.round(rect.height)] : null,
    text: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 120)
  });
})()"""


def _smoke_probe(window) -> None:
    """Verify the real page loaded inside WKWebView, then close the window.

    Used by ``--smoke`` so a build can be validated without screen access.
    """
    try:
        time.sleep(3.0)
        report = window.evaluate_js(SMOKE_PROBE_JS)
        log(f"SMOKE {report}")
    except Exception as exc:  # noqa: BLE001 - reported in the log
        log_exception("smoke", exc)
    finally:
        try:
            window.destroy()
        except Exception:  # noqa: BLE001
            pass


def _run_as_multiprocessing_helper(argv: list[str]) -> bool:
    """Serve a ``multiprocessing`` helper instead of opening a second window.

    A frozen app's ``sys.executable`` is the app itself, so the helpers that
    ``multiprocessing`` normally starts with ``python -c ...`` relaunch the whole
    bundle: a second editor window appears and competes for a second port. The
    helper's own entry point is executed here instead, exactly as the interpreter
    would have done.
    """
    if "--multiprocessing-fork" in argv:
        import multiprocessing

        multiprocessing.freeze_support()
        return True
    if "-c" not in argv:
        return False
    script = argv[argv.index("-c") + 1]
    if "resource_tracker" not in script:
        return False
    import re

    match = re.search(r"main\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)", script)
    if match is None:
        return False
    from multiprocessing import resource_tracker

    log(f"Multiprocessing helper, not the editor: resource tracker (fd {match.group(1)})")
    # CPython 3.12's tracker takes only the pipe descriptor.
    resource_tracker.main(int(match.group(1)))
    return True


def _main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _configure_streams()
    log("---- Phrasync launcher start ----")
    if _run_as_multiprocessing_helper(argv):
        os._exit(0)

    if not is_frozen():
        root = project_root()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

    from phrasync.config import (
        APP_NAME,
        APP_VERSION,
        CUSTOM_FONTS_DIR,
        DEFAULT_HOST,
        DEFAULT_PORT,
        WORKSPACE,
    )
    from phrasync.server import available_port, instance_url

    host = DEFAULT_HOST
    requested_port = DEFAULT_PORT
    use_browser = "--browser" in argv
    headless = "--no-browser" in argv
    if "--port" in argv:
        requested_port = int(argv[argv.index("--port") + 1])

    log(f"Build: {'packaged' if is_frozen() else 'source'}, version {APP_VERSION}, python {sys.version.split()[0]}")
    log(f"PID {os.getpid()}, parent {os.getppid()}, args {argv or ['(none)']}, workspace {WORKSPACE}")
    log(f"Custom font folder: {CUSTOM_FONTS_DIR}")
    copied = migrate_custom_fonts(CUSTOM_FONTS_DIR)
    if copied:
        log(f"Copied {len(copied)} legacy custom font(s): {', '.join(copied)}")

    import app as app_module

    bridge_class = _desktop_bridge_class()
    bridge = bridge_class()
    app_module.desktop_export = bridge

    owns_server = False
    server = None
    thread = None
    try:
        reused = instance_url(host, requested_port)
        url = reused
        if url:
            log(f"Reusing the Phrasync instance already running at {url}")
            if headless:
                return 0
        else:
            try:
                port = available_port(host, requested_port)
            except RuntimeError as exc:
                _alert(f"Phrasync could not find a free local port.\n{exc}")
                raise
            if port != requested_port:
                log(f"Port {requested_port} is busy; using {port}")
            server, thread = _start_server(app_module, host, port)
            owns_server = True
            url = _wait_ready(host, port, thread)
            log(f"Server ready at {url}")

        if headless:
            log("Headless mode: serving until /api/shutdown is called")
            thread.join()
            return 0

        if use_browser:
            log("Browser mode requested")
            webbrowser.open(url)
            if owns_server:
                thread.join()
            return 0

        import webview

        document_url = f"{url}?desktop=1&app_version={APP_VERSION}"
        window = None
        try:
            window = webview.create_window(
                APP_NAME,
                document_url,
                width=WINDOW_WIDTH,
                height=WINDOW_HEIGHT,
                min_size=MIN_SIZE,
                resizable=True,
                background_color="#0b0912",
                js_api=bridge,
            )
            bridge._window = window
            if "--smoke" in argv:
                threading.Thread(target=_smoke_probe, args=(window,), daemon=True).start()
            webview.start(
                gui="cocoa",
                debug=bool(os.environ.get("PHRASYNC_WEBVIEW_DEBUG")),
                private_mode=False,
                storage_path=str(Path(CUSTOM_FONTS_DIR).parent / "WebKit"),
            )
            log("Window closed by the user")
            return 0
        except Exception as exc:  # noqa: BLE001 - fall back to the browser
            log_exception("window", exc)
            if not owns_server:
                _alert("Phrasync could not open its window.\nSee ~/Library/Logs/Phrasync/launcher.log")
                return 1
            log("Falling back to the default browser")
            _alert(
                "Phrasync could not open its own window, so the editor is opening in your browser."
                "\nUse the in-app Quit button to stop the server."
                "\nLog: ~/Library/Logs/Phrasync/launcher.log"
            )
            webbrowser.open(url)
            thread.join()
            return 0
    finally:
        # Every exit path stops the server this process started, including the
        # headless one: leaving it running made the app take seconds to die.
        if owns_server:
            _stop_server(server, thread)
        log("---- Phrasync launcher exit ----")


def main(argv: list[str] | None = None) -> int:
    """Run the app, then leave the process for certain.

    A packaged bundle is a single process the user cannot inspect, so it must
    not outlive its window: the exit is forced once the server is stopped, and
    that holds for a startup failure too.
    """
    try:
        code = _main(argv)
    except BaseException:
        if is_frozen():
            log_exception("fatal", sys.exc_info()[1] or RuntimeError("startup failed"))
            _exit_process(1)
        raise
    if is_frozen():
        _exit_process(code)
    return code


if __name__ == "__main__":
    sys.exit(main())