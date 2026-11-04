"""Object art — the material anchor tables shared by the 2D object sprites and the 3D builders (Phase 17 L3.0, #387).

Standard library only (no Qt, no numpy — pinned by an AST scan in
``tests/unit/test_object_sprite_conformance.py``):

- ``materials`` — ``MATERIALS``, ``EMBER``, ``FLAME``, ``TONE_KEYS``, ``mat``:
  the five-tone material anchors used by ``scripts/generate_object_sprites.py``
  and ``core/scene3d/builders/palette.py``.
"""

from __future__ import annotations

from .materials import EMBER, FLAME, MATERIALS, TONE_KEYS, mat

__all__ = ["EMBER", "FLAME", "MATERIALS", "TONE_KEYS", "mat"]

