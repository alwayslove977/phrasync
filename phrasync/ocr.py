from __future__ import annotations

import csv
import importlib.util
import io
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any
from .processes import background_flags

# What ONNX Runtime -- and therefore RapidOCR -- requires from macOS. Every other
# native dependency in the bundle loads on 12.0, so this value is the only reason
# an OCR call can fail on a system where the app itself starts and runs.
OCR_MIN_MACOS = "13.4"


class OCRUnavailable(RuntimeError):
    pass


def _describe(exc: BaseException) -> str:
    """``TypeError: first line`` -- short enough for a toast, specific enough to
    tell a missing package from a dylib the system refused to load."""
    lines = str(exc).strip().splitlines()
    return f"{type(exc).__name__}: {lines[0]}" if lines else type(exc).__name__


@lru_cache(maxsize=1)
def _rapid_import_failure() -> str:
    """Why ``import rapidocr_onnxruntime`` failed, or ``""`` when it worked.

    Importing the package is what loads ONNX Runtime's dylibs, so on a macOS
    older than ``OCR_MIN_MACOS`` it fails here with a dyld error before any OCR
    code runs. Cached so ``/api/health`` does not retry a broken dlopen on every
    poll; the outcome cannot change without a restart anyway.
    """
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except Exception as exc:
        return _describe(exc)
    return ""


def _rapid_installed() -> bool:
    """Locate the package without importing it, to tell "absent" from "broken"."""
    try:
        return importlib.util.find_spec("rapidocr_onnxruntime") is not None
    except (ImportError, ValueError):  # unresolvable, e.g. broken parent
        return False


@lru_cache(maxsize=1)
def _rapid_engine() -> tuple[Any, str]:
    """``(engine, failure)``; ``engine`` is None whenever OCR cannot run.

    Building the engine loads three ONNX models, so this is cached and only ever
    entered from a real OCR request -- never from a capability probe.
    """
    failure = _rapid_import_failure()
    if failure:
        return None, failure
    try:
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR(), ""
    except Exception as exc:
        return None, _describe(exc)


def rapidocr_available() -> bool:
    return not _rapid_import_failure()


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _sort_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]):
        box = item.get("box") or []
        if box and len(box) >= 4:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            return (sum(ys) / len(ys), sum(xs) / len(xs))
        return (float(item.get("top", 0)), float(item.get("left", 0)))

    return sorted(lines, key=key)


def _rapid_ocr(path: Path) -> dict[str, Any] | None:
    engine, _failure = _rapid_engine()
    if engine is None:
        return None
    result, elapsed = engine(str(path))
    lines: list[dict[str, Any]] = []
    for row in result or []:
        if not row or len(row) < 3:
            continue
        box, text, score = row[0], str(row[1]).strip(), float(row[2])
        if text:
            lines.append({"text": text, "confidence": score, "box": box})
    lines = _sort_lines(lines)
    return {
        "engine": "RapidOCR",
        "text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "elapsed": elapsed,
    }


def _tesseract_ocr(path: Path, language: str = "eng") -> dict[str, Any] | None:
    executable = shutil.which("tesseract")
    if not executable:
        return None
    language = "eng" if not language or language == "auto" else language
    command = [executable, str(path), "stdout", "-l", language, "--psm", "6", "tsv"]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, creationflags=background_flags())
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract failed: {message}")
    text = process.stdout.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in reader:
        token = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf", "-1"))
        except ValueError:
            confidence = -1
        if not token or confidence < 0:
            continue
        key = (
            row.get("page_num", "1"),
            row.get("block_num", "0"),
            row.get("par_num", "0"),
            row.get("line_num", "0"),
        )
        grouped.setdefault(key, []).append(
            {
                "text": token,
                "confidence": confidence / 100.0,
                "left": int(row.get("left", "0") or 0),
                "top": int(row.get("top", "0") or 0),
                "width": int(row.get("width", "0") or 0),
                "height": int(row.get("height", "0") or 0),
            }
        )
    lines: list[dict[str, Any]] = []
    for tokens in grouped.values():
        tokens.sort(key=lambda token: token["left"])
        left = min(token["left"] for token in tokens)
        top = min(token["top"] for token in tokens)
        right = max(token["left"] + token["width"] for token in tokens)
        bottom = max(token["top"] + token["height"] for token in tokens)
        lines.append(
            {
                "text": " ".join(token["text"] for token in tokens),
                "confidence": sum(token["confidence"] for token in tokens) / len(tokens),
                "box": [[left, top], [right, top], [right, bottom], [left, bottom]],
            }
        )
    lines = _sort_lines(lines)
    return {
        "engine": "Tesseract",
        "text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "elapsed": None,
    }


def unavailable_reason() -> str:
    """A sentence that names the cause it actually found.

    "Install the AI pack" is the wrong advice when the pack is installed and the
    system refused to load ONNX Runtime, which is what a macOS below
    ``OCR_MIN_MACOS`` looks like from here.
    """
    failure = _rapid_import_failure()
    if failure and _rapid_installed():
        if sys.platform == "darwin":
            return (
                f"RapidOCR is installed but could not load ({failure}). It needs macOS "
                f"{OCR_MIN_MACOS} or later for ONNX Runtime; Phrasync's other features run "
                "on 12.0, so only OCR is unavailable on this system. "
                "Install Tesseract (brew install tesseract) for OCR here."
            )
        return (
            f"RapidOCR is installed but could not load ({failure}). "
            "Reinstall it with the AI installer, or install Tesseract."
        )
    return (
        "No OCR engine is available. Install requirements-ai.txt (RapidOCR) or Tesseract OCR."
    )


def ocr_image(path: Path, language: str = "auto") -> dict[str, Any]:
    rapid = _rapid_ocr(path)
    if rapid is not None:
        return rapid
    tesseract = _tesseract_ocr(path, language=language)
    if tesseract is not None:
        return tesseract
    raise OCRUnavailable(unavailable_reason())


def capability_status() -> dict[str, Any]:
    """Health payload. ``reason`` is empty whenever ``available`` is true."""
    failure = _rapid_import_failure()
    tesseract = tesseract_available()
    available = not failure or tesseract
    return {
        "rapidocr": not failure,
        "tesseract": tesseract,
        "available": available,
        "reason": "" if available else unavailable_reason(),
    }
