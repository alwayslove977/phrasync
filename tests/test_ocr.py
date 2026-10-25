"""OCR must degrade to a clear message instead of taking the app down.

The engine loads ONNX Runtime, whose dylibs require a newer macOS than the rest
of the bundle, so "installed but unloadable" is a real state on older systems.
These tests pin the three steps of that path: the failure is caught, Tesseract is
still tried, and what reaches the user names the actual cause.
"""

import sys
from pathlib import Path

import pytest

from phrasync import ocr as ocr_module
from phrasync.ocr import OCRUnavailable, capability_status, ocr_image, unavailable_reason

DYLD_FAILURE = (
    "ImportError: dlopen(...): Library not loaded: @rpath/libonnxruntime.1.23.2.dylib"
)


@pytest.fixture
def unloadable_engine(monkeypatch):
    """A bundle where RapidOCR is present but its native library will not load."""
    monkeypatch.setattr(ocr_module, "_rapid_import_failure", lambda: DYLD_FAILURE)
    monkeypatch.setattr(ocr_module, "_rapid_installed", lambda: True)
    monkeypatch.setattr(ocr_module, "_rapid_engine", lambda: (None, DYLD_FAILURE))
    monkeypatch.setattr(ocr_module, "tesseract_available", lambda: False)
    monkeypatch.setattr(ocr_module, "_tesseract_ocr", lambda path, language="auto": None)


def test_reference_image_ocr():
    if not capability_status()["available"]:
        pytest.skip("No OCR engine installed")
    path = Path(__file__).resolve().parent.parent / "assets" / "style_reference.png"
    result = ocr_image(path)
    normalized = result["text"].upper()
    assert "STAND" in normalized
    assert "GROUND" in normalized


def test_unloadable_engine_raises_instead_of_crashing(unloadable_engine, tmp_path):
    image = tmp_path / "poster.png"
    image.write_bytes(b"not really a png")

    with pytest.raises(OCRUnavailable) as excinfo:
        ocr_image(image)
    # A bare "no OCR engine" would send the user to reinstall a pack they have.
    assert "could not load" in str(excinfo.value)
    assert "ImportError" in str(excinfo.value)


def test_unavailable_reason_names_the_macos_floor_on_darwin(unloadable_engine, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    message = unavailable_reason()
    assert ocr_module.OCR_MIN_MACOS in message
    assert "only OCR is unavailable" in message


def test_ocr_still_uses_tesseract_when_rapidocr_cannot_load(unloadable_engine, monkeypatch):
    monkeypatch.setattr(
        ocr_module,
        "_tesseract_ocr",
        lambda path, language="auto": {
            "engine": "Tesseract",
            "text": "STAND",
            "lines": [],
            "elapsed": None,
        },
    )

    result = ocr_image(Path("poster.png"))
    assert result["engine"] == "Tesseract"


def test_capability_status_explains_a_broken_engine(unloadable_engine):
    status = capability_status()
    assert status["available"] is False
    assert status["rapidocr"] is False
    # /api/health carries this string to the UI, which shows it instead of
    # "run the AI installer".
    assert "could not load" in status["reason"]


def test_capability_status_is_quiet_when_tesseract_covers_ocr(unloadable_engine, monkeypatch):
    monkeypatch.setattr(ocr_module, "tesseract_available", lambda: True)

    status = capability_status()
    assert status["available"] is True
    assert status["reason"] == ""


def test_missing_package_keeps_the_install_hint(monkeypatch):
    failure = "ModuleNotFoundError: No module named 'rapidocr_onnxruntime'"
    monkeypatch.setattr(ocr_module, "_rapid_import_failure", lambda: failure)
    monkeypatch.setattr(ocr_module, "_rapid_installed", lambda: False)

    message = unavailable_reason()
    assert "requirements-ai.txt" in message
    assert "could not load" not in message
