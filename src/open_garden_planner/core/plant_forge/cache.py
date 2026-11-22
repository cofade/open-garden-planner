"""Memory-bounded LRU cache for forged plant meshes (Phase 17 L3.1, #387).

Caches ``tuple[MeshPart, ...]`` keyed by ``(sprite_group, sprite_name, seed, lod,
height_bucket, radius_bucket, extra_sig)`` with a bounded LRU eviction policy so
repeated plant builds, camera LOD switches, or undo/redo snapshots hit in O(1).

The dimensions are quantised to 2 % geometric buckets (#973): a tree that grows a
little every day keeps one forged shape for a whole bucket, and ``forge_plant``
scales it to the exact height and spread, so a year time-lapse no longer reforges
the tree with new random positions every day. A bucket is ``1.02 ** k`` (1 cm at
``k = 0``); a size below 1 cm uses a negative index.

Qt-free: standard library + NumPy only.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from typing import Final, TypeAlias

from ..scene3d.mesh import MeshPart

CacheKey: TypeAlias = tuple[str, str, int, int, int, int, str]

#: Two sizes this relative step apart share one forged mesh (#973).
QUANT_STEP: Final[float] = 1.02


def size_bucket(value_cm: float) -> int:
    """The 2 % geometric bucket that holds ``value_cm`` (#973)."""
    return int(round(math.log(max(float(value_cm), 1e-6)) / math.log(QUANT_STEP)))


def quantised_size_cm(value_cm: float) -> float:
    """The size a bucket is forged at: ``1 cm * 1.02 ** bucket`` (#973)."""
    return float(QUANT_STEP ** size_bucket(value_cm))


def make_cache_key(
    sprite_group: str,
    sprite_name: str,
    seed: int,
    lod: int,
    height_cm: float,
    radius_cm: float,
    extra_sig: str = "",
) -> CacheKey:
    """Build a canonical hashable cache key with 2 % geometric dimension buckets."""
    return (
        str(sprite_group),
        str(sprite_name),
        int(seed),
        int(lod),
        size_bucket(height_cm),
        size_bucket(radius_cm),
        str(extra_sig),
    )


class ForgeCache:
    """Bounded LRU cache mapping ``CacheKey`` to ``tuple[MeshPart, ...]``."""

    def __init__(self, max_entries: int = 256, max_bytes: int = 64 * 1024 * 1024) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be >= 1, got {max_entries}")
        self._max_entries = int(max_entries)
        if max_bytes < 1:
            raise ValueError("max_bytes must be >= 1")
        self.max_bytes = int(max_bytes)
        self.current_bytes = 0
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
        self.current_bytes = 0
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
        old = self._store.pop(key, None)
        if old is not None:
            self.current_bytes -= self._size(old)
        size = self._size(parts)
        if size > self.max_bytes:
            return parts
        self._store[key] = parts
        self.current_bytes += size
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries or self.current_bytes > self.max_bytes:
            _, evicted = self._store.popitem(last=False)
            self.current_bytes -= self._size(evicted)
        return parts

    @staticmethod
    def _size(parts: tuple[MeshPart, ...]) -> int:
        return sum(array.nbytes for part in parts for array in (
            part.mesh.positions, part.mesh.normals, part.mesh.colors,
            part.mesh.uvs, part.mesh.indices,
        ))

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


DEFAULT_FORGE_CACHE = ForgeCache()

__all__ = [
    "CacheKey",
    "DEFAULT_FORGE_CACHE",
    "ForgeCache",
    "QUANT_STEP",
    "make_cache_key",
    "quantised_size_cm",
    "size_bucket",
]

