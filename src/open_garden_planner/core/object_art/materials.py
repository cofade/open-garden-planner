"""The object-sprite material tables — one source for the 2D object SVGs and the 3D builders.

Every furniture and infrastructure sprite in ``resources/objects/`` is coloured from
``MATERIALS`` (plus the ``EMBER`` and ``FLAME`` triads for fire features). Until Phase 17
L3.0 (#387) these tables lived in ``scripts/generate_object_sprites.py`` and
``core/scene3d/builders/palette.py`` mirrored the entries the 3D builders needed. Now
there is one home:

- ``scripts/generate_object_sprites.py`` loads this module by file path (so the
  script needs nothing beyond the standard library, no PyQt6 and no numpy) and emits
  byte-identical SVGs (pinned by ``tests/unit/test_object_sprite_conformance.py``);
- ``core/scene3d/builders/palette.py`` reads ``MATERIALS`` directly at runtime.

Standard library only (pinned by an AST scan in ``tests/unit/test_object_sprite_conformance.py``).
"""

# ruff: noqa: C408 - dict() keyword style matches the sprite generator tables.

from __future__ import annotations

from typing import Final

#: The five tone keys every entry of ``MATERIALS`` defines:
#: crown light, mid body, rim dark, contact occlusion, and line detail.
TONE_KEYS: Final[tuple[str, str, str, str, str]] = ("light", "mid", "dark", "occ", "line")


def mat(light: str, mid: str, dark: str, occ: str, line: str) -> dict[str, str]:
    """Construct one five-tone material dictionary."""
    return {"light": light, "mid": mid, "dark": dark, "occ": occ, "line": line}


#: Material name -> five-tone hex table (``light``, ``mid``, ``dark``, ``occ``, ``line``).
MATERIALS: dict[str, dict[str, str]] = {
    # woods
    "oak": mat("#dcae70", "#b98350", "#7d5029", "#3f2510", "#8f5c2e"),
    "teak": mat("#c98f56", "#a06a3a", "#69401c", "#33200c", "#7c4c24"),
    "pine": mat("#efd8a0", "#d4b471", "#9e7c40", "#54401e", "#ab8c4c"),
    "walnut": mat("#8f5f3c", "#66432c", "#3f2617", "#1e1109", "#4e3220"),
    "grey_wood": mat("#bdb7aa", "#918a7a", "#5f584b", "#34302a", "#726b5d"),
    "charcoal_wood": mat("#4a4441", "#2f2a28", "#191614", "#0a0908", "#3a3432"),
    "shingle": mat("#a89c8c", "#78695a", "#4b4037", "#231d18", "#5f5246"),
    # metals
    "steel": mat("#eaedf0", "#adb4bc", "#626b73", "#2c3237", "#8e979f"),
    "iron": mat("#7e838a", "#4c525a", "#262a2f", "#0f1113", "#3c424a"),
    "brass": mat("#f4dc8e", "#cca84e", "#8d6d24", "#4a380f", "#ab8930"),
    # enamels & plastics
    "enamel_black": mat("#70757a", "#313538", "#131517", "#050506", "#45494d"),
    "enamel_green": mat("#83b67e", "#3f7c3e", "#204c22", "#0e2810", "#2e612f"),
    "enamel_red": mat("#f28d7d", "#cb3b2d", "#821b13", "#470c07", "#a52b20"),
    "plastic_green": mat("#73ab6e", "#3e7c3c", "#214c21", "#0e2810", "#306c30"),
    "plastic_blue": mat("#84b6ea", "#427bc2", "#224c82", "#10294c", "#3162a2"),
    "plastic_yellow": mat("#fbe792", "#e9c33f", "#a8861c", "#5a470c", "#c9a52a"),
    "rubber": mat("#5c5f63", "#303336", "#151719", "#050606", "#404447"),
    # fabrics
    "canvas_cream": mat("#fcf6e8", "#eee1c6", "#cbba95", "#8b7a58", "#dacba6"),
    "canvas_blue": mat("#a1c0e5", "#5e89bf", "#315787", "#182d4c", "#4c74aa"),
    "canvas_red": mat("#f4a391", "#d65d4b", "#913024", "#4a150e", "#ba4b3c"),
    "canvas_green": mat("#accf9d", "#71a661", "#406e37", "#213c1c", "#5c8b4e"),
    "canvas_grey": mat("#dad7d1", "#aca79e", "#716c62", "#3e3a33", "#918c82"),
    "canvas_teal": mat("#9fd3cf", "#4f9d97", "#27625e", "#12332f", "#3f817c"),
    # minerals
    "terracotta": mat("#eaa377", "#ca7341", "#8c4523", "#4a220e", "#aa5c31"),
    "stone": mat("#d2cdc3", "#a29d93", "#68645c", "#383632", "#837e75"),
    "sandstone": mat("#e5d5b6", "#c4ae86", "#8c7756", "#4a3e2c", "#a28e68"),
    "concrete": mat("#d5d5d2", "#abaca8", "#717370", "#404240", "#8e8f8b"),
    "ash": mat("#c9c5bd", "#8f8b83", "#57544e", "#2b2925", "#6f6b64"),
    # translucent / liquid / ground
    "glass": mat("#f4faff", "#c0dcf0", "#82accb", "#476f8f", "#e8f4fc"),
    "water": mat("#a6dff2", "#43a3d2", "#1e6291", "#0f3a5a", "#cbf0fb"),
    "soil": mat("#7d5c3e", "#573c26", "#352111", "#1a0f06", "#6b4b30"),
    "compost": mat("#725232", "#4c3521", "#2d1d10", "#140c05", "#8b6c3c"),
    "sand": mat("#f6e8c6", "#e4d0a0", "#bfa872", "#8a754a", "#d4bd8a"),
    "grass_bit": mat("#a9d77a", "#5f9a3c", "#2f5c1c", "#1b3a10", "#4a7f2c"),
}

#: Fire-pit / BBQ ember triad (highlight, mid, dark).
EMBER: Final[tuple[str, str, str]] = ("#fff4b0", "#ff9d3e", "#c8421a")
#: Fire-pit flame triad (highlight, mid, dark).
FLAME: Final[tuple[str, str, str]] = ("#fff7c2", "#ffc23a", "#f0621c")

__all__ = ["EMBER", "FLAME", "MATERIALS", "TONE_KEYS", "mat"]
