from __future__ import annotations

import json
import re
import shutil
import uuid
import hashlib
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import AsyncIterable, BinaryIO

from starlette.concurrency import run_in_threadpool
from PIL import ImageFont

from .config import (
    MAX_UPLOAD_BYTES,
    SUPPORTED_AUDIO,
    SUPPORTED_FONT,
    SUPPORTED_IMAGE,
    SUPPORTED_LYRICS,
    SUPPORTED_VIDEO,
    UPLOADS_DIR,
)


@dataclass(slots=True)
class Asset:
    id: str
    kind: str
    name: str
    path: str
    size: int
    extension: str

    @property
    def url(self) -> str:
        return f"/media/{self.id}"

    def public(self) -> dict:
        data = asdict(self)
        data.pop("path", None)
        data["url"] = self.url
        return data


_KIND_EXTENSIONS = {
    "audio": SUPPORTED_AUDIO,
    "image": SUPPORTED_IMAGE,
    "video": SUPPORTED_VIDEO,
    "font": SUPPORTED_FONT,
    "lyrics": SUPPORTED_LYRICS,
}
_font_lock = threading.Lock()


def _finish_asset(asset: Asset) -> Asset:
    """Validate and content-address fonts, keeping other asset IDs unchanged."""
    if asset.kind == "font":
        path = Path(asset.path)
        try:
            ImageFont.truetype(str(path), 24).getname()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with _font_lock:
                target = UPLOADS_DIR / f"font-{digest}{asset.extension}"
                if target.exists():
                    path.unlink()
                else:
                    path.rename(target)
                asset.id = target.name
                asset.path = str(target)
                # Preserve a Unicode display name; the storage path remains a hash.
                asset.name = Path(asset.name).name
                _metadata_path(asset.id).write_text(json.dumps(asdict(asset), indent=2), encoding="utf-8")
            from .font_utils import refresh_fonts
            refresh_fonts()
            return asset
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise ValueError(f"Could not load font. Choose a valid TTF, OTF or TTC file: {exc}") from exc
    _metadata_path(asset.id).write_text(json.dumps(asdict(asset), indent=2), encoding="utf-8")
    return asset


def sanitize_name(name: str) -> str:
    name = Path(name).name.strip() or "asset"
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).stem).strip(" ._") or "asset"
    suffix = Path(name).suffix.lower()
    return f"{stem[:80]}{suffix}"


def validate_extension(kind: str, filename: str) -> str:
    if kind not in _KIND_EXTENSIONS:
        raise ValueError(f"Unsupported asset kind: {kind}")
    ext = Path(filename).suffix.lower()
    if ext not in _KIND_EXTENSIONS[kind]:
        allowed = ", ".join(sorted(_KIND_EXTENSIONS[kind]))
        raise ValueError(f"Unsupported {kind} file. Allowed: {allowed}")
    return ext


def _metadata_path(asset_id: str) -> Path:
    return UPLOADS_DIR / f"{asset_id}.meta.json"


def store_stream(kind: str, filename: str, stream: BinaryIO) -> Asset:
    clean_name = sanitize_name(filename)
    ext = validate_extension(kind, clean_name)
    asset_id = f"{uuid.uuid4().hex}{ext}"
    destination = UPLOADS_DIR / asset_id
    size = 0

    try:
        with destination.open("wb") as output:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError(
                        f"Upload exceeds the configured {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    asset = Asset(
        id=asset_id,
        kind=kind,
        name=Path(filename).name if kind == "font" else clean_name,
        path=str(destination),
        size=size,
        extension=ext,
    )
    return _finish_asset(asset)


def store_path(kind: str, source: Path, original_name: str | None = None) -> Asset:
    name = original_name or source.name
    clean_name = sanitize_name(name)
    ext = validate_extension(kind, clean_name)
    asset_id = f"{uuid.uuid4().hex}{ext}"
    destination = UPLOADS_DIR / asset_id
    shutil.copy2(source, destination)
    asset = Asset(
        id=asset_id,
        kind=kind,
        name=Path(name).name if kind == "font" else clean_name,
        path=str(destination),
        size=destination.stat().st_size,
        extension=ext,
    )
    return _finish_asset(asset)


def get_asset(asset_id: str | None, expected_kind: str | None = None) -> Asset | None:
    if not asset_id:
        return None
    safe_id = Path(asset_id).name
    metadata = _metadata_path(safe_id)
    asset_path = UPLOADS_DIR / safe_id
    if not metadata.exists() or not asset_path.exists():
        return None
    data = json.loads(metadata.read_text(encoding="utf-8"))
    asset = Asset(**data)
    # The sidecar records an absolute path from whenever the file was imported.
    # Trusting it breaks as soon as the workspace moves — a renamed folder, a
    # different user profile, a restored backup — so the id always wins.
    asset.path = str(asset_path)
    if expected_kind and asset.kind != expected_kind:
        raise ValueError(f"Asset {safe_id} is {asset.kind}, expected {expected_kind}")
    return asset


async def store_chunks(kind: str, filename: str, chunks: AsyncIterable[bytes], expected_size: int | None = None) -> Asset:
    """Write the request directly to its destination, without a second spool file."""
    clean_name = sanitize_name(filename)
    ext = validate_extension(kind, clean_name)
    if expected_size is not None and (expected_size < 0 or expected_size > MAX_UPLOAD_BYTES):
        raise ValueError(f"Upload exceeds the configured {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    asset_id = f"{uuid.uuid4().hex}{ext}"
    destination = UPLOADS_DIR / asset_id
    metadata = _metadata_path(asset_id)
    size = 0
    try:
        with destination.open("wb") as output:
            async for chunk in chunks:
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError(f"Upload exceeds the configured {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
                await run_in_threadpool(output.write, chunk)
        if expected_size is not None and size != expected_size:
            raise ValueError("Upload was interrupted; please import the file again")
        if not size:
            raise ValueError("The uploaded file is empty")
        asset = Asset(asset_id, kind, Path(filename).name if kind == "font" else clean_name, str(destination), size, ext)
        return await run_in_threadpool(_finish_asset, asset)
    except BaseException:
        destination.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        raise


def get_av_asset(asset_id: str | None) -> Asset | None:
    """Return an audio or video asset usable as a transcription/audio source."""
    asset = get_asset(asset_id)
    if asset and asset.kind not in {"audio", "video"}:
        raise ValueError(f"Asset {asset.id} is {asset.kind}, expected audio or video")
    return asset


def list_assets() -> list[dict]:
    assets: list[dict] = []
    for metadata in sorted(UPLOADS_DIR.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
            asset = Asset(**data)
            resolved = UPLOADS_DIR / Path(asset.id).name
            if resolved.exists():
                asset.path = str(resolved)
                assets.append(asset.public())
        except Exception:
            continue
    return assets


def delete_asset(asset_id: str) -> bool:
    asset = get_asset(asset_id)
    if not asset:
        return False
    Path(asset.path).unlink(missing_ok=True)
    _metadata_path(asset.id).unlink(missing_ok=True)
    return True
