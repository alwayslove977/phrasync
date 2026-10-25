"""Install wheels by extraction only (create, never delete).

pip's normal installer replaces files with ``os.replace`` and unlinks the
leftovers. On this managed account those unlinks are refused by the file
policy, which makes ``pip install`` abort halfway. Extracting the wheel
archives writes the same files without any rename or delete step, so the
venv ends up in the same state.

    python packaging/macos/install_wheels.py build/macos/wheels .venv-build

Exit codes: 0 extracted, 2 site-packages missing, 3 a wheel member would be
written outside site-packages (that wheel is refused whole and the run stops).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path, PurePosixPath

REMAP = {"purelib": "", "platlib": ""}


class UnsafeWheelMember(ValueError):
    """A wheel member name would place a file outside site-packages."""


def target_for(name: str) -> str | None:
    """Wheel member name -> path inside site-packages (None = skip)."""
    parts = name.split("/")
    if len(parts) >= 3 and parts[0].endswith(".data"):
        kind = parts[1]
        if kind not in REMAP:
            return None  # scripts/, headers/, data/ are not needed to import
        return "/".join(parts[2:])
    return name


def safe_relative(name: str) -> str | None:
    """Validate a member name and return it normalised, or raise.

    Wheel member names are POSIX paths relative to the archive root, so an
    absolute name, a backslash-separated name or any ``..`` component is either
    a corrupt archive or an attempt to write outside the target directory. Both
    are refused rather than skipped: a wheel that tries this must not be
    installed partially. Empty and ``.`` components are dropped, which keeps the
    ``./pkg/module.py`` spelling working. ``None`` means the member carries no
    path at all.
    """
    if not name:
        return None
    if "\x00" in name:
        raise UnsafeWheelMember(f"member name contains a null byte: {name!r}")
    if "\\" in name:
        raise UnsafeWheelMember(f"member name uses a backslash separator: {name!r}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or name.startswith("/"):
        raise UnsafeWheelMember(f"absolute member path: {name!r}")
    parts = [part for part in pure.parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise UnsafeWheelMember(f"member path escapes the target directory: {name!r}")
    if not parts:
        return None
    return "/".join(parts)


def destination_for(root: Path, relative: str, member: str) -> Path:
    """Join ``relative`` onto ``root`` and prove the result stays inside it."""
    destination = root / relative
    resolved = destination.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise UnsafeWheelMember(
            f"member {member!r} resolves to {resolved}, outside {root}"
        )
    return destination


def install(wheel: Path, site: Path) -> int:
    written = 0
    root = site.resolve()
    with zipfile.ZipFile(wheel) as archive:
        # Every member is validated before the first byte is written: a wheel that
        # tries to escape is refused as a whole, never half-installed.
        plan = []
        for member in archive.infolist():
            if member.is_dir():
                continue
            relative = target_for(member.filename)
            if relative is None:
                continue
            try:
                safe = safe_relative(relative)
                if safe is None:
                    continue
                plan.append((member, destination_for(root, safe, member.filename)))
            except UnsafeWheelMember as exc:
                raise UnsafeWheelMember(f"{wheel.name}: {exc}") from None
        for member, destination in plan:
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
        try:
            count = install(wheel, site)
        except UnsafeWheelMember as exc:
            print(f"refusing {exc}", file=sys.stderr)
            return 3
        total += count
        print(f"  {wheel.name}: {count} files")
    print(f"extracted {total} files into {site}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
