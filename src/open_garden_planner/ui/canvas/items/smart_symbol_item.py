"""Smart-symbol canvas item (US-C4, #599).

A ``SmartSymbolItem`` is a parametric block: it stores ``symbol_id`` +
``symbol_version`` + ``params`` and **regenerates** its child geometry from a
:class:`SmartSymbolDefinition` rather than storing the expanded shapes. It is a
subclass of :class:`GroupItem`, so it inherits selection/move/rotate, the
type-dispatch sites that treat groups correctly, serialization-of-children, and
DXF export — only the parametric regeneration is new.

Children honour the definition's ``object_type`` field when set (falling back to
the generic shape type when omitted) and apply the standard object styling and
metadata so downstream 2D and 3D pipelines consume them as real domain items.
2D-only construction guides (``guide: true``, or untyped ``LineSpec`` /
``PolylineSpec``) carry ``metadata["smart_symbol_guide"] = True`` so 3D and
analytical shadow casting skip them while 2D and DXF keep them.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, Literal, cast

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsSceneContextMenuEvent

if TYPE_CHECKING:
    from open_garden_planner.models.smart_symbol import SmartSymbolDefinition

from open_garden_planner.models.smart_symbol import (
    CircleSpec,
    LineSpec,
    PolygonSpec,
    PolylineSpec,
    PrimitiveSpec,
    RectSpec,
    SmartSymbolError,
)

from .group_item import GroupItem

logger = logging.getLogger(__name__)


class SmartSymbolItem(GroupItem):
    """A parametric block whose children are regenerated from params."""

    def __init__(
        self,
        symbol_id: str,
        symbol_version: int = 1,
        params: dict[str, Any] | None = None,
        layer_id: uuid.UUID | None = None,
        name: str = "",
    ) -> None:
        super().__init__(layer_id=layer_id, name=name)
        self.symbol_id = symbol_id
        self.symbol_version = symbol_version
        self.params: dict[str, Any] = dict(params or {})
        # Last successfully-resolved geometry, kept so a save embeds a snapshot
        # that survives even if the definition is later removed/changed.
        self._cached_specs: list[PrimitiveSpec] | None = None

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        """Context menu without the inherited Ungroup action.

        Ungrouping a smart symbol would scatter its generated child shapes and
        silently drop the parametric identity (not undoable as a symbol), so it
        is suppressed; only Move to Layer is offered.
        """
        if event is None:
            return
        from PyQt6.QtWidgets import QMenu

        self.normalize_context_menu_selection()
        menu = QMenu()
        # A smart symbol may be GROUPED with other objects, but it is never an
        # Ungroup target (its members are generated from its parameters).
        group_actions = self.build_group_context_menu(menu, allow_ungroup=False)
        if group_actions.offered:
            menu.addSeparator()
        move_layer_menu = self._build_move_to_layer_menu(menu)
        # Arrange submenu (Bring to Front / Forward / Send Backward / Back) —
        # always built, so the menu is never empty (the old isEmpty() guard
        # that papered over a single-layer project is dead now).
        arrange_menu = self._build_arrange_menu(menu)
        action = menu.exec(event.screenPos())
        if self.dispatch_group_action(action, group_actions):
            return
        if move_layer_menu and action and action.parent() is move_layer_menu:
            self._dispatch_move_to_layer(action.data())
        elif arrange_menu and action and action.parent() is arrange_menu:
            self._dispatch_arrange(action.data())

    # ── Geometry ────────────────────────────────────────────────────────────
    def _definition(self) -> SmartSymbolDefinition | None:
        from open_garden_planner.services.smart_symbol_library import (
            get_smart_symbol_library,
        )

        return get_smart_symbol_library().get(self.symbol_id)

    def can_edit_parameters(self) -> bool:
        """Whether a live definition matching ``symbol_version`` is available."""
        definition = self._definition()
        return definition is not None and definition.version == self.symbol_version

    def validate_params(self, candidate_params: dict[str, Any]) -> bool:
        """Return whether *candidate_params* generate valid specs and child items."""
        definition = self._definition()
        if definition is None or definition.version != self.symbol_version:
            return False
        try:
            specs = definition.generate(candidate_params)
            for spec in specs:
                _validate_spec_for_item(spec)
            return True
        except SmartSymbolError as exc:
            logger.warning(
                "Smart symbol %s failed parameter validation: %s",
                self.symbol_id,
                exc,
            )
            return False

    def _resolve_specs(self) -> list[PrimitiveSpec]:
        """Resolve the geometry specs: live definition if available + version
        matches, else the cached snapshot (with a warning)."""
        definition = self._definition()
        if definition is not None and definition.version == self.symbol_version:
            try:
                specs = list(definition.generate(self.params))
                for spec in specs:
                    _validate_spec_for_item(spec)
                self._cached_specs = specs
                return specs
            except SmartSymbolError as exc:
                # Untrusted JSON: a bad expression, divide-by-zero/overflow, a
                # bad round() arg, or an over-budget repeat must never crash the
                # GUI. generate() funnels every such failure into one type, so
                # the last good geometry (cached) is kept and we warn.
                logger.warning("Smart symbol %s failed to generate: %s", self.symbol_id, exc)
        elif definition is not None:
            logger.warning(
                "Smart symbol %s version mismatch (file v%s, instance v%s) — "
                "using cached geometry.",
                self.symbol_id, definition.version, self.symbol_version,
            )
        elif self._cached_specs is None:
            logger.warning("Smart symbol %s definition not found — using cached geometry.",
                           self.symbol_id)
        if self._cached_specs is not None:
            return self._cached_specs
        # No cache and an unusable/absent definition: best-effort when empty.
        if definition is not None:
            try:
                specs = list(definition.generate(self.params))
                for spec in specs:
                    _validate_spec_for_item(spec)
                return specs
            except SmartSymbolError:
                return []
        return []

    def regenerate_geometry(self) -> None:
        """Rebuild child primitives from the current params, preserving the
        group's position/rotation/layer and deterministic child UUIDs."""
        from .garden_item import GardenItemMixin

        definition = self._definition()
        if (
            (definition is None or definition.version != self.symbol_version)
            and self._cached_specs is None
            and self.childItems()
        ):
            logger.warning(
                "Smart symbol %s has no matching definition for v%s — "
                "keeping loaded child geometry.",
                self.symbol_id,
                self.symbol_version,
            )
            return

        if (
            definition is not None
            and definition.version == self.symbol_version
            and self.childItems()
        ):
            try:
                specs = definition.generate(self.params)
                for spec in specs:
                    _validate_spec_for_item(spec)
                self._cached_specs = specs
            except SmartSymbolError as exc:
                logger.warning(
                    "Smart symbol %s failed to generate: %s — keeping existing children.",
                    self.symbol_id,
                    exc,
                )
                return
        else:
            specs = self._resolve_specs()

        new_children = []
        try:
            for idx, spec in enumerate(specs):
                child = _spec_to_item(
                    spec,
                    self.layer_id,
                    parent_symbol_id=self.item_id,
                    fallback_index=idx,
                )
                if child is not None:
                    new_children.append(child)
        except SmartSymbolError as exc:
            logger.warning(
                "Smart symbol %s spec validation failed: %s", self.symbol_id, exc
            )
            if self.childItems():
                return
            new_children = []

        prev_child_links: dict[uuid.UUID, list[uuid.UUID]] = {}
        for old_child in self.childItems():
            if isinstance(old_child, GardenItemMixin) and old_child.child_item_ids:
                prev_child_links[old_child.item_id] = list(old_child.child_item_ids)

        self._clear_children()
        for child in new_children:
            if isinstance(child, GardenItemMixin) and child.item_id in prev_child_links:
                child._child_item_ids = list(prev_child_links[child.item_id])
            child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            child.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            child.setParentItem(self)

    def set_cached_specs(self, specs: list[PrimitiveSpec]) -> None:
        """Seed the fallback snapshot (used when loading a file whose definition
        is missing or version-mismatched, before building children from it)."""
        for spec in specs:
            _validate_spec_for_item(spec)
        self._cached_specs = list(specs)

    def _clear_children(self) -> None:
        for child in list(self.childItems()):
            child.setParentItem(None)
            scene = child.scene()
            if scene is not None:
                scene.removeItem(child)


def _spec_shape_and_default_type(
    spec: PrimitiveSpec,
) -> tuple[Literal["rectangle", "polyline", "polygon", "circle"], Any] | None:
    from open_garden_planner.core.object_types import ObjectType

    if isinstance(spec, RectSpec):
        return "rectangle", ObjectType.GENERIC_RECTANGLE
    if isinstance(spec, (LineSpec, PolylineSpec)):
        return "polyline", ObjectType.FENCE
    if isinstance(spec, PolygonSpec):
        return "polygon", ObjectType.GENERIC_POLYGON
    if isinstance(spec, CircleSpec):
        return "circle", ObjectType.GENERIC_CIRCLE
    return None


def _validate_spec_for_item(spec: PrimitiveSpec) -> Any:
    """Resolve and validate ``spec.object_type`` for its primitive shape class."""
    from open_garden_planner.core.object_types import (
        ObjectType,
        get_valid_types_for_shape,
    )

    info = _spec_shape_and_default_type(spec)
    if info is None:
        raise SmartSymbolError(f"Unsupported smart-symbol spec type: {type(spec).__name__}")
    shape_name, default_type = info
    guide = bool(getattr(spec, "guide", False))
    raw_type = spec.object_type
    if raw_type is None:
        return default_type
    if not isinstance(raw_type, str) or not raw_type:
        raise SmartSymbolError(f"Invalid smart-symbol object_type: {raw_type!r}")
    if guide:
        raise SmartSymbolError(
            f"Guide spec ({shape_name}) cannot also declare object_type {raw_type!r}"
        )
    try:
        obj_type = ObjectType[raw_type]
    except KeyError as exc:
        raise SmartSymbolError(f"Unknown smart-symbol object_type: {raw_type!r}") from exc
    if obj_type not in get_valid_types_for_shape(shape_name):
        raise SmartSymbolError(
            f"object_type {raw_type!r} is incompatible with shape {shape_name!r}"
        )
    return obj_type


def _spec_to_item(
    spec: PrimitiveSpec,
    layer_id: uuid.UUID | None,
    *,
    parent_symbol_id: uuid.UUID | None = None,
    fallback_index: int = 0,
) -> QGraphicsItem | None:
    """Map a Qt-free geometry spec to a concrete typed shape item."""
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    obj_type = _validate_spec_for_item(spec)
    child: Any = None
    if isinstance(spec, RectSpec):
        child = RectangleItem(
            spec.x, spec.y, spec.w, spec.h,
            object_type=obj_type, layer_id=layer_id,
        )
    elif isinstance(spec, LineSpec):
        child = PolylineItem(
            [QPointF(spec.x1, spec.y1), QPointF(spec.x2, spec.y2)],
            object_type=obj_type, layer_id=layer_id,
        )
    elif isinstance(spec, PolylineSpec):
        child = PolylineItem(
            [QPointF(x, y) for x, y in spec.points],
            object_type=obj_type, layer_id=layer_id,
        )
    elif isinstance(spec, PolygonSpec):
        child = PolygonItem(
            [QPointF(x, y) for x, y in spec.points],
            object_type=obj_type, layer_id=layer_id,
        )
    elif isinstance(spec, CircleSpec):
        child = CircleItem(
            spec.cx, spec.cy, spec.r,
            object_type=obj_type, layer_id=layer_id,
        )
    if child is None:
        return None

    member_key = getattr(spec, "member_key", "") or f"e{fallback_index}"
    child.metadata["smart_symbol_member_key"] = member_key
    if parent_symbol_id is not None:
        child._item_id = uuid.uuid5(parent_symbol_id, member_key)

    is_guide = bool(getattr(spec, "guide", False)) or (
        isinstance(spec, (LineSpec, PolylineSpec)) and spec.object_type is None
    )
    if is_guide:
        child.metadata["smart_symbol_guide"] = True

    height_cm = getattr(spec, "height_cm", None)
    if height_cm is not None:
        child.metadata["object_height_cm"] = float(height_cm)

    if getattr(spec, "plain_panel", False):
        child.metadata["smart_symbol_plain_panel"] = True

    return cast(QGraphicsItem, child)
