"""DXF export and import service for garden plans."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ACI_PALETTE: list[tuple[int, int, int, int]] = [
    (1, 255, 0, 0),
    (2, 255, 255, 0),
    (3, 0, 255, 0),
    (4, 0, 255, 255),
    (5, 0, 0, 255),
    (6, 255, 0, 255),
    (7, 255, 255, 255),
    (8, 65, 65, 65),
    (9, 128, 128, 128),
    (250, 51, 51, 51),
    (251, 80, 80, 80),
    (252, 105, 105, 105),
    (253, 130, 130, 130),
    (254, 190, 190, 190),
    (255, 255, 255, 255),
]


def _rgb_to_aci(r: int, g: int, b: int) -> int:
    """Return the nearest AutoCAD Color Index for an RGB triple."""
    best_aci = 7
    best_dist = float("inf")
    for aci, ar, ag, ab in _ACI_PALETTE:
        dist = (r - ar) ** 2 + (g - ag) ** 2 + (b - ab) ** 2
        if dist < best_dist:
            best_dist = dist
            best_aci = aci
    return best_aci


def _layer_name(scene: QGraphicsScene, item: Any) -> str:
    """Return the OGP layer name for an item, falling back to '0'."""
    layer_id = getattr(item, "layer_id", None)
    if layer_id is not None and hasattr(scene, "get_layer_by_id"):
        layer = scene.get_layer_by_id(layer_id)
        if layer is not None:
            return layer.name
    return "0"


def _is_construction(item: QGraphicsItem) -> bool:
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionCircleItem,
        ConstructionLineItem,
    )

    return isinstance(item, (ConstructionLineItem, ConstructionCircleItem))



def _is_garden_item(item: QGraphicsItem) -> bool:
    from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

    return isinstance(item, GardenItemMixin)


def _item_layer_visible(scene: QGraphicsScene, item: Any) -> bool:
    layer_id = getattr(item, "layer_id", None)
    if layer_id is not None and hasattr(scene, "get_layer_by_id"):
        layer = scene.get_layer_by_id(layer_id)
        if layer is not None:
            return layer.visible
    return True


# ---------------------------------------------------------------------------
# DXF Export
# ---------------------------------------------------------------------------

class DxfExportService:
    """Exports a CanvasScene to an AutoCAD R2010 DXF file.

    1 OGP scene unit (cm) = 1 DXF unit (cm).
    OGP's view Y-flip makes scene Y=0 the visual bottom, which matches DXF Y-up
    convention (Y=0 at bottom), so no coordinate transformation is needed.
    """

    @staticmethod
    def export(scene: CanvasScene, file_path: Path | str) -> None:
        import ezdxf

        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()

        for item in scene.items():
            if not _is_garden_item(item):
                continue
            if _is_construction(item):
                continue
            if not item.isVisible():
                continue
            if not _item_layer_visible(scene, item):
                continue

            layer = _layer_name(scene, item)
            pen_color = getattr(item, "pen", None)
            if callable(pen_color):
                qcolor = item.pen().color()
                aci = _rgb_to_aci(qcolor.red(), qcolor.green(), qcolor.blue())
            else:
                aci = 7

            # Ensure DXF layer exists
            if layer not in doc.layers:
                doc.layers.add(layer, color=aci)

            DxfExportService._export_item(msp, item, layer, aci)

        doc.saveas(str(file_path))

    @staticmethod
    def _export_item(msp: Any, item: QGraphicsItem, layer: str, aci: int) -> None:
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
        from open_garden_planner.ui.canvas.items.group_item import GroupItem
        from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
        from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

        attribs = {"layer": layer, "color": aci}

        if isinstance(item, GroupItem):
            # GroupItem children are also in scene.items() – skip the container
            return

        if isinstance(item, RectangleItem):
            rect: QRectF = item.rect()
            corners_local = [
                rect.topLeft(),
                rect.topRight(),
                rect.bottomRight(),
                rect.bottomLeft(),
            ]
            pts = [item.mapToScene(c) for c in corners_local]
            dxf_pts = [(p.x(), p.y()) for p in pts]
            msp.add_lwpolyline(dxf_pts, close=True, dxfattribs=attribs)

        elif isinstance(item, PolygonItem):
            from PyQt6.QtWidgets import QGraphicsPolygonItem

            if isinstance(item, QGraphicsPolygonItem):
                poly = item.polygon()
                pts = [item.mapToScene(poly.at(i)) for i in range(poly.count())]
                dxf_pts = [(p.x(), p.y()) for p in pts]
                if dxf_pts:
                    msp.add_lwpolyline(dxf_pts, close=True, dxfattribs=attribs)

        elif isinstance(item, PolylineItem):
            pts = [item.mapToScene(p) for p in item.points]
            dxf_pts = [(p.x(), p.y()) for p in pts]
            if len(dxf_pts) >= 2:
                msp.add_lwpolyline(dxf_pts, close=False, dxfattribs=attribs)

        elif isinstance(item, CircleItem):
            rect = item.rect()
            cx_local = rect.center()
            center = item.mapToScene(cx_local)
            radius = rect.width() / 2.0
            msp.add_circle(
                center=(center.x(), center.y()),
                radius=radius,
                dxfattribs=attribs,
            )

        elif isinstance(item, EllipseItem):
            rect = item.rect()
            cx_local = rect.center()
            center = item.mapToScene(cx_local)
            semi_a = rect.width() / 2.0
            semi_b = rect.height() / 2.0
            rotation_deg = item.rotation()
            # DXF ELLIPSE: major_axis is vector from center to end of semi-major axis
            angle_rad = math.radians(rotation_deg)
            if semi_a >= semi_b:
                major = (semi_a * math.cos(angle_rad), semi_a * math.sin(angle_rad), 0.0)
                ratio = semi_b / semi_a if semi_a > 0 else 1.0
            else:
                angle_rad += math.pi / 2
                major = (semi_b * math.cos(angle_rad), semi_b * math.sin(angle_rad), 0.0)
                ratio = semi_a / semi_b if semi_b > 0 else 1.0
            msp.add_ellipse(
                center=(center.x(), center.y(), 0.0),
                major_axis=major,
                ratio=ratio,
                dxfattribs=attribs,
            )


# ---------------------------------------------------------------------------
# DXF Import
# ---------------------------------------------------------------------------

@dataclass
class DxfImportResult:
    """Result of a DXF import operation."""

    items: list[QGraphicsItem] = field(default_factory=list)
    skipped_count: int = 0
    skipped_types: list[str] = field(default_factory=list)


class DxfImportService:
    """Imports DXF entities into a CanvasScene."""

    SUPPORTED_TYPES = {"LINE", "LWPOLYLINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE"}
    ARC_SEGMENTS = 32

    @staticmethod
    def get_dxf_layers(file_path: Path | str) -> list[str]:
        """Return the list of layer names present in a DXF file."""
        import ezdxf

        doc = ezdxf.readfile(str(file_path))
        layers: set[str] = set()
        for entity in doc.modelspace():
            if hasattr(entity, "dxf") and hasattr(entity.dxf, "layer"):
                layers.add(entity.dxf.layer)
        return sorted(layers)

    @staticmethod
    def import_file(
        scene: CanvasScene,
        file_path: Path | str,
        scale_factor: float = 1.0,
        selected_layers: list[str] | None = None,
    ) -> DxfImportResult:
        """Parse a DXF file and return scene items ready to be added.

        The caller is responsible for adding items to the scene via a Command.
        Y-coordinates are negated (DXF Y-up → Qt Y-down) and scaled.
        """
        import ezdxf

        doc = ezdxf.readfile(str(file_path))
        result = DxfImportResult()

        for entity in doc.modelspace():
            dxf_type = entity.dxftype()
            dxf_layer = getattr(entity.dxf, "layer", "0") if hasattr(entity, "dxf") else "0"

            if selected_layers is not None and dxf_layer not in selected_layers:
                continue

            if dxf_type not in DxfImportService.SUPPORTED_TYPES:
                result.skipped_count += 1
                if dxf_type not in result.skipped_types:
                    result.skipped_types.append(dxf_type)
                continue

            layer_id = DxfImportService._get_or_create_layer(scene, dxf_layer)
            item = DxfImportService._entity_to_item(entity, dxf_type, scale_factor, layer_id)
            if item is not None:
                result.items.append(item)
            else:
                result.skipped_count += 1
                if dxf_type not in result.skipped_types:
                    result.skipped_types.append(dxf_type)

        return result

    @staticmethod
    def _get_or_create_layer(scene: CanvasScene, dxf_layer_name: str) -> Any:
        """Return existing OGP layer matching dxf_layer_name or create a new one."""
        from open_garden_planner.models.layer import Layer

        if hasattr(scene, "layers"):
            for layer in scene.layers:
                if layer.name == dxf_layer_name:
                    return layer.id
            # Create new layer
            new_layer = Layer(name=dxf_layer_name)
            if hasattr(scene, "add_layer"):
                scene.add_layer(new_layer)
            elif hasattr(scene, "_layers"):
                scene._layers.append(new_layer)  # type: ignore[attr-defined]
                if hasattr(scene, "layers_changed"):
                    scene.layers_changed.emit()
            # Assign a unique z_order so items on different DXF layers stack
            # deterministically rather than all defaulting to z_order=0.
            new_layer.z_order = len(scene.layers) - 1 if hasattr(scene, "layers") else 0
            return new_layer.id
        return None

    @staticmethod
    def _entity_to_item(
        entity: Any,
        dxf_type: str,
        scale: float,
        layer_id: Any,
    ) -> QGraphicsItem | None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem
        from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
        from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem

        def _s(v: float) -> float:
            return v * scale

        def _y(v: float) -> float:
            # DXF Y-up matches OGP scene Y-up (view flips Y so scene Y=0 is visual
            # bottom, same as DXF). No negation needed.
            return v * scale

        try:
            if dxf_type == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                pts = [QPointF(_s(start.x), _y(start.y)), QPointF(_s(end.x), _y(end.y))]
                return PolylineItem(pts, object_type=ObjectType.GENERIC_POLYGON, layer_id=layer_id)

            if dxf_type == "LWPOLYLINE":
                raw_pts = list(entity.get_points("xy"))
                pts = [QPointF(_s(x), _y(y)) for x, y in raw_pts]
                if len(pts) < 2:
                    return None
                if entity.is_closed and len(pts) >= 3:
                    return PolygonItem(pts, object_type=ObjectType.GENERIC_POLYGON, layer_id=layer_id)
                return PolylineItem(pts, object_type=ObjectType.GENERIC_POLYGON, layer_id=layer_id)

            if dxf_type == "CIRCLE":
                cx = _s(entity.dxf.center.x)
                cy = _y(entity.dxf.center.y)
                r = _s(entity.dxf.radius)
                return CircleItem(
                    cx, cy, r,
                    object_type=ObjectType.GENERIC_CIRCLE,
                    layer_id=layer_id,
                )

            if dxf_type == "ARC":
                # Sample arc into polyline points
                cx = entity.dxf.center.x
                cy = entity.dxf.center.y
                r = entity.dxf.radius
                start_a = math.radians(entity.dxf.start_angle)
                end_a = math.radians(entity.dxf.end_angle)
                if end_a < start_a:
                    end_a += 2 * math.pi
                n = DxfImportService.ARC_SEGMENTS
                pts = []
                for i in range(n + 1):
                    t = start_a + (end_a - start_a) * i / n
                    pts.append(QPointF(_s(cx + r * math.cos(t)), _y(cy + r * math.sin(t))))
                return PolylineItem(pts, object_type=ObjectType.GENERIC_POLYGON, layer_id=layer_id)

            if dxf_type == "ELLIPSE":
                cx = _s(entity.dxf.center.x)
                cy = _y(entity.dxf.center.y)
                major = entity.dxf.major_axis
                ratio = entity.dxf.ratio
                semi_a = _s(math.hypot(major.x, major.y))
                semi_b = semi_a * ratio
                angle_deg = -math.degrees(math.atan2(major.y, major.x))
                item = EllipseItem(
                    cx - semi_a, cy - semi_b, semi_a * 2, semi_b * 2,
                    object_type=ObjectType.GENERIC_ELLIPSE,
                    layer_id=layer_id,
                )
                item.setRotation(angle_deg)
                return item

            if dxf_type == "SPLINE":
                # Sample control points
                control_pts = list(entity.control_points)
                if len(control_pts) < 2:
                    return None
                pts = [QPointF(_s(p[0]), _y(p[1])) for p in control_pts]
                return PolylineItem(pts, object_type=ObjectType.GENERIC_POLYGON, layer_id=layer_id)

        except Exception:
            return None

        return None
