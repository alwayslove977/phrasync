"""Native export-folder selection for the local browser edition.

The small helper runs Tk on its own main thread/process, never on Uvicorn's
event loop. The desktop edition continues to use its existing pywebview bridge.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

from .config import RENDERS_DIR, PROJECT_ROOT
from .processes import background_flags


class FolderPickerUnavailable(RuntimeError):
    pass


class FolderPickerBusy(RuntimeError):
    pass


def available() -> bool:
    # A frozen desktop executable is not a Python interpreter for `-m`.
    # Packaged apps use their attached desktop bridge instead.
    return not getattr(sys, "frozen", False) and all(
        importlib.util.find_spec(name) is not None for name in ("tkinter", "_tkinter")
    )


def native_dialog(initial_directory: str) -> str | None:
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root, title="Phrasync - Choose export folder",
            initialdir=initial_directory, mustexist=True,
        )
        return str(Path(selected).resolve()) if selected else None
    finally:
        root.destroy()


class BrowserFolderPicker:
    def __init__(self):
        self._dialog_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._directory: str | None = None

    def selected(self) -> str | None:
        with self._state_lock:
            return self._directory

    def choose(self) -> str | None:
        if not self._dialog_lock.acquire(blocking=False):
            raise FolderPickerBusy("An export folder dialog is already open.")
        try:
            if not available():
                raise FolderPickerUnavailable("Native folder selection is unavailable. Enter the export path manually.")
            initial = self.selected() or str(RENDERS_DIR)
            result = subprocess.run(
                [sys.executable, "-m", "phrasync.folder_picker", initial],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                encoding="utf-8", timeout=300, creationflags=background_flags(),
            )
            if result.returncode != 0:
                raise FolderPickerUnavailable("Could not open the folder dialog. Enter the export path manually.")
            directory = json.loads(result.stdout).get("directory")
            if directory is None:
                return None  # Cancellation must never reset a prior choice.
            path = Path(directory).expanduser()
            if not path.is_absolute() or not path.is_dir():
                raise FolderPickerUnavailable("Choose an existing absolute export folder.")
            with self._state_lock:
                self._directory = str(path.resolve())
                return self._directory
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError) as exc:
            raise FolderPickerUnavailable("Folder selection failed or timed out. Enter the export path manually.") from exc
        finally:
            self._dialog_lock.release()


browser_folder_picker = BrowserFolderPicker()


if __name__ == "__main__":
    try:
        print(json.dumps({"directory": native_dialog(sys.argv[1] if len(sys.argv) > 1 else str(RENDERS_DIR))}))
    except Exception:
        sys.exit(1)
