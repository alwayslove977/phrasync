"""Launch non-interactive media helpers without flashing a Windows console."""
import subprocess
import threading

_tracked: set[subprocess.Popen] = set()
_lock = threading.Lock()


def background_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def track(process: subprocess.Popen) -> subprocess.Popen:
    """Remember a long-lived helper so it can be reaped if the app is exited."""
    with _lock:
        _tracked.add(process)
    return process


def terminate_tracked(timeout: float = 4.0) -> int:
    """Stop helpers that are still running, so none is orphaned by a forced exit."""
    with _lock:
        processes = list(_tracked)
        _tracked.clear()
    stopped = 0
    for process in processes:
        if process.poll() is not None:
            continue
        share = timeout / max(1, len(processes))
        try:
            process.terminate()
            process.wait(timeout=share)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        except OSError:
            continue
        stopped += 1
    return stopped
