"""Build a macOS .icns icon from the shipped Phrasync PNG.

The source artwork is 310x310, which is below the 1024 px master an icon set
needs; it is upscaled once with a high-quality filter so the bundle has every
size macOS asks for (including 16 px menu-bar/Spotlight sizes).

``iconutil`` is used when it works. On managed macOS accounts it can fail
because it stages its output in ``/private/var/folders/.../TemporaryItems`` and
the file policy there refuses the cleanup step. The fallback writes the ICNS
container directly: an ``icns`` header followed by PNG payloads, which is the
same layout ``iconutil`` produces for PNG input.
"""

from __future__ import annotations

import io
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ICONSET_SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}

# ICNS element type -> pixel size. The @1x/@2x pairs share a type only at the
# sizes macOS defines twice, so each element gets its own type here.
ICNS_TYPES = [
    (b"icp4", 16),
    (b"icp5", 32),
    (b"icp6", 64),
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic09", 512),
    (b"ic10", 1024),
    (b"ic11", 32),
    (b"ic12", 64),
    (b"ic13", 256),
    (b"ic14", 512),
]


def write_icns(master: Image.Image, destination: Path) -> Path:
    chunks: list[bytes] = []
    for kind, size in ICNS_TYPES:
        buffer = io.BytesIO()
        master.resize((size, size), Image.LANCZOS).save(buffer, format="PNG")
        payload = buffer.getvalue()
        chunks.append(kind + struct.pack(">I", len(payload) + 8) + payload)
    body = b"".join(chunks)
    destination.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    return destination


def build_icon(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    master = Image.open(source).convert("RGBA")
    if master.size != (1024, 1024):
        master = master.resize((1024, 1024), Image.LANCZOS)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "Phrasync.iconset"
            iconset.mkdir()
            for filename, size in ICONSET_SIZES.items():
                master.resize((size, size), Image.LANCZOS).save(iconset / filename)
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset), "-o", str(destination)],
                check=True, capture_output=True,
            )
        return destination
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        print(f"iconutil unavailable ({detail.decode(errors='replace').strip() or exc}); "
              f"writing ICNS directly", file=sys.stderr)
        return write_icns(master, destination)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: make_icns.py <source.png> <output.icns>", file=sys.stderr)
        return 2
    icon = build_icon(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"icon: {icon} ({icon.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
