"""Render a PNG of the live canvas for the Agent API (US-D1.3).

Unlike ``queries.py``/``diagnostics.py`` (deliberately Qt-free), this module
genuinely touches Qt — it builds a ``QImage``/``QPainter`` and reads live scene
items. ``render_canvas_image`` must run on the Qt main thread (marshaled via
``MainThreadBridge.run_on_main``, same as the other providers).

Coordinate-frame note: the read tools report object positions in the native
scene frame (cm, CAD Y-up per ADR-002 — origin bottom-left, +y north/up).
``render_scene_region``'s ``y_flip=True`` (kept for visual parity with the live
CAD view and every other export) means the output PNG is also Y-up — north at
the top — so a scene point's pixel ROW is inverted relative to its scene y
(pixel rows count top-down). See ``RenderMeta.px_per_cm``'s field description in
``schema.py`` for the exact correction formula, and
``tests/unit/test_agent_api_render_coordinate_frame.py`` for the empirical proof.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from PyQt6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.scene_rendering import (
    compute_export_font_size,
    render_scene_region,
)

MIN_IMAGE_PX = 128
MAX_IMAGE_PX = 2048
DEFAULT_IMAGE_PX = 1024


def resolve_image_pixel_size(
    region_width_cm: float,
    region_height_cm: float,
    image_width_px: int,
    *,
    min_px: int = MIN_IMAGE_PX,
    max_px: int = MAX_IMAGE_PX,
) -> tuple[int, int]:
    """Clamp the requested width and derive+clamp height, preserving aspect ratio.

    Both dimensions are independently clamped to ``[min_px, max_px]`` so a
    pathological region aspect ratio (e.g. a 1cm x 10 000cm strip) can't turn a
    modest width request into a runaway-large image. At that extreme (still
    out of range on the *other* axis even after the first correction), the
    final pair no longer preserves the requested aspect ratio exactly — a
    bounded image is the right tradeoff over a faithful but enormous one, but
    it means the caller's uniform ``px_per_cm`` (derived from width) is not
    exact for the Y axis in this edge case.
    """
    if region_width_cm <= 0 or region_height_cm <= 0:
        raise ValueError("region_width_cm and region_height_cm must be positive.")
    width_px = max(min_px, min(max_px, image_width_px))
    aspect = region_height_cm / region_width_cm
    height_px = round(width_px * aspect)
    if height_px > max_px:
        height_px = max_px
        width_px = round(height_px / aspect)
    elif height_px < min_px:
        height_px = min_px
        width_px = round(height_px / aspect)
    width_px = max(min_px, min(max_px, width_px))
    height_px = max(min_px, min(max_px, height_px))
    return width_px, height_px


@contextmanager
def _hidden_layers_not_in(
    scene: QGraphicsScene, allowed: list[str] | None
) -> Iterator[None]:
    """Temporarily force layer-bearing item visibility to match ``allowed``.

    Matches by layer id or layer name, mirroring
    ``agent_api.queries._layer_matches`` but over live scene items instead of
    a snapshot dict. ``allowed=None`` renders the scene's current live
    visibility as-is (no filtering). Unknown names in ``allowed`` are
    tolerated — they simply match nothing.

    This is a **full override**, not a subtractive filter: an allowed layer
    the user currently has toggled off in the Layers panel is shown anyway
    (an agent asking for "Layer A" gets Layer A, regardless of an unrelated
    live UI toggle it can't see), and every layer-bearing item's *original*
    visibility — shown or hidden — is restored afterward, not just the ones
    this function itself hid. A ``GroupItem``/``SmartSymbolItem`` child whose
    own layer differs from its (forced-hidden) parent group's is suppressed
    too — Qt hides descendants of a hidden item regardless of the child's own
    layer — the same inherent limitation ``_hidden_overlay_items``/
    ``_hidden_construction_items`` already have.
    """
    if allowed is None:
        yield
        return
    names_by_id = {str(layer.id): layer.name for layer in getattr(scene, "layers", [])}
    wanted = set(allowed)
    layer_items = [
        item
        for item in scene.items()
        if hasattr(item, "layer_id") and item.layer_id is not None
    ]
    # Snapshot every original state in a first pass, before mutating anything,
    # so a restore is never left partial if a later setVisible() ever raised.
    original = [(item, item.isVisible()) for item in layer_items]
    for item in layer_items:
        lid = str(item.layer_id)
        should_show = lid in wanted or names_by_id.get(lid, "") in wanted
        item.setVisible(should_show)
    try:
        yield
    finally:
        for item, was_visible in original:
            item.setVisible(was_visible)


def render_canvas_image(
    scene: QGraphicsScene,
    region: tuple[float, float, float, float] | None,
    layers: list[str] | None,
    image_width_px: int,
) -> dict[str, Any]:
    """Render a PNG of ``scene`` for the Agent API. Must run on the Qt main thread.

    Resolves the default region (full canvas) internally so "what did we see"
    and "what did we paint" happen on the same hop — no separate snapshot
    call, no race if the canvas is resized in between calls. Returns a
    Qt-free dict: ``png_bytes``, ``region`` (x, y, width, height in scene cm),
    ``image_width_px``, ``image_height_px``, ``px_per_cm``, ``layers_rendered``.
    """
    canvas_rect = scene.canvas_rect if hasattr(scene, "canvas_rect") else scene.sceneRect()
    if region is None:
        source_rect = QRectF(canvas_rect)
    else:
        x, y, width, height = region
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive.")
        source_rect = QRectF(x, y, width, height)

    width_px, height_px = resolve_image_pixel_size(
        source_rect.width(), source_rect.height(), image_width_px
    )
    px_per_cm = width_px / source_rect.width()
    # No physical paper size is involved here (unlike PDF/PNG export) — derive
    # an equivalent drawing scale from the achieved pixel density so text
    # stays legible, reusing the exact same font-sizing formula export_to_png
    # uses, anchored on the same reference DPI it treats as "screen".
    equivalent_scale = px_per_cm * 2.54 / ExportService.DPI_SCREEN
    text_point_size = compute_export_font_size(equivalent_scale, ExportService.DPI_SCREEN)

    image = QImage(width_px, height_px, QImage.Format.Format_ARGB32)
    background = getattr(scene, "CANVAS_COLOR", Qt.GlobalColor.white)
    image.fill(background)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    with _hidden_layers_not_in(scene, layers):
        try:
            render_scene_region(
                scene=scene,
                painter=painter,
                target_rect=QRectF(0, 0, width_px, height_px),
                source_rect=source_rect,
                hide_overlays=True,
                hide_construction=True,
                text_point_size=text_point_size,
                y_flip=True,
            )
        finally:
            painter.end()

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    png_bytes = bytes(buf.data())
    buf.close()

    return {
        "png_bytes": png_bytes,
        "region": (
            source_rect.x(),
            source_rect.y(),
            source_rect.width(),
            source_rect.height(),
        ),
        "image_width_px": width_px,
        "image_height_px": height_px,
        "px_per_cm": px_per_cm,
        "layers_rendered": list(layers) if layers is not None else None,
    }
