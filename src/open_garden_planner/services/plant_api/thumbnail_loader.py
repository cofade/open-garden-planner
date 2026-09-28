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
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_CACHE_DIR_NAME = "plant_thumbs"
_TIMEOUT_SECONDS = 10


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
    return _cache_path(url).exists()


def get_cached_thumbnail(url: str) -> Path | None:
    """Return the cached thumbnail path if it exists, else None."""
    path = _cache_path(url)
    if path.exists():
        return path
    return None


def fetch_thumbnail(url: str) -> Path | None:
    """Fetch a thumbnail from a URL and cache it on disk.

    Returns the cache path on success, None on failure (network error,
    invalid image, etc.). Never raises — failures are logged and return
    None so the caller can show a placeholder.
    """
    if not url:
        return None

    # Check cache first
    cached = get_cached_thumbnail(url)
    if cached is not None:
        return cached

    try:
        response = requests.get(url, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        content = response.content
        if not content:
            logger.warning("Empty thumbnail response for %s", url)
            return None

        # Validate Content-Type is an image
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            logger.warning(
                "Unexpected Content-Type '%s' for thumbnail %s", content_type, url
            )
            return None

        # Write to cache
        path = _cache_path(url)
        path.write_bytes(content)
        return path
    except Exception as exc:
        logger.warning("Failed to fetch thumbnail %s: %s", url, exc)
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
