"""Local cache for Permapeople companion data (US-G3, issue #318).

Permapeople companion data is CC BY-SA 4.0 and must be credited before it
ships. The cache is keyed by scientific name (lower-cased per ADR-016) and
stores the raw companion relationships with a ``retrieved_at`` timestamp.

The cache is loaded by ``CompanionPlantingService`` as a third tier after
bundled + custom rules. Conflicts (bundled says beneficial, provider says
antagonistic) → bundled wins, provider entry kept with a ``conflict`` flag.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_DIR_NAME = "companion_cache"
_CACHE_FILE_NAME = "permapeople.json"

# In-memory cache to avoid re-reading the file on every access
_memory_cache: dict[str, Any] | None = None


def get_cache_dir() -> Path:
    """Return the companion cache directory, creating it if needed."""
    from PyQt6.QtCore import QStandardPaths

    app_data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    cache_dir = Path(app_data) / _CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_cache_path() -> Path:
    """Return the cache file path."""
    return get_cache_dir() / _CACHE_FILE_NAME


def _load_cache_from_disk() -> dict[str, Any]:
    """Load the companion cache from disk.

    Returns:
        Dict mapping scientific names (lower-cased) to their companion data.
        Returns an empty dict if the cache file doesn't exist or is invalid.
    """
    path = get_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("Failed to load companion cache: %s", exc)
    return {}


def load_cache() -> dict[str, Any]:
    """Get the companion cache, loading from disk on first access.

    Returns:
        Dict mapping scientific names (lower-cased) to their companion data.
    """
    global _memory_cache
    if _memory_cache is None:
        _memory_cache = _load_cache_from_disk()
    return _memory_cache


def save_cache(cache: dict[str, Any]) -> None:
    """Save the companion cache to disk and update the in-memory copy.

    Args:
        cache: Dict mapping scientific names to their companion data.
    """
    global _memory_cache
    _memory_cache = cache
    path = get_cache_path()
    try:
        path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save companion cache: %s", exc)


def get_cached_companions(scientific_name: str) -> list[dict[str, Any]] | None:
    """Get cached companions for a scientific name.

    Args:
        scientific_name: The plant's scientific name.

    Returns:
        List of companion dicts if cached, None if not.
    """
    cache = load_cache()
    key = scientific_name.lower()
    if key in cache:
        return cache[key].get("companions", [])
    return None


def set_cached_companions(
    scientific_name: str, companions: list[dict[str, Any]]
) -> None:
    """Cache companions for a scientific name.

    Args:
        scientific_name: The plant's scientific name.
        companions: List of companion relationship dicts.
    """
    cache = load_cache()
    key = scientific_name.lower()
    cache[key] = {
        "companions": companions,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    save_cache(cache)


def clear_cache() -> int:
    """Clear the companion cache. Returns the number of entries removed."""
    global _memory_cache
    path = get_cache_path()
    if not path.exists() and _memory_cache is None:
        return 0
    try:
        cache = load_cache()
        count = len(cache)
        _memory_cache = {}
        if path.exists():
            path.unlink()
        return count
    except Exception as exc:
        logger.warning("Failed to clear companion cache: %s", exc)
        return 0
