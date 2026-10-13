"""Thumbnail loader for plant profile images (US-G2, issue #317).

Fetches plant thumbnails off-thread and caches them on disk. Follows the
``climate_service.py`` cache pattern: ``QStandardPaths.AppLocalDataLocation``
+ subdirectory.

The loader is Qt-free (uses ``requests`` directly) so it can be unit-tested
without a QApplication and reused off the UI thread.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path

from open_garden_planner.services.image_download import (
    THUMBNAIL_MAX_BYTES,
    THUMBNAIL_MAX_PIXELS,
    decode_image,
    fetch_image,
    thumbnail_png,
)

logger = logging.getLogger(__name__)

_CACHE_DIR_NAME = "plant_thumbs"
_TIMEOUT_SECONDS = 10
_CACHE_MAX_BYTES = 24 * 1024 * 1024  # worst-case 2048² RGBA PNG plus encoding overhead


def get_cache_dir() -> Path:
    """Return the thumbnail cache directory, creating it if needed."""
    from PyQt6.QtCore import QStandardPaths

    app_data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    cache_dir = Path(app_data) / _CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key(url: str) -> str:
    """Generate a filesystem-safe cache key from a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _cache_path(url: str) -> Path:
    """Return the cache file path for a given URL."""
    return get_cache_dir() / f"{_cache_key(url)}.png"


def is_cached(url: str) -> bool:
    """Check if a thumbnail is already cached on disk."""
    return get_cached_thumbnail(url) is not None


def get_cached_thumbnail(url: str) -> Path | None:
    """Return the cached thumbnail path if it exists, else None."""
    path = _cache_path(url)
    if path.exists():
        try:
            if path.stat().st_size > _CACHE_MAX_BYTES:
                raise ValueError("Oversized cached thumbnail")
            content = path.read_bytes()
            image = decode_image(content, max_pixels=THUMBNAIL_MAX_PIXELS)
            if not content.startswith(b"\x89PNG\r\n\x1a\n") or max(image.size) > 2048:
                _publish_cache(path, thumbnail_png(image))
            return path
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Cannot remove an invalid cached thumbnail")
    return None


def _publish_cache(path: Path, content: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".thumb-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def fetch_thumbnail(url: str) -> Path | None:
    """Fetch a thumbnail from a URL and cache it on disk.

    Returns the cache path on success, None on failure (network error,
    invalid image, etc.). Never raises — failures are logged and return
    None so the caller can show a placeholder.
    """
    if not url:
        return None

    try:
        cached = get_cached_thumbnail(url)
        if cached is not None:
            return cached
        image = fetch_image(url, max_bytes=THUMBNAIL_MAX_BYTES,
                            max_pixels=THUMBNAIL_MAX_PIXELS, timeout=_TIMEOUT_SECONDS)
        path = _cache_path(url)
        _publish_cache(path, thumbnail_png(image))
        return path
    except Exception:
        logger.warning("Thumbnail download or decoding failed")
        return None


def clear_cache() -> int:
    """Clear all cached thumbnails. Returns the number of files removed."""
    cache_dir = get_cache_dir()
    if not cache_dir.exists():
        return 0
    count = 0
    for f in cache_dir.glob("*.png"):
        f.unlink()
        count += 1
    return count
