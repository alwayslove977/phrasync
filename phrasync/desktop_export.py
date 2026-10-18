"""Native, user-approved destinations for desktop video exports."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import webbrowser
from urllib.parse import urlsplit
from pathlib import Path

from .config import RENDERS_DIR
from .jobs import manager


class DesktopExportBridge:
    def open_store_updates(self) -> bool:
        from .store_updates import package_identity
        if os.name != "nt" or not package_identity():
            raise RuntimeError("Microsoft Store updates are only available for the Store installation.")
        os.startfile("ms-windows-store://pdp/?productid=9NF9JBG2PKHX")
        return True

    def open_external_url(self, url: str) -> bool:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc not in {"x.com", "www.linkedin.com", "github.com", "buymeacoffee.com", "www.giovannidemiccoli.com"}:
            raise ValueError("External link is not allowed")
        return webbrowser.open(url)

    def __init__(self) -> None:
        self._window = None
        self._lock = threading.RLock()
        self._directory = RENDERS_DIR
        self._directory_selected = False
        self._file_directory = Path.home()

    def save_text_file(self, content: str, filename: str, extension: str) -> str | None:
        """Save only after the user chooses a destination in the native dialog."""
        if extension not in {"json", "srt", "vtt", "ass", "lrc"}:
            raise ValueError("Unsupported file format")
        if self._window is None:
            raise RuntimeError("Desktop window is not ready")
        import webview

        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE, directory=str(self._file_directory),
            save_filename=Path(filename).name,
            file_types=(f"{extension.upper()} file (*.{extension})",),
        )
        if not selected:
            return None
        target = Path(selected[0]).resolve()
        if target.suffix.lower() != f".{extension}":
            target = target.with_name(target.name + f".{extension}")
        target.write_text(content, encoding="utf-8")
        self._file_directory = target.parent
        return str(target)

    def load_project_file(self) -> dict[str, str] | None:
        if self._window is None:
            raise RuntimeError("Desktop window is not ready")
        import webview

        selected = self._window.create_file_dialog(
            webview.FileDialog.OPEN, directory=str(self._file_directory),
            allow_multiple=False, file_types=("Phrasync project (*.json;*.phrasync;*.verseframe)",),
        )
        if not selected:
            return None
        target = Path(selected[0]).resolve()
        content = target.read_text(encoding="utf-8-sig")
        self._file_directory = target.parent
        return {"path": str(target), "content": content}

    def get_render_directory(self) -> str:
        with self._lock:
            return str(self._directory)

    def get_selected_render_directory(self) -> str | None:
        with self._lock:
            return str(self._directory) if self._directory_selected else None

    def show_render_file(self, job_id: str) -> str:
        source = manager.output_path(job_id)
        if source is None:
            raise FileNotFoundError("Rendered MP4 is not ready")
        if os.name != "nt":
            raise RuntimeError("Showing a file is only supported in the Windows app")
        subprocess.Popen(["explorer.exe", "/select,", str(source)], creationflags=0x08000000)
        return str(source)

    def choose_render_directory(self) -> str | None:
        if self._window is None:
            raise RuntimeError("Desktop window is not ready")
        import webview

        selected = self._window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=self.get_render_directory()
        )
        if not selected:
            return None
        directory = Path(selected[0]).resolve()
        if not directory.is_dir():
            raise ValueError("The selected export folder does not exist")
        with self._lock:
            self._directory = directory
            self._directory_selected = True
        return str(directory)

    def open_render_directory(self, job_id: str | None = None) -> str:
        path = manager.output_path(job_id) if job_id else None
        if path is None and self.get_selected_render_directory() is None:
            raise RuntimeError("Choose where to save your exports before starting a render.")
        directory = path.parent if path else Path(self.get_render_directory())
        directory.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", str(directory)], creationflags=0x08000000)
        else:
            raise RuntimeError("Opening a folder is only supported in the Windows desktop app")
        return str(directory)

    def open_default_render_directory(self) -> str:
        RENDERS_DIR.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", str(RENDERS_DIR)], creationflags=0x08000000)
        else:
            raise RuntimeError("Opening a folder is only supported in the Windows desktop app")
        return str(RENDERS_DIR)

    def save_render_as(self, job_id: str) -> str | None:
        source = manager.output_path(job_id)
        if source is None:
            raise FileNotFoundError("Rendered MP4 is not ready")
        if self._window is None:
            raise RuntimeError("Desktop window is not ready")
        import webview

        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(source.parent),
            save_filename=source.name,
            file_types=("MP4 video (*.mp4)",),
        )
        if not selected:
            return None
        target = Path(selected[0]).with_suffix(".mp4").resolve()
        if target != source.resolve():
            shutil.copy2(source, target)
        return str(target)
