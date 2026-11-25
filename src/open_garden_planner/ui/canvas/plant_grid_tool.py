"""A transient, transformable plant grid that commits as one undo step."""

from __future__ import annotations

from math import atan2, degrees, isfinite
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import (
    QCoreApplication,
    QLineF,
    QPointF,
    QRectF,
    QSignalBlocker,
    Qt,
)
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QTransform
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.settings import AppSettings, get_settings
from open_garden_planner.core.commands import CompoundCommand, CreateItemsCommand, GroupCommand
from open_garden_planner.core.plant_grid import (
    MIN_SPAN_CM,
    cell_centers,
    first_cell_center,
    handle_positions,
    resize_edges,
    snap_cell_span,
)
from open_garden_planner.core.plant_renderer import paint_plant
from open_garden_planner.core.plant_sizing import species_drop_diameter_cm
from open_garden_planner.core.tools.base_tool import BaseTool, ToolType
from open_garden_planner.services import PlantAPIManager
from open_garden_planner.services.bundled_species_db import merge_calendar_data
from open_garden_planner.ui.canvas.items.circle_item import PLANT_FILL_SCALE
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.resize_handle import (
    HANDLE_COLOR,
    HANDLE_HOVER_COLOR,
    HANDLE_SIZE,
    ROTATION_HANDLE_COLOR,
    ROTATION_HANDLE_HOVER_COLOR,
    ROTATION_HANDLE_OFFSET,
    ROTATION_HANDLE_SIZE,
    ROTATION_SNAP_ANGLE,
)
from open_garden_planner.ui.canvas.viewport_overlay import ViewportOverlay
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog
from open_garden_planner.ui.icons import get_icon
from open_garden_planner.ui.plant_creation import build_species_plant, species_object_type
from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

_ACCENT = "#e38127"
_MIN_SPAN = MIN_SPAN_CM  # cm
_MAX_PLANT_DIAMETER = 5000.0  # cm
_MAX_SPAN = 100000.0  # cm
_ROTATION_SNAP_WINDOW = 3.0  # degrees; snap-enabled rotation sticks near a step


class PlantGridTool(BaseTool):
    tool_type = ToolType.PLANT_GRID
    shortcut = ""
    cursor = Qt.CursorShape.CrossCursor
    accepts_typed_coordinates = False
    skip_anchor_snap = True

    def _translated_name(self) -> str:
        return QCoreApplication.translate("PlantGridTool", "Plant Grid")

    def __init__(self, view: CanvasView, scene: CanvasScene) -> None:
        super().__init__(view)
        self._scene = scene
        self._scene.document_replaced.connect(self.cancel)
        self._origin: QPointF | None = None
        self._species: dict[str, Any] | None = None
        self._dimensions = (3, 3)
        self._diameter = 100.0
        self._size_edited = False
        self._center = QPointF()
        self._width = self._height = _MIN_SPAN
        self._angle = 0.0
        self._editing = False
        self._drag: str | tuple[int, int] | None = None
        self._drag_start = QPointF()
        self._before = (QPointF(), 0.0, 0.0, 0.0)
        self._diameter_before = 0.0
        self._size_edited_before = False
        self._press_completed_extent = False
        self._hover: str | tuple[int, int] | None = None
        self._controls: QFrame | None = None
        self._size_button: QToolButton | None = None
        self._size_slider: QSlider | None = None
        self._preview_button: QToolButton | None = None
        self._fields: dict[str, LengthSpinBox] = {}
        # The control strip follows the draft on screen. The overlay owns the
        # subscription to zoom, scrolling and viewport geometry and places the
        # strip from ``_controls_anchor``; a paint never moves it (ADR-082).
        self._overlay: ViewportOverlay | None = None

    @property
    def _viewport(self) -> QWidget:
        viewport = self.view.viewport()
        assert viewport is not None
        return viewport

    def _edit_dimensions(self) -> bool:
        dialog = QDialog(self.view)
        dialog.setWindowTitle(QCoreApplication.translate("PlantGridTool", "Plant Grid"))
        form = QFormLayout(dialog)
        rows, columns = QSpinBox(dialog), QSpinBox(dialog)
        for widget, value in zip((rows, columns), self._dimensions, strict=True):
            widget.setRange(1, AppSettings.PLANT_GRID_MAX_SIDE)
            widget.setValue(value)
        form.addRow(QCoreApplication.translate("PlantGridTool", "Rows"), rows)
        form.addRow(QCoreApplication.translate("PlantGridTool", "Columns"), columns)
        self._dialog_buttons(dialog, form)
        generation = self._scene.document_generation
        accepted = dialog.exec() == QDialog.DialogCode.Accepted and self._is_current(generation)
        if accepted:
            self._dimensions = (rows.value(), columns.value())
            settings = get_settings()
            settings.plant_grid_dimensions = self._dimensions
            settings.sync()
            self._sync_fields()
            self._place_controls()
            self._viewport.update()
        dialog.deleteLater()
        return accepted

    @staticmethod
    def _dialog_buttons(dialog: QDialog, form: QFormLayout) -> None:
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

    def _pick_plant(self) -> bool:
        dialog = PlantSearchDialog(PlantAPIManager.from_settings(), self.view)
        try:
            generation = self._scene.document_generation
            if not dialog.exec() or dialog.selected_plant is None or not self._is_current(generation):
                return False
            self._species = merge_calendar_data(dialog.selected_plant.to_dict())
            diameter = species_drop_diameter_cm(
                self._species, species_object_type(self._species).name,
            )
            self._diameter = (
                max(_MIN_SPAN, min(_MAX_PLANT_DIAMETER, diameter))
                if isfinite(diameter) else 100.0
            )
            self._size_edited = self._diameter != diameter
            self._sync_size_slider()
            self._sync_fields()
            self._place_controls()
            self._viewport.update()
            return True
        finally:
            dialog.deleteLater()

    def _is_current(self, generation: int) -> bool:
        return self.view.active_tool is self and generation == self._scene.document_generation

    def _toggle_plant_size(self, enabled: bool) -> None:
        if self._size_slider is not None and self._controls is not None:
            self._sync_size_slider()
            self._size_slider.setVisible(enabled)
            self._controls.adjustSize()
            self._place_controls()
        self._viewport.update()

    def _sync_size_slider(self) -> None:
        slider = self._size_slider
        if slider is not None:
            with QSignalBlocker(slider):
                slider.setMaximum(max(round(self._diameter), min(round(_MAX_PLANT_DIAMETER), max(200, round(self._diameter * 3)))))
                slider.setValue(round(self._diameter))

    def _slide_plant_size(self, value: int) -> None:
        self._diameter = float(value)
        self._size_edited = True
        self._sync_fields()
        self._viewport.update()

    def _length_field(
        self, key: str, label: str, minimum: float, maximum: float,
    ) -> LengthSpinBox:
        """A units-aware numeric field bound to one piece of the draft."""
        field = LengthSpinBox(parent=self._controls)
        field.setObjectName(f"{key}_field")
        field.setRange(minimum, maximum)
        field.setDecimals(1)
        field.setSingleStep(1.0)
        field.setSuffix(" cm")
        field.setAccessibleName(label)
        field.setToolTip(QCoreApplication.translate(
            "PlantGridTool",
            "Typing a value updates the draft. Units follow Preferences.",
        ))
        field.valueChanged.connect(
            lambda value, name=key: self._field_changed(name, value)
        )
        # A focus-out or Return is the moment a field stops being the editor.
        # Clamping happens in the handler, so the model value can differ from
        # what was typed; without this the field kept showing the unclamped
        # number (a 1 cm spacing on a grid clamped to 2 cm wide, #1021 review).
        field.editingFinished.connect(lambda name=key: self._field_finished(name))
        return field

    def _field_values(self) -> dict[str, float]:
        """The draft's current values, keyed like ``self._fields``."""
        rows, columns = self._dimensions
        return {
            "size": self._diameter,
            "spacing": self._width / columns,
            "width": self._width,
            "height": self._height,
        }

    def _field_finished(self, name: str) -> None:
        """Show the model's value for the field the user just left."""
        field = self._fields.get(name)
        if field is None:
            return
        with QSignalBlocker(field):
            field.setValue(self._field_values()[name])
        self._sync_fields()

    def _sync_fields(self) -> None:
        """Show the draft's current values without re-entering the handlers.

        A field that currently has focus is the authoritative editor: it is not
        overwritten while the user types. ``editingFinished`` closes that gap
        when the user leaves the field (or presses Return).
        """
        fields = self._fields
        if not fields:
            return
        with (
            QSignalBlocker(fields["size"]),
            QSignalBlocker(fields["spacing"]),
            QSignalBlocker(fields["width"]),
            QSignalBlocker(fields["height"]),
        ):
            # Never overwrite the field the user is typing in: a drag or a
            # sibling field updates the others, and the typed text already
            # names the value the model holds.
            for key, value in self._field_values().items():
                if not fields[key].hasFocus():
                    fields[key].setValue(value)

    def _field_changed(self, name: str, value: float) -> None:
        if name == "size":
            self._diameter = max(_MIN_SPAN, min(_MAX_PLANT_DIAMETER, value))
            self._size_edited = True
            self._sync_size_slider()
        elif name == "spacing":
            rows, columns = self._dimensions
            self._width = max(_MIN_SPAN, min(_MAX_SPAN, value * columns))
            self._height = max(_MIN_SPAN, min(_MAX_SPAN, value * rows))
        elif name == "width":
            self._width = max(_MIN_SPAN, min(_MAX_SPAN, value))
        elif name == "height":
            self._height = max(_MIN_SPAN, min(_MAX_SPAN, value))
        else:
            return
        self._sync_fields()
        self._place_controls()
        self._viewport.update()

    def _ensure_controls(self) -> QFrame:
        if self._controls is not None:
            self._sync_fields()
            return self._controls
        controls = QFrame(self._viewport)
        controls.setFrameShape(QFrame.Shape.StyledPanel)
        controls.setAutoFillBackground(True)
        layout = QVBoxLayout(controls)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        buttons = QHBoxLayout()
        buttons.setSpacing(2)
        layout.addLayout(buttons)
        actions = (
            ("cross", QCoreApplication.translate("PlantGridTool", "Cancel grid"), self._finish),
            ("grid", QCoreApplication.translate("PlantGridTool", "Edit rows and columns"), self._edit_dimensions),
            ("shrub", QCoreApplication.translate("PlantGridTool", "Change plant"), self._pick_plant),
            ("measure", QCoreApplication.translate(
                "PlantGridTool", "Plant size slider",
            ), self._toggle_plant_size),
            ("eye", QCoreApplication.translate("PlantGridTool", "Preview selected plant"),
             lambda _checked: self._viewport.update()),
            ("check", QCoreApplication.translate("PlantGridTool", "Place plants"), self._commit),
        )
        for name, tip, action in actions:
            button = QToolButton(controls)
            button.setObjectName(name)
            button.setAccessibleName(tip)
            button.setToolTip(tip)
            if name == "measure":
                button.setCheckable(True)
                self._size_button = button
            elif name == "eye":
                button.setCheckable(True)
                self._preview_button = button
            icon = get_icon(name)
            if icon is not None:
                button.setIcon(icon)
            else:
                button.setText(tip)
            button.clicked.connect(action)
            buttons.addWidget(button)
        values = QGridLayout()
        values.setContentsMargins(0, 0, 0, 0)
        values.setHorizontalSpacing(4)
        values.setVerticalSpacing(2)
        specs = (
            ("size", QCoreApplication.translate("PlantGridTool", "Plant size"),
             _MIN_SPAN, _MAX_PLANT_DIAMETER),
            ("spacing", QCoreApplication.translate("PlantGridTool", "Column spacing"),
             0.1, _MAX_SPAN),
            ("width", QCoreApplication.translate("PlantGridTool", "Width"),
             _MIN_SPAN, _MAX_SPAN),
            ("height", QCoreApplication.translate("PlantGridTool", "Height"),
             _MIN_SPAN, _MAX_SPAN),
        )
        for index, (key, label, minimum, maximum) in enumerate(specs):
            row, column = divmod(index, 2)
            values.addWidget(QLabel(label, controls), row, column * 2)
            field = self._length_field(key, label, minimum, maximum)
            if key == "spacing":
                field.setToolTip(QCoreApplication.translate(
                    "PlantGridTool",
                    "Typing a value sets both directions. The field shows the column spacing.",
                ))
            field.setMaximumWidth(110)
            self._fields[key] = field
            values.addWidget(field, row, column * 2 + 1)
        layout.addLayout(values)
        slider = QSlider(Qt.Orientation.Horizontal, controls)
        slider.setAccessibleName(QCoreApplication.translate("PlantGridTool", "Plant size slider"))
        slider.setMinimum(round(_MIN_SPAN))
        slider.valueChanged.connect(self._slide_plant_size)
        slider.hide()
        layout.addWidget(slider)
        self._size_slider = slider
        self._sync_size_slider()
        self._sync_fields()
        self._controls = controls
        self._overlay = ViewportOverlay(self.view, controls, self._controls_anchor)
        controls.adjustSize()
        return controls

    def _transform(self) -> QTransform:
        return QTransform().translate(self._center.x(), self._center.y()).rotate(self._angle)

    def _rect(self) -> QRectF:
        return QRectF(-self._width / 2, -self._height / 2, self._width, self._height)

    def _centers(self) -> list[QPointF]:
        rows, columns = self._dimensions
        return [
            QPointF(x, y)
            for x, y in cell_centers(rows, columns, self._width, self._height)
        ]

    def _set_extent(self, point: QPointF) -> None:
        if self._origin is None:
            return
        rect = QRectF(self._origin, self.view.snap_point(point)).normalized()
        self._center = rect.center()
        self._width = max(_MIN_SPAN, rect.width())
        self._height = max(_MIN_SPAN, rect.height())
        self._sync_fields()

    def _pixel_scale(self) -> float:
        transform = self.view.transform()
        return max(1e-6, QLineF(transform.map(QPointF()), transform.map(QPointF(1, 0))).length())

    def _handles(self) -> dict[str | tuple[int, int], QPointF]:
        transform = self._transform()
        rows, columns = self._dimensions
        offset = ROTATION_HANDLE_OFFSET / self._pixel_scale()
        return {
            key: transform.map(QPointF(x, y))
            for key, (x, y) in handle_positions(
                self._width,
                self._height,
                rows=rows,
                columns=columns,
                diameter=self._diameter,
                rotation_offset=offset,
            ).items()
        }

    def _first_plant(self) -> QPointF:
        rows, columns = self._dimensions
        x, y = first_cell_center(rows, columns, self._width, self._height)
        return QPointF(x, y)

    def _handle_at(self, point: QPointF) -> str | tuple[int, int] | None:
        nearest = None
        limit = (max(HANDLE_SIZE, ROTATION_HANDLE_SIZE) / 2 + 4) / self._pixel_scale()
        for name, center in reversed(tuple(self._handles().items())):
            distance = QLineF(center, point).length()
            if distance < limit:
                limit, nearest = distance, name
        if nearest is None and self._rect().contains(self._transform().inverted()[0].map(point)):
            return "move"
        return nearest

    def _update_cursor(self, handle: str | tuple[int, int] | None) -> None:
        cursor = Qt.CursorShape.ArrowCursor
        if handle == "move":
            cursor = Qt.CursorShape.ClosedHandCursor if self._drag else Qt.CursorShape.OpenHandCursor
        elif handle == "rotate":
            cursor = Qt.CursorShape.CrossCursor
        elif handle == "diameter":
            cursor = Qt.CursorShape.SizeAllCursor
        elif isinstance(handle, tuple):
            direction = self._transform().map(QPointF(*handle)) - self._center
            screen = self.view.transform().map(direction) - self.view.transform().map(QPointF())
            sector = round(degrees(atan2(screen.y(), screen.x())) / 45) % 4
            cursor = (Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeFDiagCursor,
                      Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeBDiagCursor)[sector]
        self.view.setCursor(cursor)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._origin is None:
            self._dimensions = get_settings().plant_grid_dimensions
            if self._edit_dimensions() and self._pick_plant():
                self._origin = self.view.snap_point(scene_pos)
                self._set_extent(self._origin)
            else:
                self._finish()
        elif not self._editing:
            self._before = (QPointF(self._center), self._width, self._height, self._angle)
            self._press_completed_extent = True
            self._set_extent(scene_pos)
            self._editing = True
            self._ensure_controls().show()
            self._place_controls()
        else:
            self._drag = self._handle_at(scene_pos)
            self._drag_start = scene_pos
            self._before = (QPointF(self._center), self._width, self._height, self._angle)
            self._diameter_before = self._diameter
            self._size_edited_before = self._size_edited
            self._update_cursor(self._drag)
        self._viewport.update()
        return True

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if self._origin is None:
            return False
        if not self._editing:
            self._set_extent(scene_pos)
        elif self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._transform_drag(scene_pos, event.modifiers())
            self._place_controls()
        else:
            # A hover changes nothing but the highlighted handle: repaint the
            # plan (and up to 400 preview sprites) only when that changes. The
            # cursor is set on every move: the view resets it from outside the
            # tool (a middle-button pan release, leaving a guide).
            highlighted = self._drag if self._drag is not None else self._hover
            self._drag = None
            self._hover = self._handle_at(scene_pos)
            self._update_cursor(self._hover)
            if self._hover == highlighted:
                return True
        self._viewport.update()
        return True

    def _transform_drag(self, point: QPointF, modifiers: Qt.KeyboardModifier) -> None:
        center, width, height, angle = self._before
        snapping = self.view.snap_enabled
        if self._drag == "move":
            target = center + point - self._drag_start
            self._center = self.view.snap_point(target) if snapping else target
        elif self._drag == "rotate":
            start, end = self._drag_start - center, point - center
            if not end.isNull():
                self._angle = angle + degrees(atan2(end.y(), end.x()) - atan2(start.y(), start.x()))
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self._angle = round(self._angle / ROTATION_SNAP_ANGLE) * ROTATION_SNAP_ANGLE
                elif snapping:
                    nearest = round(self._angle / ROTATION_SNAP_ANGLE) * ROTATION_SNAP_ANGLE
                    if abs(self._angle - nearest) <= _ROTATION_SNAP_WINDOW:
                        self._angle = nearest
        elif self._drag == "diameter":
            plant = self._transform().map(self._first_plant())
            delta = QLineF(plant, point).length() - QLineF(plant, self._drag_start).length()
            diameter = max(_MIN_SPAN, min(_MAX_PLANT_DIAMETER,
                                          self._diameter_before + 2 * delta))
            if snapping:
                diameter = round(diameter)
            if abs(diameter - self._diameter_before) > 1e-6:
                self._size_edited = True
            self._diameter = diameter
            self._sync_size_slider()
        elif isinstance(self._drag, tuple):
            sx, sy = self._drag
            transform = QTransform().translate(center.x(), center.y()).rotate(angle)
            inverse = transform.inverted()[0]
            # A handle is grabbed within a few centimetres of its centre. The
            # EDGE follows the handle (cursor delta applied to the handle), and
            # snapping acts on that handle position: snapping the raw cursor
            # instead baked the grab offset into the edge (#1021 review).
            handle = QPointF(sx * width / 2, sy * height / 2)
            desired = transform.map(handle) + (point - self._drag_start)
            target = self.view.snap_point(desired) if snapping else desired
            local = inverse.map(target)
            start_x, end_x = resize_edges(width, sx, local.x())
            start_y, end_y = resize_edges(height, sy, local.y())
            if snapping:
                rows, columns = self._dimensions
                if sx:
                    span = snap_cell_span(end_x - start_x, columns)
                    if sx < 0:
                        start_x = end_x - span
                    else:
                        end_x = start_x + span
                if sy:
                    span = snap_cell_span(end_y - start_y, rows)
                    if sy < 0:
                        start_y = end_y - span
                    else:
                        end_y = start_y + span
            self._width, self._height = end_x - start_x, end_y - start_y
            self._center = transform.map(QPointF((start_x + end_x) / 2, (start_y + end_y) / 2))
        self._sync_fields()

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return False
        self._press_completed_extent = False
        if self._drag is not None:
            self._transform_drag(scene_pos, event.modifiers())
            self._drag = None
            self._hover = self._handle_at(scene_pos)
            self._update_cursor(self._hover)
            self._place_controls()
            self._viewport.update()
        return True

    # Esc is not handled here: the view's single Esc rule (#829) ends the
    # tool, and ``deactivate`` -> ``cancel`` discards the draft.

    def paint_foreground(self, painter: QPainter) -> None:
        if self._origin is None:
            return
        transform = self._transform()
        painter.save()
        try:
            painter.setWorldTransform(transform, True)
            pen = QPen(QColor(_ACCENT))
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect())
            painter.setBrush(QColor(227, 129, 39, 35))
            radius = self._diameter / 2
            species = self._species
            preview = self._preview_button is not None and self._preview_button.isChecked()
            object_type = species_object_type(species) if preview and species is not None else None
            species_name = (species.get("common_name") or species.get("scientific_name") or "") if species else ""
            for point in self._centers():
                if object_type is not None:
                    # Drawn as the placed CircleItem draws it: the sprite is
                    # wider than the footprint by the same fill factor.
                    size = self._diameter * PLANT_FILL_SCALE
                    rect = QRectF(point.x() - size / 2, point.y() - size / 2, size, size)
                    if paint_plant(painter, rect, object_type, species=species_name):
                        continue
                painter.drawEllipse(point, radius, radius)
        finally:
            painter.restore()
        if self._editing:
            self._paint_handles(painter)

    def _paint_handles(self, painter: QPainter) -> None:
        painter.save()
        transform = painter.worldTransform()
        painter.resetTransform()
        handles = {handle: transform.map(point) for handle, point in self._handles().items()}
        painter.setPen(QPen(ROTATION_HANDLE_COLOR, 1.0))
        painter.drawLine(handles[(0, -1)], handles["rotate"])
        painter.setPen(QPen(QColor("white"), 1.0))
        for handle, point in handles.items():
            active = handle == (self._drag if self._drag is not None else self._hover)
            size, color = HANDLE_SIZE, HANDLE_HOVER_COLOR if active else HANDLE_COLOR
            if handle == "rotate":
                size = ROTATION_HANDLE_SIZE
                color = ROTATION_HANDLE_HOVER_COLOR if active else ROTATION_HANDLE_COLOR
            elif handle == "diameter":
                size, color = ROTATION_HANDLE_SIZE, QColor("#ffad60" if active else _ACCENT)
            painter.setBrush(color)
            bounds = QRectF(point.x() - size / 2, point.y() - size / 2, size, size)
            if handle in ("rotate", "move", "diameter"):
                painter.drawEllipse(bounds)
                if handle == "move":
                    painter.drawLine(point - QPointF(3, 0), point + QPointF(3, 0))
                    painter.drawLine(point - QPointF(0, 3), point + QPointF(0, 3))
            else:
                painter.drawRect(bounds)
        painter.restore()

    def _controls_anchor(self) -> QRectF | None:
        """The draft's screen rect, for the overlay's placement (ADR-082)."""
        if self._controls is None or not self._editing:
            return None
        points = [QPointF(self.view.mapFromScene(point)) for point in self._handles().values()]
        left = min(point.x() for point in points)
        top = min(point.y() for point in points)
        right = max(point.x() for point in points)
        bottom = max(point.y() for point in points)
        return QRectF(left, top, max(1.0, right - left), max(1.0, bottom - top))

    def _place_controls(self, *_args: object) -> None:
        """Ask the overlay to place the strip from the draft's anchor."""
        if self._overlay is not None:
            self._overlay.place()

    def _commit(self) -> None:
        if not self._editing or self._species is None:
            return
        transform = self._transform()
        positions = [transform.map(point) for point in self._centers()]
        if not all(self._scene.canvas_rect.contains(point) for point in positions):
            self.view.set_status_message(QCoreApplication.translate(
                "PlantGridTool", "All plant centres must be inside the plan",
            ))
            return

        group = False
        if len(positions) > 1:
            generation = self._scene.document_generation
            choice = QMessageBox.question(
                self.view,
                QCoreApplication.translate("PlantGridTool", "Plant Grid"),
                QCoreApplication.translate("PlantGridTool", "Add all plants from this grid to one group?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if (
                choice not in (QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
                or not self._is_current(generation)
            ):
                return
            group = choice == QMessageBox.StandardButton.Yes

        items: list[QGraphicsItem] = [
            build_species_plant(
                self._scene, position, self._species,
                diameter_cm=self._diameter if self._size_edited else None,
                auto_assign=self.view.auto_assign_permaculture_layers,
            )
            for position in positions
        ]
        create = CreateItemsCommand(
            self._scene, items, QCoreApplication.translate("PlantGridTool", "plants"),
        )
        command = CompoundCommand([create, GroupCommand(self._scene, items)]) if group else create
        self.view.command_manager.execute(command)
        self._finish()
        # As after a single drop: the new plants (or their group) are selected.
        self._scene.clearSelection()
        parent = items[0].parentItem()
        for item in [parent] if isinstance(parent, GroupItem) else items:
            item.setSelected(True)

    def _finish(self) -> None:
        if self.view.active_tool is self:
            self.view.set_active_tool(ToolType.SELECT)

    def cancel_pointer_press(self) -> None:
        if not self._editing:
            self.cancel()
            return
        if self._press_completed_extent:
            self._center, self._width, self._height, self._angle = self._before
            self._editing = self._press_completed_extent = False
            if self._controls is not None:
                self._controls.hide()
        elif self._drag is not None:
            self._center, self._width, self._height, self._angle = self._before
            self._diameter = self._diameter_before
            self._size_edited = self._size_edited_before
            self._sync_size_slider()
            self._sync_fields()
        self._drag = self._hover = None
        if self._editing:
            self._update_cursor(None)
        else:
            # Back in the rubber-band phase, which shows the tool's own cursor.
            self.view.setCursor(self.cursor)
        self._place_controls()
        self._viewport.update()

    def cancel(self) -> None:
        self._origin = None
        self._species = None
        self._angle = 0.0
        self._editing = self._press_completed_extent = False
        self._drag = None
        self._hover = None
        if self._size_button is not None:
            self._size_button.setChecked(False)
        if self._size_slider is not None:
            self._size_slider.hide()
        if self._preview_button is not None:
            self._preview_button.setChecked(False)
        if self._controls is not None:
            self._controls.hide()
        self._viewport.update()
