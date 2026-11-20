"""Placement and editing of reference points (#666, ADR-080).

One dialog serves both gestures: a click on the canvas (create) and a
double-click on the point (edit). Every write is one undoable command, and the
object itself is still the ordinary circle record plus additive metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from PyQt6.QtCore import QCoreApplication, QPointF
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QLabel,
    QLineEdit,
    QMenu,
    QSpinBox,
)

from open_garden_planner.core import reference_points as ref
from open_garden_planner.core.commands import ChangePropertyCommand, CreateItemCommand
from open_garden_planner.core.object_types import get_translated_display_name
from open_garden_planner.core.snap.geometry import item_edges
from open_garden_planner.ui.canvas.items.reference_point_item import (
    ReferencePointItem,
    nearest_contour_position,
)
from open_garden_planner.ui.dialogs.properties_dialog import ColorButton

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


@dataclass(frozen=True)
class PointProperties:
    """The editable appearance and binding of one reference point."""

    name: str
    parent_id: UUID | None = None
    on_contour: bool = False
    size_mode: str = ref.SIZE_MODE_PLAN
    size: float = ref.DEFAULT_SIZE_CM
    color: str = ref.DEFAULT_COLOR
    stroke_width: float = ref.DEFAULT_STROKE_WIDTH

    @classmethod
    def from_item(cls, item: ReferencePointItem) -> PointProperties:
        metadata = item.metadata
        return cls(
            name=item.name,
            parent_id=ref.parent_id(metadata),
            on_contour=ref.on_contour(metadata),
            size_mode=ref.size_mode(metadata),
            size=ref.size_value(metadata),
            color=ref.color(metadata),
            stroke_width=ref.stroke_width(metadata),
        )

    def to_metadata(self) -> dict[str, Any]:
        return ref.build_metadata(
            parent=self.parent_id,
            on_contour_value=self.on_contour,
            mode=self.size_mode,
            size=self.size,
            colour=self.color,
            stroke=self.stroke_width,
        )


def parent_name(item: Any) -> str:
    """A stable, readable label for the attachment combo."""
    label = item.name or (
        get_translated_display_name(item.object_type) if item.object_type else ""
    )
    return f"{label} [{str(item.item_id)[:8]}]"


def reference_status(item: ReferencePointItem) -> str:
    """The one-line state shown in the status bar and the tooltip."""
    parent_uuid = ref.parent_id(item.metadata)
    if parent_uuid is None:
        return QCoreApplication.translate("ReferencePoints", "Independent point")
    parent = item.binding_parent
    if parent is None:
        # A deleted parent leaves the datum where it is; it reads as
        # independent until its next edit clears the dangling key.
        return QCoreApplication.translate("ReferencePoints", "Independent point")
    name = parent_name(parent)
    if ref.on_contour(item.metadata):
        return QCoreApplication.translate("ReferencePoints", "On outline of: {name}").format(name=name)
    return QCoreApplication.translate("ReferencePoints", "Attached to: {name}").format(name=name)


def reference_summary(item: ReferencePointItem) -> str:
    mode = ref.size_mode(item.metadata)
    unit = QCoreApplication.translate("ReferencePoints", "px") if mode == ref.SIZE_MODE_SCREEN else QCoreApplication.translate("ReferencePoints", "cm")
    return QCoreApplication.translate("ReferencePoints", "{name}\n{status}\nSymbol: {size} {unit}; stroke: {width} px").format(
        name=item.name,
        status=reference_status(item),
        size=f"{ref.size_value(item.metadata):g}",
        unit=unit,
        width=f"{ref.stroke_width(item.metadata):g}",
    )


def _contour_parents(
    view: CanvasView, item: ReferencePointItem | None
) -> list[Any]:
    """Top-level shapes with a straight outline that may own a point."""
    scene = view._canvas_scene
    candidates: list[Any] = []
    for candidate in scene.items():
        if candidate is item or not candidate.isVisible():
            continue
        if candidate.parentItem() is not None:
            continue
        if ref.is_reference_point(candidate):
            continue
        if not (candidate.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
            continue
        if next(iter(item_edges(candidate)), None) is None:
            continue
        candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda candidate: (getattr(candidate, "name", ""), str(getattr(candidate, "item_id", ""))),
    )


def _nearest_parent(
    view: CanvasView, position: QPointF, candidates: list[Any]
) -> tuple[UUID | None, bool]:
    """The contour within eight screen pixels of *position*, if any."""
    threshold = 8.0 / max(view._zoom_factor, 0.01)
    best: tuple[UUID | None, float] | None = None
    for candidate in candidates:
        projection = nearest_contour_position(candidate, position)
        if projection is None or projection[1] > threshold:
            continue
        if best is None or projection[1] < best[1]:
            best = (candidate.item_id, projection[1])
    return (best[0], True) if best is not None else (None, False)


def point_dialog(
    view: CanvasView,
    item: ReferencePointItem | None = None,
    position: QPointF | None = None,
) -> PointProperties | None:
    """Ask for a point's name, binding and look; ``None`` on Cancel."""
    dialog = QDialog(view)
    dialog.setWindowTitle(QCoreApplication.translate("ReferencePoints", "Reference point"))
    form = QFormLayout(dialog)
    options = PointProperties.from_item(item) if item is not None else PointProperties("")

    name_edit = QLineEdit(item.name if item is not None else "", dialog)
    form.addRow(QCoreApplication.translate("ReferencePoints", "Name"), name_edit)

    candidates = _contour_parents(view, item)
    if item is not None:
        current_parent = item.binding_parent
        if current_parent is not None and current_parent not in candidates:
            # A parent inside a group is still a valid binding; keep it in the
            # combo so editing the point cannot silently detach it.
            candidates.append(current_parent)
            candidates.sort(
                key=lambda candidate: (
                    getattr(candidate, "name", ""),
                    str(getattr(candidate, "item_id", "")),
                )
            )
    parents = QComboBox(dialog)
    parents.setObjectName("reference_point_parent")
    parents.addItem(QCoreApplication.translate("ReferencePoints", "Independent point"), None)
    for candidate in candidates:
        parents.addItem(parent_name(candidate), candidate.item_id)

    parent_id = options.parent_id
    contour_hint = False
    if item is None and position is not None:
        parent_id, contour_hint = _nearest_parent(view, position, candidates)
    index = parents.findData(parent_id)
    parents.setCurrentIndex(max(0, index))
    form.addRow(QCoreApplication.translate("ReferencePoints", "Attached to"), parents)

    contour = QCheckBox(QCoreApplication.translate("ReferencePoints", "Keep on the parent outline"), dialog)
    contour.setObjectName("reference_point_on_contour")
    contour.setChecked(options.on_contour or contour_hint)
    form.addRow(contour)

    sizing = QComboBox(dialog)
    sizing.setObjectName("reference_point_sizing")
    sizing.addItem(QCoreApplication.translate("ReferencePoints", "Fixed in plan (scales with zoom)"), ref.SIZE_MODE_PLAN)
    sizing.addItem(QCoreApplication.translate("ReferencePoints", "Constant on screen"), ref.SIZE_MODE_SCREEN)
    sizing.setCurrentIndex(
        0 if options.size_mode == ref.SIZE_MODE_PLAN else 1
    )
    form.addRow(QCoreApplication.translate("ReferencePoints", "Size mode"), sizing)

    size = QSpinBox(dialog)
    size.setObjectName("reference_point_size")
    size.setRange(int(ref.MIN_SIZE), int(ref.MAX_SIZE_PLAN))
    size.setValue(round(options.size))
    form.addRow(QCoreApplication.translate("ReferencePoints", "Symbol size"), size)

    colour = ColorButton(QColor(options.color), dialog)
    colour.setObjectName("reference_point_color")
    form.addRow(QCoreApplication.translate("ReferencePoints", "Color"), colour)

    width = QDoubleSpinBox(dialog)
    width.setObjectName("reference_point_width")
    width.setRange(0.5, 8.0)
    width.setSingleStep(0.5)
    width.setSuffix(QCoreApplication.translate("ReferencePoints", " px"))
    width.setValue(options.stroke_width)
    form.addRow(QCoreApplication.translate("ReferencePoints", "Stroke width"), width)

    status = QLabel(dialog)
    status.setWordWrap(True)
    form.addRow(status)

    def update_controls() -> None:
        has_parent = parents.currentData() is not None
        contour.setEnabled(has_parent)
        if not has_parent:
            contour.setChecked(False)
        mode = sizing.currentData()
        size.setSuffix(QCoreApplication.translate("ReferencePoints", " cm") if mode == ref.SIZE_MODE_PLAN else QCoreApplication.translate("ReferencePoints", " px"))
        size.setRange(
            int(ref.MIN_SIZE),
            int(ref.MAX_SIZE_SCREEN if mode == ref.SIZE_MODE_SCREEN else ref.MAX_SIZE_PLAN),
        )
        status.setText(
            QCoreApplication.translate("ReferencePoints", "On outline of: {name}").format(name=parents.currentText())
            if has_parent and contour.isChecked()
            else QCoreApplication.translate("ReferencePoints", "Attached to: {name}").format(name=parents.currentText())
            if has_parent
            else QCoreApplication.translate("ReferencePoints", "Independent point")
        )

    parents.currentIndexChanged.connect(update_controls)
    contour.toggled.connect(update_controls)
    sizing.currentIndexChanged.connect(update_controls)
    update_controls()

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=dialog,
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    name_edit.setFocus()

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return PointProperties(
        name=name_edit.text().strip(),
        parent_id=cast(UUID | None, parents.currentData()),
        on_contour=contour.isChecked() and contour.isEnabled(),
        size_mode=cast(str, sizing.currentData()),
        size=float(size.value()),
        color=colour.color.name(QColor.NameFormat.HexArgb),
        stroke_width=width.value(),
    )


def _apply_properties(item: ReferencePointItem, value: tuple[PointProperties, QPointF]) -> None:
    options, position = value
    item.name = options.name
    for key in (
        ref.MARKER,
        ref.PARENT_ID,
        ref.ON_CONTOUR,
        ref.SIZE_MODE,
        ref.SIZE,
        ref.COLOR,
        ref.STROKE_WIDTH,
    ):
        item.metadata.pop(key, None)
    item.metadata.update(options.to_metadata())
    item.setFlag(
        QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
        options.size_mode == ref.SIZE_MODE_SCREEN,
    )
    item.set_radius_centered(options.size / 2.0)
    item.stroke_color = QColor(options.color)
    item.stroke_width = options.stroke_width
    pen = QPen(item.pen())
    pen.setColor(QColor(options.color))
    pen.setWidthF(options.stroke_width)
    item.setPen(pen)
    parent_item = item.parentItem()
    item.setPos(
        parent_item.mapFromScene(position) if parent_item is not None else position
    )
    item.prepareGeometryChange()
    item.update()


def _usable_layer(view: CanvasView, parent: QGraphicsItem | None) -> Any | None:
    scene = view._canvas_scene
    if parent is not None:
        layer_id = getattr(parent, "layer_id", None)
        if isinstance(layer_id, UUID):
            parent_layer = scene.get_layer_by_id(layer_id)
            if parent_layer is not None and not parent_layer.locked and parent_layer.visible:
                return parent_layer
    active = scene.active_layer
    if active is not None and not active.locked and active.visible:
        return active
    return next(
        (
            layer
            for layer in sorted(scene.layers, key=lambda item: -item.z_order)
            if not layer.locked and layer.visible
        ),
        None,
    )


def place_reference_point(view: CanvasView, position: QPointF) -> bool:
    """Create a point at *position* through the dialog, as one undo step."""
    options = point_dialog(view, None, position)
    if options is None:
        return False
    scene = view._canvas_scene
    parent = scene.find_item_by_id(options.parent_id) if options.parent_id else None
    layer = _usable_layer(view, parent)
    if layer is None:
        view.set_status_message(QCoreApplication.translate("ReferencePoints", "Choose a visible, unlocked layer to place a reference point."))
        return False
    if options.on_contour and parent is not None:
        projection = nearest_contour_position(parent, position)
        if projection is not None:
            position = projection[0]
    item = ReferencePointItem(
        position.x(),
        position.y(),
        options.size / 2.0,
        name=options.name,
        metadata=options.to_metadata(),
        layer_id=layer.id,
    )
    view.command_manager.execute(
        CreateItemCommand(
            scene, item, QCoreApplication.translate("Commands", "reference point")
        )
    )
    scene.clearSelection()
    item.setSelected(True)
    view.set_status_message(reference_status(item))
    return True


def edit_reference_point(item: ReferencePointItem) -> None:
    """Edit an existing point; appearance, binding and position are one step."""
    raw_scene = item.scene()
    if raw_scene is None or not raw_scene.views():
        return
    scene = cast("CanvasScene", raw_scene)
    view = cast("CanvasView", scene.views()[0])
    layer = scene.get_layer_by_id(item.layer_id) if item.layer_id else None
    if layer is not None and layer.locked:
        view.set_status_message(
            QCoreApplication.translate(
                "ReferencePoints", "Unlock the layer to edit this reference point."
            )
        )
        return
    options = point_dialog(view, item)
    if options is None:
        return
    old_position = item.mapToScene(item.rect().center())
    new_position = QPointF(old_position)
    if options.on_contour and options.parent_id is not None:
        parent = scene.find_item_by_id(options.parent_id)
        if parent is not None:
            projection = nearest_contour_position(parent, item.mapToScene(item.rect().center()))
            if projection is not None:
                new_position = projection[0]
    old = (PointProperties.from_item(item), old_position)
    new = (options, new_position)
    if old == new:
        return

    view.command_manager.execute(
        ChangePropertyCommand(item, "Reference point", old, new, _apply_properties)
    )
    view.set_status_message(reference_status(item))


def reference_context_menu(item: ReferencePointItem) -> tuple[QMenu, Any]:
    """The usual object actions, routed through the existing view commands.

    The lock action is returned so the caller can dispatch it after ``exec``
    (a menu-wide trigger hook would also fire for Edit, Copy and Delete).
    """
    raw_scene = item.scene()
    menu = QMenu()
    if raw_scene is None or not raw_scene.views():
        return menu, None
    scene = cast("CanvasScene", raw_scene)
    view = cast("CanvasView", scene.views()[0])
    layer = scene.get_layer_by_id(item.layer_id) if item.layer_id else None
    editable = layer is not None and not layer.locked
    if editable and not item.isSelected():
        scene.clearSelection()
        item.setSelected(True)

    edit = menu.addAction(QCoreApplication.translate("ReferencePoints", "Edit reference point…"))
    assert edit is not None
    edit.setObjectName("reference_edit")
    edit.setEnabled(editable)
    edit.triggered.connect(lambda: edit_reference_point(item))

    layer_menu = item._build_move_to_layer_menu(menu)
    if layer_menu is not None:
        layer_menu.setEnabled(editable)
        layer_menu.triggered.connect(lambda action: item._dispatch_move_to_layer(action.data()))
    arrange_menu = item._build_arrange_menu(menu)
    arrange_menu.setEnabled(editable)
    arrange_menu.triggered.connect(lambda action: item._dispatch_arrange(action.data()))

    menu.addSeparator()
    lock_action = item.build_lock_context_menu(menu)
    menu.addSeparator()

    copy = menu.addAction(QCoreApplication.translate("GardenPlannerApp", "&Copy"))
    duplicate = menu.addAction(QCoreApplication.translate("CircleItem", "Duplicate"))
    delete = menu.addAction(QCoreApplication.translate("CircleItem", "Delete"))
    assert copy is not None and duplicate is not None and delete is not None
    copy.setEnabled(editable)
    copy.triggered.connect(view.copy_selected)
    duplicate.setEnabled(editable)
    duplicate.triggered.connect(view.duplicate_selected)
    delete.setEnabled(editable)
    delete.triggered.connect(view._delete_selected_items)
    return menu, lock_action
