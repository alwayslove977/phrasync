"""Microsoft Store updates for the packaged Windows application.

This module deliberately does not fetch installers from third-party URLs. The
Store remains responsible for selecting, downloading and installing packages.
"""

from __future__ import annotations

import ctypes
import asyncio
import sys
import threading
from typing import Any
from .diagnostics import log_event

_window = None
_install_lock = threading.Lock()
STATES = {0: "pending", 1: "downloading", 2: "deploying", 3: "completed", 4: "canceled",
          5: "other-error", 6: "low-battery", 7: "wifi-recommended", 8: "wifi-required"}


def bind_window(window) -> None:
    """Register the actual desktop owner; never use a foreground/guessed HWND."""
    global _window
    _window = window


def _record_error(action: str, exc: Exception) -> str:
    code = getattr(exc, "winerror", None) or getattr(exc, "hresult", None)
    if code is None and exc.args and isinstance(exc.args[0], int):
        code = exc.args[0]
    formatted = f"0x{int(code) & 0xffffffff:08X}" if code is not None else None
    log_event("error", "updates", f"{action}: {type(exc).__name__}: {exc}; HRESULT={formatted or 'unavailable'}")
    return f" Error code: {formatted}." if formatted else ""


def _state_name(value) -> str:
    # Python IntEnum.__str__ returns a number in recent Python versions.
    try:
        return STATES.get(int(value), "unknown")
    except (TypeError, ValueError):
        name = str(getattr(value, "name", value)).split(".")[-1].replace("_", "").lower()
        return {"othererror": "other-error", "errorlowbattery": "low-battery",
                "errorwifirecommended": "wifi-recommended", "errorwifirequired": "wifi-required",
                "cancelled": "canceled"}.get(name, name)


def _initialize_owner(context, hwnd):
    from winrt.runtime.interop import initialize_with_window
    initialize_with_window(context, hwnd)


def _ui_delegate(callback):
    from System import Action
    return Action(callback)


def _start_install_on_ui(updates):
    native = getattr(_window, "native", None)
    if native is None or native.IsDisposed or not native.IsHandleCreated:
        raise StoreUpdateUnavailable("The Phrasync desktop window is not ready. Reopen the app and try again.")
    result = {}

    def start():
        try:
            context = _context()
            _initialize_owner(context, native.Handle.ToInt64())
            # Initiate on the WinForms STA thread, but await on the server loop.
            # Running/waiting an asyncio loop here would block Store consent UI.
            operation = context.request_download_and_install_store_package_updates_async(updates)
            result["value"] = (context, operation)
        except Exception as exc:
            result["error"] = exc

    if native.InvokeRequired:
        native.Invoke(_ui_delegate(start))
    else:
        start()
    if "error" in result:
        raise result["error"]
    return result["value"]


class StoreUpdateUnavailable(RuntimeError):
    pass


def package_identity() -> str | None:
    """Return the active MSIX identity, or None for the portable preview."""
    if sys.platform != "win32":
        return None
    length = ctypes.c_uint32(0)
    get_name = ctypes.windll.kernel32.GetCurrentPackageFullName
    result = get_name(ctypes.byref(length), None)
    if result != 122 or not length.value:  # ERROR_INSUFFICIENT_BUFFER
        return None
    buffer = ctypes.create_unicode_buffer(length.value)
    if get_name(ctypes.byref(length), buffer) != 0:
        return None
    return buffer.value


def _context() -> Any:
    if not package_identity():
        raise StoreUpdateUnavailable("Store updates are available in the Microsoft Store installation of Phrasync.")
    try:
        from winrt.windows.services.store import StoreContext
        return StoreContext.get_default()
    except (ImportError, OSError, RuntimeError) as exc:
        detail = _record_error("Store context failed", exc)
        raise StoreUpdateUnavailable("The Microsoft Store update service is unavailable on this device." + detail) from exc


async def check_updates() -> dict[str, Any]:
    context = _context()
    try:
        updates = await context.get_app_and_optional_store_package_updates_async()
    except Exception as exc:
        detail = _record_error("Check failed", exc)
        raise StoreUpdateUnavailable("Could not check Microsoft Store for updates. Try again later or open the Store listing." + detail) from exc
    return {"available": len(updates) > 0, "count": len(updates)}


async def install_updates() -> dict[str, Any]:
    """Re-query before installing; never trust a previous UI check."""
    if not _install_lock.acquire(blocking=False):
        raise StoreUpdateUnavailable("An update installation is already in progress.")
    try:
        context = _context()
        updates = await context.get_app_and_optional_store_package_updates_async()
        if not updates:
            return {"available": False, "state": "up-to-date"}
        owner_context, operation = await asyncio.to_thread(_start_install_on_ui, updates)
        result = await operation
        state = _state_name(result.overall_state)
        log_event("info", "updates", f"Store result: {state}; package states=" +
                  ",".join(_state_name(item.package_update_state) for item in getattr(result, "store_package_update_statuses", [])))
        return {"available": True, "state": state}
    except StoreUpdateUnavailable:
        raise
    except Exception as exc:
        detail = _record_error("Install failed", exc)
        raise StoreUpdateUnavailable("Microsoft Store could not install the update. See Diagnostics for details or open Microsoft Store and try again." + detail) from exc
    finally:
        _install_lock.release()
