"""Microsoft Store updates for the packaged Windows application.

This module deliberately does not fetch installers from third-party URLs. The
Store remains responsible for selecting, downloading and installing packages.
"""

from __future__ import annotations

import ctypes
import asyncio
import sys
import threading
import json
import math
from typing import Any
from .diagnostics import log_event
from .config import WORKSPACE

_window = None
_install_lock = threading.Lock()
_progress_lock = threading.Lock()
_progress = {"busy": False, "state": "idle", "percent": None}
_receipt = WORKSPACE / "store-update.json"
STATES = {0: "pending", 1: "downloading", 2: "deploying", 3: "completed", 4: "canceled",
          5: "other-error", 6: "low-battery", 7: "wifi-recommended", 8: "wifi-required"}


def update_progress() -> dict[str, Any]:
    with _progress_lock:
        return dict(_progress)


def _set_progress(**values):
    with _progress_lock:
        _progress.update(values)


def _on_progress(_operation, status):
    value = float(status.total_download_progress)
    percent = max(0, min(100, round(value * 100))) if math.isfinite(value) else None
    # A progress notification is not proof of successful deployment.
    _set_progress(state=_state_name(status.package_update_state), percent=percent,
                  downloaded_bytes=int(status.package_bytes_downloaded),
                  total_bytes=int(status.package_download_size_in_bytes))


def _write_receipt(state):
    try:
        previous = json.loads(_receipt.read_text(encoding="utf-8")) if _receipt.exists() else {}
        if state == "started":
            previous = {"from_identity": package_identity()}
        previous["state"] = state
        temporary = _receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(previous), encoding="utf-8")
        temporary.replace(_receipt)
    except (OSError, ValueError) as exc:
        log_event("warning", "updates", f"Could not save update verification: {exc}")


def previous_update() -> str | None:
    """Verify after relaunch instead of assuming a Store consent installed anything."""
    identity = package_identity()
    if not identity:
        return None
    try:
        receipt = json.loads(_receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    previous = receipt.get("from_identity")
    if previous and previous != identity:
        try:
            old = tuple(map(int, previous.split("_")[1].split(".")))
            new = tuple(map(int, identity.split("_")[1].split(".")))
            if new > old:
                return "verified"
        except (ValueError, IndexError):
            pass
    return "not-applied" if receipt.get("state") in {"started", "completed", "pending", "unverified"} else receipt.get("state")


def _result_state(result):
    """The overall Store result can be Completed even if a package failed."""
    state = _state_name(result.overall_state)
    statuses = list(getattr(result, "store_package_update_statuses", []))
    package_states = [_state_name(item.package_update_state) for item in statuses]
    codes = []
    queue_states = []
    for item in getattr(result, "store_queue_items", []):
        current = item.get_current_status()
        queue_state = int(current.package_install_state)
        queue_states.append(queue_state)
        raw = current.extended_error
        code = int(getattr(raw, "value", raw)) & 0xffffffff
        if code:
            codes.append(f"0x{code:08X}")
        log_event("info", "updates", f"Queue package={item.package_family_name}; state={queue_state}; "
                  f"extended={int(current.package_install_extended_state)}; HRESULT=0x{code:08X}")
    if 3 in queue_states or codes:
        state = "other-error"
    elif 2 in queue_states:
        state = "canceled"
    elif any(value in (0, 4) for value in queue_states):
        state = "pending"
    elif any(value != "completed" for value in package_states):
        state = next(value for value in package_states if value != "completed")
    elif state == "completed" and not (package_states or queue_states):
        state = "unverified"
    log_event("info" if state == "completed" else "warning", "updates",
              f"Verified Store result: {state}; overall={_state_name(result.overall_state)}; packages={package_states}; codes={codes}")
    return state, codes


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


def _register_restart():
    """Let Windows relaunch the packaged EXE after an update, never python.exe."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        register = ctypes.windll.kernel32.RegisterApplicationRestart
        register.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        register.restype = ctypes.c_long
        # Restart for patching/reboot, not crashes or hangs. Windows manages the
        # new package activation; do not relaunch an obsolete WindowsApps path.
        result = register(None, 3)
        if result:
            log_event("warning", "updates", f"Restart registration failed: 0x{result & 0xffffffff:08X}")
    except (AttributeError, OSError) as exc:
        log_event("warning", "updates", f"Restart registration unavailable: {exc}")


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
            operation.progress = _on_progress
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
        _set_progress(busy=True, state="checking", percent=None, downloaded_bytes=0, total_bytes=0, error_codes=[])
        context = _context()
        updates = await context.get_app_and_optional_store_package_updates_async()
        if not updates:
            _set_progress(state="up-to-date")
            return {"available": False, "state": "up-to-date"}
        _write_receipt("started")
        _set_progress(state="pending")
        _register_restart()
        owner_context, operation = await asyncio.to_thread(_start_install_on_ui, updates)
        result = await operation
        state, codes = _result_state(result)
        # The real 0.4.7 -> 0.4.8 test failed with WU SOAP fault 0x80244007;
        # retrying the same update in Store succeeded. Refresh once, rather than
        # reporting success or repeatedly resuming the failed request forever.
        if state == "other-error" and set(codes) == {"0x80244007"}:
            log_event("warning", "updates", "Refreshing Store update query and retrying once after 0x80244007")
            _set_progress(state="retrying", percent=None, error_codes=codes)
            await asyncio.sleep(1)
            updates = await owner_context.get_app_and_optional_store_package_updates_async()
            if updates:
                owner_context, operation = await asyncio.to_thread(_start_install_on_ui, updates)
                result = await operation
                state, codes = _result_state(result)
        _write_receipt(state)
        _set_progress(state=state, error_codes=codes, percent=100 if state == "completed" else None)
        response = {"available": True, "state": state}
        if codes:
            response["error_codes"] = codes
        return response
    except StoreUpdateUnavailable:
        _set_progress(state="other-error", percent=None)
        raise
    except Exception as exc:
        _set_progress(state="other-error", percent=None)
        _write_receipt("other-error")
        detail = _record_error("Install failed", exc)
        raise StoreUpdateUnavailable("Microsoft Store could not install the update. See Diagnostics for details or open Microsoft Store and try again." + detail) from exc
    finally:
        _set_progress(busy=False)
        _install_lock.release()
