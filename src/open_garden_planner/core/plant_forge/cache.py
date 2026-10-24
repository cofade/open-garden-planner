"""Memory-bounded LRU cache for forged plant meshes (Phase 17 L3.1, #387).

Caches ``tuple[MeshPart, ...]`` keyed by ``(sprite_group, sprite_name, seed, lod,
height_q, radius_q, extra_sig)`` with a bounded LRU eviction policy so repeated
plant builds, camera LOD switches, or undo/redo snapshots hit in O(1).

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from typing import TypeAlias

from ..scene3d.mesh import MeshPart

CacheKey: TypeAlias = tuple[str, str, int, int, int, int, str]


def make_cache_key(
    sprite_group: str,
    sprite_name: str,
    seed: int,
    lod: int,
    height_cm: float,
    radius_cm: float,
    extra_sig: str = "",
) -> CacheKey:
    """Build a canonical hashable cache key with 0.01 cm dimension quantisation."""
    return (
        str(sprite_group),
        str(sprite_name),
        int(seed),
        int(lod),
        int(round(float(height_cm) * 100.0)),
        int(round(float(radius_cm) * 100.0)),
        str(extra_sig),
    )


class ForgeCache:
    """Bounded LRU cache mapping ``CacheKey`` to ``tuple[MeshPart, ...]``."""

    def __init__(self, max_entries: int = 512) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be >= 1, got {max_entries}")
        self._max_entries = int(max_entries)
        self._store: OrderedDict[CacheKey, tuple[MeshPart, ...]] = OrderedDict()
        self.hits: int = 0
        self.misses: int = 0

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0

    def get(self, key: CacheKey) -> tuple[MeshPart, ...] | None:
        parts = self._store.get(key)
        if parts is not None:
            self._store.move_to_end(key)
            self.hits += 1
            return parts
        self.misses += 1
        return None

    def put(self, key: CacheKey, parts: tuple[MeshPart, ...]) -> tuple[MeshPart, ...]:
        self._store[key] = parts
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)
        return parts

    def get_or_build(
        self,
        key: CacheKey,
        builder: Callable[[], tuple[MeshPart, ...]],
    ) -> tuple[MeshPart, ...]:
        cached = self.get(key)
        if cached is not None:
            return cached
        built = builder()
        return self.put(key, built)


DEFAULT_FORGE_CACHE = ForgeCache(max_entries=512)

__all__ = [
    "CacheKey",
    "DEFAULT_FORGE_CACHE",
    "ForgeCache",
    "make_cache_key",
]

