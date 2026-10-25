from __future__ import annotations

import os
import shutil
from pathlib import Path

from PIL import Image, ImageOps


def install_output(temporary: Path, destination: Path) -> None:
    """Move a finished MP4 onto its reserved name without losing the render.

    The atomic rename is the normal path. Some accounts and locations refuse to
    replace an existing file even though the process owns it: managed folders,
    network volumes, security software, or a sandbox that denies unlink. Losing
    a completed encode to that refusal is never acceptable, so the reservation
    file is removed first and, when the rename is still refused, the finished
    bytes are copied over the reservation in place.
    """
    temporary = Path(temporary)
    destination = Path(destination)
    try:
        os.replace(temporary, destination)
        return
    except OSError as refusal:
        first_error = refusal
    try:
        destination.unlink()
    except OSError:
        pass  # the destination is either gone or will be overwritten below
    try:
        os.replace(temporary, destination)
        return
    except OSError:
        pass
    try:
        with open(temporary, "rb") as source, open(destination, "wb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
    except OSError:
        raise first_error
    try:
        temporary.unlink()
    except OSError:
        pass  # the copy landed; the staging file is left for the user to remove


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def hex_color(value: str | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) != 6:
        return fallback
    try:
        return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def apply_dim(image: Image.Image, amount: float) -> Image.Image:
    amount = clamp(amount)
    if amount <= 0:
        return image
    overlay = Image.new("RGB", image.size, (0, 0, 0))
    return Image.blend(image, overlay, amount)


def scale_for_canvas(value: float, height: int, width: int | None = None) -> float:
    """Scale a design value expressed at 1080p onto this canvas.

    The reference is the SHORT edge, not the height. Keying type size to height
    made a 9:16 frame inflate 160px to about 285px across a 1080-wide canvas, so
    a portrait export fitted roughly seven characters per line.
    """
    reference = min(height, width) if width else height
    return value * reference / 1080.0
