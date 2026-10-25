"""Install wheels by extraction only (create, never delete).

pip's normal installer replaces files with ``os.replace`` and unlinks the
leftovers. On this managed account those unlinks are refused by the file
policy, which makes ``pip install`` abort halfway. Extracting the wheel
archives writes the same files without any rename or delete step, so the
venv ends up in the same state.

    python packaging/macos/install_wheels.py build/macos/wheels .venv-build
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REMAP = {"purelib": "", "platlib": ""}


def target_for(name: str) -> str | None:
    """Wheel member name -> path inside site-packages (None = skip)."""
    parts = name.split("/")
    if len(parts) >= 3 and parts[0].endswith(".data"):
        kind = parts[1]
        if kind not in REMAP:
            return None  # scripts/, headers/, data/ are not needed to import
        return "/".join(parts[2:])
    return name


def install(wheel: Path, site: Path) -> int:
    written = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            relative = target_for(member.filename)
            if not relative:
                continue
            destination = site / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(destination, "wb") as handle:
                while True:
                    chunk = source.read(1 << 20)
                    if not chunk:
                        break
                    handle.write(chunk)
            written += 1
    return written


def main() -> int:
    wheels_dir = Path(sys.argv[1]).resolve()
    site = Path(sys.argv[2]).resolve() / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    if not site.is_dir():
        print(f"missing site-packages: {site}")
        return 2
    total = 0
    for wheel in sorted(wheels_dir.glob("*.whl")):
        count = install(wheel, site)
        total += count
        print(f"  {wheel.name}: {count} files")
    print(f"extracted {total} files into {site}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
