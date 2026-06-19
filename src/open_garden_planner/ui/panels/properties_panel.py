"""Properties panel for live editing of selected objects."""

from collections.abc import Callable

from PyQt6.QtCore import QCoreApplication, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFocusEvent, QIcon, QPen
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.commands import ChangePropertyCommand, CommandManager
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.furniture_renderer import get_furniture_svg_path
from open_garden_planner.core.object_types import (
    ObjectType,
    PathFenceStyle,
    StrokeStyle,
    get_style,
    get_translated_display_name,
    get_translated_path_fence_style_name,
    is_bed_type,
)
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
    TextItem,
)

# Clean, translatable description fragments for TextItem font properties.
# The raw attribute names (font_family, font_size) make ugly undo labels
# ("Change text font_family"); these map them to nouns registered under the
# "Commands" i18n context (scripts/fill_translations.py).
_TEXT_PROPERTY_LABELS = {
    "font_family": "font",
    "font_size": "font size",
    "bold": "bold",
    "italic": "italic",
}

# Free-text fields (Name, Text Content) live-update the item on every keystroke
# but only commit ONE undo command per typing burst. The command is committed
# after the user pauses for this long, or immediately on focus-out — whichever
# comes first. The debounce (rather than focus-out only) is what lets Ctrl+Z
# work while the field still has focus: without a committed command the Undo
# action stays disabled and Ctrl+Z is a no-op (issue #210 manual-test finding).
_TEXT_COMMIT_DEBOUNCE_MS = 600


class FocusOutTextEdit(QTextEdit):
    """QTextEdit that emits ``editing_finished`` when it loses focus.

    QTextEdit (unlike QLineEdit) has no ``editingFinished`` signal. Mirrors the
    focus-out pattern used by the in-canvas text editors (text_item.py,
    callout_item.py) so a multi-line edit can be committed as a single undo
    step on click-away instead of one command per keystroke.
    """

    editing_finished = pyqtSignal()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802 (Qt)
        """Emit ``editing_finished`` after the default focus-out handling."""
        super().focusOutEvent(event)
        self.editing_finished.emit()


class ColorButton(QPushButton):
    """A button that displays a color and opens a color picker when clicked."""

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        """Initialize the color button.

        Args:
            color: Initial color
            parent: Parent widget
        """
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(30)
        self._update_style()
        self.clicked.connect(self._pick_color)

    @property
    def color(self) -> QColor:
        """Get the current color."""
        return self._color

    def set_color(self, color: QColor) -> None:
        """Set the button color.

        Args:
            color: New color
        """
        self._color = color
        self._update_style()

    def _update_style(self) -> None:
        """Update the button style to show the current color.

        Uses Qt's stylesheet rgba() with **integer 0-255 alpha** — Qt 6's CSS
        parser rejects the long-float CSS-standard form (e.g. ``0.50196…``)
        and logs ``Could not parse stylesheet of object QPushButton`` for each
        repaint cycle. Integer alpha avoids the warning entirely.
        """
        self.setStyleSheet(
            f"background-color: rgba({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha()}); "
            f"border: 1px solid #888;"
        )

    def _pick_color(self) -> None:
        """Open color picker dialog."""
        dialog = QColorDialog()
        dialog.setCurrentColor(self._color)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setWindowTitle(self.tr("Choose Color"))

        if dialog.exec():
            color = dialog.selectedColor()
            if color.isValid():
                self.set_color(color)


class PropertiesPanel(QWidget):
    """Panel for live editing of selected object properties.

    Shows properties of currently selected objects and allows immediate editing.
    Changes are applied in real-time to the canvas with undo support.
    """

    # Signal emitted when an object's type changes (for updating other panels)
    object_type_changed = pyqtSignal()

    def __init__(
        self,
        command_manager: CommandManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the properties panel.

        Args:
            command_manager: Optional command manager for undo support
            parent: Parent widget
        """
        super().__init__(parent)
        self._command_manager = command_manager
        self._current_items: list[QGraphicsItem] = []
        self._updating = False  # Prevent feedback loops
        # Identity of the currently built form. set_selected_items rebuilds only
        # when this changes; an unchanged selection takes the in-place value
        # refresh path instead of tearing down and recreating every widget (#206).
        self._current_identity: tuple | None = None
        # Closures that re-read the model and push fresh values into the live
        # form widgets (one per editable field, registered as the field is
        # built). Run by _refresh_field_values; cleared by _clear_form (#206).
        self._field_refreshers: list[Callable[[], None]] = []
        # Commit callbacks for the free-text fields with a pending debounce
        # (Name, Text Content). Flushed before any form rebuild so a pending
        # edit is not destroyed with its widget and lost from undo (#210).
        self._pending_text_commits: list[Callable[[], None]] = []
        self._setup_ui()

    def set_command_manager(self, command_manager: CommandManager) -> None:
        """Set the command manager for undo support.

        Args:
            command_manager: The command manager to use
        """
        self._command_manager = command_manager

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Scroll area for properties
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # Content widget
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)

        # Form layout for properties
        self._form_layout = QFormLayout()
        self._form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._content_layout.addLayout(self._form_layout)
        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

        # Initially show "no selection" message
        self._show_no_selection()

    def _clear_form(self) -> None:
        """Clear all widgets from the form.

        Also drops the field refreshers: they reference the widgets being
        destroyed here, and the rebuild re-registers fresh ones (#206).
        """
        self._field_refreshers = []
        while self._form_layout.rowCount() > 0:
            self._form_layout.removeRow(0)

    def _show_no_selection(self) -> None:
        """Show message when nothing is selected."""
        self._clear_form()
        label = QLabel(self.tr("No objects selected"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("secondary", True)
        label.setStyleSheet("padding: 20px;")
        self._form_layout.addRow(label)

    def _show_multi_selection(self, count: int) -> None:
        """Show message for multiple selection.

        Args:
            count: Number of selected objects
        """
        self._clear_form()
        label = QLabel(self.tr("{count} objects selected").format(count=count))
        label.setStyleSheet("font-weight: bold;")
        self._form_layout.addRow(label)

        # TODO: Show common properties for batch editing
        info = QLabel(self.tr("Multi-selection editing\nnot yet implemented"))
        info.setProperty("secondary", True)
        info.setStyleSheet("padding: 10px;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._form_layout.addRow(info)

    def set_selected_items(self, items: list[QGraphicsItem]) -> None:
        """Set the selected items to display properties for.

        Args:
            items: List of selected graphics items
        """
        # Since #206 a pure property edit on the *same* selection no longer
        # tears down the form (it takes the in-place refresh path below, which
        # skips the focused widget), so this focus guard is now a defensive
        # backstop rather than the primary mechanism: it still protects the rare
        # case where the selection genuinely *changed* to a different item while
        # a panel field holds focus, where a full rebuild would delete the
        # focused widget mid-input and drop focus + caret (issue #200).
        # QAbstractSpinBox covers QSpinBox/QDoubleSpinBox and each widget's
        # internal QLineEdit. Trade-off: such a rebuild is skipped, so the panel
        # briefly shows the previous item until the next trigger — keeping focus
        # is worth it; do NOT remove the guard to "fix" it.
        fw = QApplication.focusWidget()
        if (
            fw is not None
            and isinstance(fw, (QAbstractSpinBox, QLineEdit, QTextEdit))
            and self.isAncestorOf(fw)
        ):
            return

        # Commit any pending debounced free-text edit BEFORE rebuilding — the
        # rebuild deletes the field and its debounce timer synchronously, so an
        # un-flushed edit would be applied to the model but never recorded as a
        # command (lost from undo history). The fields are still alive here.
        self._flush_pending_text_commits()

        # Incremental update (#206): when the selection set and form structure
        # are unchanged (a pure scalar property edit, a canvas drag/resize, or
        # undo/redo on the same item), keep the widgets alive and push fresh
        # model values into them instead of rebuilding. Rebuild only on a
        # genuine selection/structure change. This removes the per-signal
        # teardown that was the root cause of the #200 focus loss.
        # The refresh path applies only when refreshers exist (a single editable
        # item). Multi-selection and GroupItem register none, so they harmlessly
        # fall through to a (cheap, no editable fields) rebuild on every signal.
        new_identity = self._compute_identity(items)
        if new_identity == self._current_identity and self._field_refreshers:
            self._current_items = items
            self._refresh_field_values()
            return

        self._current_identity = new_identity
        self._current_items = items

        if not items:
            self._show_no_selection()
        elif len(items) > 1:
            self._show_multi_selection(len(items))
        else:
            self._show_single_item(items[0])

    def _compute_identity(self, items: list[QGraphicsItem]) -> tuple:
        """A stable key for the structure of the form needed by ``items``.

        Rebuild only when this key changes; an unchanged key takes the in-place
        value-refresh path. It folds in everything that alters the *set* of
        fields or the read-only summary rows — the item identity, its class and
        ``object_type`` (which fields exist), the bed's contained-plant ids
        (Contained Plants summary) and a plant's parent bed (Parent Bed summary)
        — so any of those forces a rebuild while pure scalar edits do not (#206).

        It also folds in the *rendered text* of the read-only summary rows
        (`_relationship_summary_key`): those rows show a **related** item's name,
        which the id set alone does not capture, so a rename/undo of the related
        item while this item stays selected would otherwise leave them stale on
        the refresh path (no refresher covers a variable-row summary list).

        Keying on ``id(item)`` is correct only because every command mutates the
        selected item *in place* and reuses the same object across undo/redo (see
        CreateItemCommand/DeleteItemsCommand). A command that ever *replaces* the
        object for the same selection must add a discriminator here or it will
        wrongly take the stale refresh path.
        """
        if len(items) != 1:
            return tuple(id(it) for it in items)
        item = items[0]
        parts: list[object] = [
            id(item),
            type(item).__name__,
            getattr(item, "object_type", None),
        ]
        child_ids = getattr(item, "child_item_ids", None)
        if child_ids is not None:
            parts.append(tuple(child_ids))
        parts.append(getattr(item, "parent_bed_id", None))
        parts.append(self._relationship_summary_key(item))
        return tuple(parts)

    def _relationship_summary_key(self, item: QGraphicsItem) -> object:
        """Text signature of the read-only Parent Bed / Contained Plants rows.

        Follows the same name derivation as `_add_parent_bed_section` /
        `_add_bed_children_section` (a related item's ``name``, falling back to
        its translated type name) for the cases those rows actually render — a
        related item gated by `is_bed_type`/`is_plant_type` always has an
        ``object_type``, so the typeless "Plant"/"Bed" fallback in the renderers
        is unreachable here. Folded into the identity so a rename of the related
        item forces a rebuild and the summary can't go stale (#206).
        """
        from open_garden_planner.core.object_types import is_bed_type
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin):
            return None
        scene = item.scene()
        if scene is None:
            return None

        def _label(it: GardenItemMixin) -> str:
            if it.name:
                return it.name
            return get_translated_display_name(it.object_type) if it.object_type else ""

        by_id = {
            si.item_id: si for si in scene.items() if isinstance(si, GardenItemMixin)
        }
        if is_bed_type(item.object_type):
            return tuple(
                sorted(
                    _label(by_id[cid]) for cid in item.child_item_ids if cid in by_id
                )
            )
        if is_plant_type(item.object_type) and item.parent_bed_id is not None:
            parent = by_id.get(item.parent_bed_id)
            return _label(parent) if parent is not None else None
        return None

    def _is_focused(self, widget: QWidget) -> bool:
        """True when ``widget`` (or a child, e.g. a spin box's editor) has focus."""
        fw = QApplication.focusWidget()
        return fw is not None and (fw is widget or widget.isAncestorOf(fw))

    def _refresh_widget(self, widget: QWidget, setter: Callable[[], object]) -> None:
        """Push a fresh model value into ``widget`` via ``setter`` in place.

        Skips a focused widget so a refresh never stomps an active edit, and
        blocks the widget's signals while writing so the value push cannot
        register a command (#206).
        """
        if self._is_focused(widget):
            return
        widget.blockSignals(True)
        try:
            setter()
        finally:
            widget.blockSignals(False)

    def _register_refresh(self, widget: QWidget, setter: Callable[[], object]) -> None:
        """Register an in-place value refresher for ``widget`` (see #206)."""
        self._field_refreshers.append(lambda: self._refresh_widget(widget, setter))

    def _refresh_field_values(self) -> None:
        """Re-read the model and push fresh values into the live form widgets.

        Runs every refresher registered by the field builders, with ``_updating``
        set so any handler that does slip through (signals are also blocked
        per-widget) is a no-op. Keeps the displayed values correct after a canvas
        drag/resize or undo/redo without tearing down the form (#206).
        """
        if not self._field_refreshers:
            return
        self._updating = True
        try:
            for refresh in self._field_refreshers:
                refresh()
        finally:
            self._updating = False

    def _flush_pending_text_commits(self) -> None:
        """Commit any pending debounced free-text edits, then clear the queue.

        Each commit is idempotent (no-op when the value is unchanged) and stops
        its own debounce timer, so this is safe to call on every rebuild. New
        fields re-register their callbacks as they are built. See #210.
        """
        pending = self._pending_text_commits
        self._pending_text_commits = []
        for commit in pending:
            commit()

    def _show_single_item(self, item: QGraphicsItem) -> None:
        """Show properties for a single selected item.

        Args:
            item: The selected graphics item
        """
        self._clear_form()
        self._updating = True

        # TextItem — show text-specific properties
        if isinstance(item, TextItem):
            self._add_text_properties(item)
            # Layer
            if hasattr(item, 'layer_id'):
                layer_combo = QComboBox()
                self._populate_layer_combo(layer_combo, item)
                layer_combo.currentIndexChanged.connect(
                    lambda: self._on_property_changed(item, 'layer_id', layer_combo.currentData())
                )
                self._form_layout.addRow(self.tr("Layer:"), layer_combo)
                self._register_refresh(
                    layer_combo,
                    lambda c=layer_combo, it=item: self._refresh_layer_combo(c, it),
                )
            self._updating = False
            return

        # GroupItem — show a compact summary
        from open_garden_planner.ui.canvas.items.group_item import GroupItem
        if isinstance(item, GroupItem):
            count = len(item.childItems())
            info = QLabel(self.tr("Group ({n} items)").format(n=count))
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._form_layout.addRow(info)
            hint = QLabel(self.tr("Ctrl+Shift+G to ungroup"))
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet("color: gray; font-size: 11px;")
            self._form_layout.addRow(hint)
            self._updating = False
            return

        # Object Type (if applicable)
        if hasattr(item, 'object_type'):
            type_combo = QComboBox()
            self._populate_object_type_combo(type_combo, item)
            type_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'object_type', type_combo.currentData())
            )
            self._form_layout.addRow(self.tr("Type:"), type_combo)
            self._register_refresh(
                type_combo,
                lambda c=type_combo, it=item: c.setCurrentIndex(max(0, c.findData(it.object_type))),
            )

        # Name/Label
        if hasattr(item, 'name'):
            name_edit = QLineEdit(item.name)
            # Live-update the canvas label on every keystroke, but commit a
            # single undo command after a typing pause (debounce) or on
            # focus-out — whichever first (issue #210). The start value is
            # captured here because the field is rebuilt per selection.
            name_edit._ogp_name_start = item.name  # type: ignore[attr-defined]
            self._attach_commit_timer(
                name_edit, lambda: self._on_name_commit(item, name_edit)
            )
            name_edit.textChanged.connect(
                lambda text, it=item, edit=name_edit: self._on_name_text_changed(it, text, edit)
            )
            name_edit.editingFinished.connect(
                lambda it=item, edit=name_edit: self._on_name_commit(it, edit)
            )
            self._form_layout.addRow(self.tr("Name:"), name_edit)
            # Refresh keeps the start marker in sync so a later focus-edit diffs
            # against the displayed value, not a stale one (#206/#210).
            self._register_refresh(
                name_edit,
                lambda e=name_edit, it=item: (
                    e.setText(it.name),
                    setattr(e, "_ogp_name_start", it.name),
                ),
            )

        # Show Label checkbox
        if hasattr(item, 'label_visible'):
            label_check = QCheckBox(self.tr("Show label on canvas"))
            label_check.setChecked(item.label_visible)
            label_check.toggled.connect(
                lambda checked: self._on_property_changed(item, 'label_visible', checked)
            )
            self._form_layout.addRow(self.tr("Label:"), label_check)
            self._register_refresh(
                label_check, lambda c=label_check, it=item: c.setChecked(it.label_visible)
            )

        # Layer
        if hasattr(item, 'layer_id'):
            layer_combo = QComboBox()
            self._populate_layer_combo(layer_combo, item)
            layer_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'layer_id', layer_combo.currentData())
            )
            self._form_layout.addRow(self.tr("Layer:"), layer_combo)
            self._register_refresh(
                layer_combo,
                lambda c=layer_combo, it=item: self._refresh_layer_combo(c, it),
            )

        # Geometry section
        self._add_geometry_properties(item)

        # Grid overlay section (for bed types only)
        self._add_grid_properties(item)

        # Soil depth section (for bed types only)
        self._add_soil_depth_properties(item)

        # Spacing radius section (for plant types only)
        self._add_spacing_properties(item)

        # Styling section
        self._add_styling_properties(item)

        # Plant-bed relationship sections
        self._add_bed_children_section(item)
        self._add_parent_bed_section(item)

        self._updating = False

    def _populate_object_type_combo(self, combo: QComboBox, item: QGraphicsItem) -> None:
        """Populate object type combobox with all valid types for the item shape.

        Args:
            combo: Combobox to populate
            item: Item to get valid types for
        """
        from open_garden_planner.core.object_types import get_valid_types_for_shape

        if isinstance(item, RectangleItem):
            valid_types = get_valid_types_for_shape("rectangle")
        elif isinstance(item, EllipseItem):
            valid_types = get_valid_types_for_shape("ellipse")
        elif isinstance(item, CircleItem):
            valid_types = get_valid_types_for_shape("circle")
        elif isinstance(item, PolygonItem):
            valid_types = get_valid_types_for_shape("polygon")
        elif isinstance(item, PolylineItem):
            valid_types = get_valid_types_for_shape("polyline")
        else:
            valid_types = list(ObjectType)

        # Populate combo with translated names and SVG icons
        combo.setIconSize(combo.iconSize())  # default icon size
        current_idx = 0
        for idx, obj_type in enumerate(valid_types):
            icon = self._get_object_type_icon(obj_type)
            if icon is not None:
                combo.addItem(icon, get_translated_display_name(obj_type), obj_type)
            else:
                combo.addItem(get_translated_display_name(obj_type), obj_type)
            if hasattr(item, 'object_type') and item.object_type == obj_type:
                current_idx = idx

        combo.setCurrentIndex(current_idx)

    @staticmethod
    def _get_object_type_icon(obj_type: ObjectType) -> QIcon | None:
        """Return a small QIcon from the SVG file for the given object type, or None."""
        from pathlib import Path

        # 1. Furniture / infrastructure SVGs (objects/ directory)
        svg_path = get_furniture_svg_path(obj_type)
        if svg_path is not None and svg_path.exists():
            return QIcon(str(svg_path))

        res = Path(__file__).parent.parent.parent / "resources"

        # 2. Tool icons (icons/tools/ directory)
        _TOOL_ICON_FILES: dict[ObjectType, str] = {
            ObjectType.GENERIC_RECTANGLE: "rectangle",
            ObjectType.GENERIC_POLYGON: "polygon",
            ObjectType.GENERIC_CIRCLE: "circle",
            ObjectType.HOUSE: "house",
            ObjectType.GARAGE_SHED: "shed",
            ObjectType.GREENHOUSE: "greenhouse",
            ObjectType.TERRACE_PATIO: "terrace",
            ObjectType.DRIVEWAY: "driveway",
            ObjectType.POND_POOL: "pond",
            ObjectType.GARDEN_BED: "garden_bed",
            ObjectType.LAWN: "lawn",
            ObjectType.FENCE: "fence",
            ObjectType.WALL: "wall",
            ObjectType.PATH: "path",
            ObjectType.TREE: "tree",
            ObjectType.SHRUB: "shrub",
            ObjectType.PERENNIAL: "flower",
        }
        tool_name = _TOOL_ICON_FILES.get(obj_type)
        if tool_name is not None:
            tool_path = res / "icons" / "tools" / f"{tool_name}.svg"
            if tool_path.exists():
                return QIcon(str(tool_path))

        return None

    def _populate_layer_combo(self, combo: QComboBox, item: QGraphicsItem) -> None:
        """Populate layer combobox.

        Args:
            combo: Combobox to populate
            item: Item to get current layer for
        """
        scene = item.scene()
        if scene and hasattr(scene, 'layers'):
            current_idx = 0
            for idx, layer in enumerate(scene.layers):
                combo.addItem(layer.name, layer.id)
                if hasattr(item, 'layer_id') and item.layer_id == layer.id:
                    current_idx = idx
            combo.setCurrentIndex(current_idx)

    def _refresh_layer_combo(self, combo: QComboBox, item: QGraphicsItem) -> None:
        """Re-populate the Layer combo from the (mutable) scene layer list.

        Unlike the other combos, this one's *items* — not just its selected
        index — come from external mutable state (`scene.layers`). A plain
        re-index refresher would leave a renamed layer showing its old name, or
        omit a newly-added layer, on the in-place refresh path. So the refresher
        must clear + repopulate the list (#206/#222). The refresher wrapper runs
        this under `blockSignals`, so the clear()+addItem()+setCurrentIndex fire
        no `currentIndexChanged` (no spurious layer-change command).
        """
        combo.clear()
        self._populate_layer_combo(combo, item)

    def _add_bed_children_section(self, item: QGraphicsItem) -> None:
        """Show contained plants list when a bed is selected."""
        from open_garden_planner.core.object_types import is_bed_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin):
            return
        if not is_bed_type(item.object_type):
            return

        children = item.child_item_ids
        scene = item.scene()

        # Header
        header = QLabel(self.tr("Contained Plants"))
        header.setStyleSheet("font-weight: bold; margin-top: 6px;")
        self._form_layout.addRow(header)

        if not children or scene is None:
            self._form_layout.addRow(QLabel(self.tr("No plants in this bed")))
            return

        # Group by name/species and count
        plant_counts: dict[str, int] = {}
        for child_id in children:
            child = None
            for si in scene.items():
                if isinstance(si, GardenItemMixin) and si.item_id == child_id:
                    child = si
                    break
            if child is not None:
                label = child.name or get_translated_display_name(child.object_type) if child.object_type else "Plant"
                plant_counts[label] = plant_counts.get(label, 0) + 1

        total = sum(plant_counts.values())
        total_label = QLabel(self.tr("Total: {count} plant(s)").format(count=total))
        self._form_layout.addRow(total_label)

        for name, count in sorted(plant_counts.items()):
            self._form_layout.addRow(QLabel(f"  {name}: {count}"))

    def _add_parent_bed_section(self, item: QGraphicsItem) -> None:
        """Show parent bed info when a plant is selected."""
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(item, GardenItemMixin):
            return
        if not is_plant_type(item.object_type):
            return
        if item.parent_bed_id is None:
            return

        scene = item.scene()
        if scene is None:
            return

        # Find parent bed
        parent_bed = None
        for si in scene.items():
            if isinstance(si, GardenItemMixin) and si.item_id == item.parent_bed_id:
                parent_bed = si
                break

        if parent_bed is None:
            return

        bed_name = parent_bed.name or (
            get_translated_display_name(parent_bed.object_type) if parent_bed.object_type else "Bed"
        )

        row = QHBoxLayout()
        row.addWidget(QLabel(bed_name))

        unlink_btn = QPushButton(self.tr("Unlink"))
        unlink_btn.setFixedWidth(60)

        def _do_unlink() -> None:
            from open_garden_planner.core.commands import SetParentBedCommand
            cmd = SetParentBedCommand(
                scene, item, item.parent_bed_id, None,
            )
            self._command_manager.execute(cmd)
            # Refresh panel
            self.set_selected_items([item])

        unlink_btn.clicked.connect(_do_unlink)
        row.addWidget(unlink_btn)

        header = QLabel(self.tr("Parent Bed"))
        header.setStyleSheet("font-weight: bold; margin-top: 6px;")
        self._form_layout.addRow(header)
        self._form_layout.addRow(row)

    @staticmethod
    def _position_xy(item: QGraphicsItem) -> tuple[float, float]:
        """Scene-space top-left of the item's bounding box (CAD bottom-left).

        In scene coords (Y-down) the bounding-box topLeft is the visual
        bottom-left after the Y-flip, so its scene X/Y are the CAD origin shown
        in the Position field. Shared by the field builder and its refresher so
        a canvas drag/undo updates the spin boxes without a rebuild (#206).
        """
        top_left_scene = item.mapToScene(item.boundingRect().topLeft())
        return top_left_scene.x(), top_left_scene.y()

    def _add_geometry_properties(self, item: QGraphicsItem) -> None:
        """Add geometry property fields.

        Args:
            item: Item to show geometry for
        """
        # Position (editable X, Y) - use top-left corner of bounding box in scene coords
        # This corresponds to visual bottom-left after Y-flip (CAD origin)
        bottom_left_x, bottom_left_y = self._position_xy(item)

        # Create horizontal layout for X and Y spin boxes
        pos_layout = QHBoxLayout()
        pos_layout.setSpacing(4)
        pos_layout.setContentsMargins(0, 0, 0, 0)

        # X coordinate
        x_label = QLabel("X:")
        x_spin = QDoubleSpinBox()
        x_spin.setRange(-100000.0, 100000.0)
        x_spin.setDecimals(1)
        x_spin.setSingleStep(10.0)
        x_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        x_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        x_spin.setValue(bottom_left_x)
        pos_layout.addWidget(x_label)
        pos_layout.addWidget(x_spin, 1)

        # Y coordinate
        y_label = QLabel("Y:")
        y_spin = QDoubleSpinBox()
        y_spin.setRange(-100000.0, 100000.0)
        y_spin.setDecimals(1)
        y_spin.setSingleStep(10.0)
        y_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        y_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        y_spin.setValue(bottom_left_y)
        pos_layout.addWidget(y_label)
        pos_layout.addWidget(y_spin, 1)

        # Connect after both spin boxes are created
        x_spin.valueChanged.connect(
            lambda _: self._on_position_changed(item, x_spin, y_spin)
        )
        y_spin.valueChanged.connect(
            lambda _: self._on_position_changed(item, x_spin, y_spin)
        )

        # Create a widget to hold the layout; Expanding so it fills the field column
        pos_widget = QWidget()
        pos_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        pos_widget.setLayout(pos_layout)
        self._form_layout.addRow(self.tr("Position:"), pos_widget)

        # Keep Position in sync after a canvas drag / undo (no rebuild) (#206).
        self._register_refresh(
            x_spin, lambda s=x_spin, it=item: s.setValue(self._position_xy(it)[0])
        )
        self._register_refresh(
            y_spin, lambda s=y_spin, it=item: s.setValue(self._position_xy(it)[1])
        )

        # Type-specific geometry (editable)
        if isinstance(item, CircleItem):
            diameter_spin = QDoubleSpinBox()
            diameter_spin.setRange(1.0, 100000.0)
            diameter_spin.setDecimals(1)
            diameter_spin.setSingleStep(10.0)
            diameter_spin.setSuffix(" cm")
            diameter_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            diameter_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            diameter_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            diameter_spin.setValue(item.radius * 2)
            diameter_spin.valueChanged.connect(
                lambda val: self._on_dimension_changed(item, 'circle_diameter', val)
            )
            self._form_layout.addRow(self.tr("Diameter:"), diameter_spin)
            self._register_refresh(
                diameter_spin, lambda s=diameter_spin, it=item: s.setValue(it.radius * 2)
            )
        elif isinstance(item, RectangleItem):
            rect = item.rect()
            size_layout = QHBoxLayout()
            size_layout.setSpacing(4)
            size_layout.setContentsMargins(0, 0, 0, 0)

            w_label = QLabel("W:")
            w_spin = QDoubleSpinBox()
            w_spin.setRange(1.0, 100000.0)
            w_spin.setDecimals(1)
            w_spin.setSingleStep(10.0)
            w_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            w_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            w_spin.setValue(rect.width())
            size_layout.addWidget(w_label)
            size_layout.addWidget(w_spin, 1)

            h_label = QLabel("H:")
            h_spin = QDoubleSpinBox()
            h_spin.setRange(1.0, 100000.0)
            h_spin.setDecimals(1)
            h_spin.setSingleStep(10.0)
            h_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            h_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            h_spin.setValue(rect.height())
            size_layout.addWidget(h_label)
            size_layout.addWidget(h_spin, 1)

            w_spin.valueChanged.connect(
                lambda _: self._on_dimension_changed(item, 'rect_size', None, w_spin, h_spin)
            )
            h_spin.valueChanged.connect(
                lambda _: self._on_dimension_changed(item, 'rect_size', None, w_spin, h_spin)
            )

            size_widget = QWidget()
            size_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            size_widget.setLayout(size_layout)
            self._form_layout.addRow(self.tr("Size:"), size_widget)
            self._register_refresh(
                w_spin, lambda s=w_spin, it=item: s.setValue(it.rect().width())
            )
            self._register_refresh(
                h_spin, lambda s=h_spin, it=item: s.setValue(it.rect().height())
            )
        elif isinstance(item, EllipseItem):
            rect = item.rect()
            axes_layout = QHBoxLayout()
            axes_layout.setSpacing(4)
            axes_layout.setContentsMargins(0, 0, 0, 0)

            rx_label = QLabel("X:")
            rx_spin = QDoubleSpinBox()
            rx_spin.setRange(0.5, 100000.0)
            rx_spin.setDecimals(1)
            rx_spin.setSingleStep(5.0)
            rx_spin.setSuffix(" cm")
            rx_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            rx_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            rx_spin.setValue(rect.width() / 2)
            axes_layout.addWidget(rx_label)
            axes_layout.addWidget(rx_spin, 1)

            ry_label = QLabel("Y:")
            ry_spin = QDoubleSpinBox()
            ry_spin.setRange(0.5, 100000.0)
            ry_spin.setDecimals(1)
            ry_spin.setSingleStep(5.0)
            ry_spin.setSuffix(" cm")
            ry_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            ry_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            ry_spin.setValue(rect.height() / 2)
            axes_layout.addWidget(ry_label)
            axes_layout.addWidget(ry_spin, 1)

            rx_spin.valueChanged.connect(
                lambda _: self._on_dimension_changed(item, 'ellipse_axes', None, rx_spin, ry_spin)
            )
            ry_spin.valueChanged.connect(
                lambda _: self._on_dimension_changed(item, 'ellipse_axes', None, rx_spin, ry_spin)
            )

            axes_widget = QWidget()
            axes_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            axes_widget.setLayout(axes_layout)
            self._form_layout.addRow(self.tr("Semi-axes:"), axes_widget)
            self._register_refresh(
                rx_spin, lambda s=rx_spin, it=item: s.setValue(it.rect().width() / 2)
            )
            self._register_refresh(
                ry_spin, lambda s=ry_spin, it=item: s.setValue(it.rect().height() / 2)
            )

    def _add_grid_properties(self, item: QGraphicsItem) -> None:
        """Add grid overlay controls (bed types only)."""
        if not hasattr(item, "object_type") or not is_bed_type(item.object_type):
            return

        separator = QLabel(self.tr("Grid Overlay"))
        separator.setStyleSheet("font-weight: bold; margin-top: 8px;")
        self._form_layout.addRow(separator)

        # Enable checkbox
        grid_check = QCheckBox(self.tr("Show grid"))
        grid_check.setChecked(item.grid_enabled)

        # Cell count (read-only)
        cell_count_label: QLabel | None = None
        if hasattr(item, "grid_cell_count"):
            cell_count_label = QLabel(str(item.grid_cell_count()))

        # Spacing spinbox
        spacing_spin = QDoubleSpinBox()
        spacing_spin.setRange(1.0, 200.0)
        spacing_spin.setSuffix(" cm")
        spacing_spin.setDecimals(1)
        spacing_spin.setValue(item.grid_spacing)

        def on_grid_check(checked: bool) -> None:
            if self._updating:
                return
            item.grid_enabled = checked
            if cell_count_label is not None:
                cell_count_label.setText(str(item.grid_cell_count()))

        def on_spacing_changed(val: float) -> None:
            if self._updating:
                return
            item.grid_spacing = val
            if cell_count_label is not None:
                cell_count_label.setText(str(item.grid_cell_count()))

        grid_check.toggled.connect(on_grid_check)
        spacing_spin.valueChanged.connect(on_spacing_changed)

        self._form_layout.addRow(self.tr("Grid:"), grid_check)
        self._form_layout.addRow(self.tr("Spacing:"), spacing_spin)
        if cell_count_label is not None:
            self._form_layout.addRow(self.tr("Cells:"), cell_count_label)

        self._register_refresh(
            grid_check, lambda c=grid_check, it=item: c.setChecked(it.grid_enabled)
        )
        self._register_refresh(
            spacing_spin, lambda s=spacing_spin, it=item: s.setValue(it.grid_spacing)
        )
        if cell_count_label is not None:
            self._register_refresh(
                cell_count_label,
                lambda lbl=cell_count_label, it=item: lbl.setText(str(it.grid_cell_count())),
            )

    def _add_soil_depth_properties(self, item: QGraphicsItem) -> None:
        """Add soil fill depth control (bed types only, issue #177)."""
        if not hasattr(item, "object_type") or not is_bed_type(item.object_type):
            return
        if not hasattr(item, "metadata"):
            return

        separator = QLabel(self.tr("Soil Fill"))
        separator.setStyleSheet("font-weight: bold; margin-top: 8px;")
        self._form_layout.addRow(separator)

        depth_spin = QSpinBox()
        depth_spin.setRange(1, 200)
        depth_spin.setSuffix(" cm")
        depth_spin.setValue(int(item.metadata.get("soil_depth_cm", 30)))
        depth_spin.setToolTip(self.tr("Fill depth used to calculate soil volume in the Shopping List"))

        def on_depth_changed(val: int) -> None:
            if self._updating:
                return
            item.metadata["soil_depth_cm"] = val

        depth_spin.valueChanged.connect(on_depth_changed)
        self._form_layout.addRow(self.tr("Soil depth:"), depth_spin)
        self._register_refresh(
            depth_spin,
            lambda s=depth_spin, it=item: s.setValue(int(it.metadata.get("soil_depth_cm", 30))),
        )

    def _add_spacing_properties(self, item: QGraphicsItem) -> None:
        """Add plant spacing radius control (plant types only)."""
        if not isinstance(item, CircleItem):
            return
        from open_garden_planner.core.plant_renderer import is_plant_type

        if not is_plant_type(getattr(item, 'object_type', None)):
            return

        spacing_spin = QDoubleSpinBox()
        spacing_spin.setRange(0.0, 10000.0)
        spacing_spin.setDecimals(1)
        spacing_spin.setSingleStep(5.0)
        spacing_spin.setSuffix(" cm")
        spacing_spin.setSpecialValueText(self.tr("—"))  # Show dash when 0 (no data)
        spacing_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spacing_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        effective = item.effective_spacing_radius()
        spacing_spin.setValue(effective if effective is not None else 0.0)
        spacing_spin.setToolTip(self.tr("Recommended spacing radius (half of plant spread)"))
        spacing_spin.valueChanged.connect(
            lambda val, it=item: self._on_spacing_changed(it, val)
        )
        self._form_layout.addRow(self.tr("Spacing radius:"), spacing_spin)
        self._register_refresh(
            spacing_spin,
            lambda s=spacing_spin, it=item: s.setValue(
                eff if (eff := it.effective_spacing_radius()) is not None else 0.0
            ),
        )

        # Frost protection tristate checkbox (US-12.2)
        frost_check = QCheckBox(self.tr("Needs frost protection"))
        frost_check.setTristate(True)
        state_map = {
            True: Qt.CheckState.Checked,
            False: Qt.CheckState.Unchecked,
            None: Qt.CheckState.PartiallyChecked,
        }
        frost_check.setCheckState(
            state_map.get(
                getattr(item, "frost_protection_needed", None),
                Qt.CheckState.PartiallyChecked,
            )
        )
        frost_check.setToolTip(
            self.tr(
                "Override frost sensitivity:\n"
                "☑ Always protect  ☐ Never protect  ‒ Use plant database default"
            )
        )
        frost_check.checkStateChanged.connect(
            lambda state, it=item: self._on_frost_protection_changed(it, state)
        )
        self._form_layout.addRow(self.tr("Frost protection:"), frost_check)
        self._register_refresh(
            frost_check,
            lambda c=frost_check, sm=state_map, it=item: c.setCheckState(
                sm.get(getattr(it, "frost_protection_needed", None), Qt.CheckState.PartiallyChecked)
            ),
        )

    def _on_frost_protection_changed(self, item: QGraphicsItem, state: Qt.CheckState) -> None:
        """Handle frost protection tristate change with undo support."""
        if self._updating:
            return
        value_map = {
            Qt.CheckState.Checked: True,
            Qt.CheckState.Unchecked: False,
            Qt.CheckState.PartiallyChecked: None,
        }
        new_val = value_map.get(state)
        old_val = getattr(item, "frost_protection_needed", None)

        def apply_func(itm: QGraphicsItem, val: bool | None) -> None:
            itm.frost_protection_needed = val  # type: ignore[attr-defined]

        cmd = ChangePropertyCommand(
            item, "frost protection", old_val, new_val,
            apply_func=apply_func,
        )
        if self._command_manager:
            self._command_manager.execute(cmd)

    def _on_spacing_changed(self, item: QGraphicsItem, value: float) -> None:
        """Handle spacing radius change with undo support."""
        if self._updating:
            return
        old_value = item.spacing_radius_cm  # type: ignore[attr-defined]
        # 0.0 means "no override" → clear to None (reverts to database value)
        new_value = value if value > 0.0 else None

        def apply_func(itm: QGraphicsItem, val: float | None) -> None:
            itm.spacing_radius_cm = val  # type: ignore[attr-defined]

        cmd = ChangePropertyCommand(
            item, "spacing radius", old_value, new_value,
            apply_func=apply_func,
        )
        if self._command_manager:
            self._command_manager.execute(cmd)

    def _add_text_properties(self, item: "TextItem") -> None:
        """Add text annotation property fields.

        Args:
            item: TextItem to show properties for
        """
        header = QLabel(self.tr("Text"))
        header.setStyleSheet("font-weight: bold; margin-top: 4px;")
        self._form_layout.addRow(header)

        # Content (multi-line). Live-update the item on every keystroke but
        # commit one undo command after a typing pause (debounce) or on focus-out
        # (issue #210) — FocusOutTextEdit adds the editing_finished signal
        # QTextEdit lacks. Start value is captured here (field rebuilt per
        # selection). Enter inserts a newline as usual — it does not commit.
        content_edit = FocusOutTextEdit()
        content_edit.setPlainText(item.content)
        content_edit.setFixedHeight(80)
        content_edit._ogp_content_start = item.content  # type: ignore[attr-defined]
        self._attach_commit_timer(
            content_edit, lambda: self._on_text_content_commit(item, content_edit)
        )
        content_edit.textChanged.connect(
            lambda: self._on_text_content_live(item, content_edit.toPlainText(), content_edit)
        )
        content_edit.editing_finished.connect(
            lambda it=item, edit=content_edit: self._on_text_content_commit(it, edit)
        )
        self._form_layout.addRow(self.tr("Content:"), content_edit)
        # Keep the start marker in sync so a later focus-edit diffs against the
        # displayed value (#206/#210).
        self._register_refresh(
            content_edit,
            lambda e=content_edit, it=item: (
                e.setPlainText(it.content),
                setattr(e, "_ogp_content_start", it.content),
            ),
        )

        # Font family
        font_combo = QFontComboBox()
        font_combo.setCurrentFont(item.font())
        font_combo.currentFontChanged.connect(
            lambda f: self._on_text_property_changed(item, "font_family", f.family())
        )
        self._form_layout.addRow(self.tr("Font:"), font_combo)
        self._register_refresh(
            font_combo, lambda c=font_combo, it=item: c.setCurrentFont(it.font())
        )

        # Font size (in cm, matching scene units)
        size_spin = QDoubleSpinBox()
        size_spin.setRange(0.1, 100.0)
        size_spin.setSingleStep(0.5)
        size_spin.setDecimals(1)
        size_spin.setSuffix(" cm")
        size_spin.setValue(item.font_size)
        size_spin.valueChanged.connect(
            lambda v: self._on_text_property_changed(item, "font_size", v)
        )
        self._form_layout.addRow(self.tr("Size:"), size_spin)
        self._register_refresh(
            size_spin, lambda s=size_spin, it=item: s.setValue(it.font_size)
        )

        # Bold / Italic row
        style_row = QHBoxLayout()
        bold_check = QCheckBox(self.tr("Bold"))
        bold_check.setChecked(item.bold)
        bold_check.toggled.connect(
            lambda v: self._on_text_property_changed(item, "bold", v)
        )
        italic_check = QCheckBox(self.tr("Italic"))
        italic_check.setChecked(item.italic)
        italic_check.toggled.connect(
            lambda v: self._on_text_property_changed(item, "italic", v)
        )
        style_row.addWidget(bold_check)
        style_row.addWidget(italic_check)
        style_row.addStretch()
        self._form_layout.addRow(self.tr("Style:"), style_row)
        self._register_refresh(bold_check, lambda c=bold_check, it=item: c.setChecked(it.bold))
        self._register_refresh(italic_check, lambda c=italic_check, it=item: c.setChecked(it.italic))

        # Text color
        color_btn = ColorButton(item.text_color)
        color_btn.clicked.connect(
            lambda: self._on_text_color_changed(item, color_btn)
        )
        self._form_layout.addRow(self.tr("Color:"), color_btn)
        self._register_refresh(
            color_btn, lambda b=color_btn, it=item: b.set_color(it.text_color)
        )

    def _on_text_content_live(self, item: "TextItem", value: str, edit: QTextEdit) -> None:
        """Live-apply text content as the user types (visual only, no command).

        The single undo command is committed by _on_text_content_commit after a
        typing pause (debounce) or on focus-out (issue #210). Guarded by
        _updating so the programmatic setPlainText during a rebuild does not
        mutate the item.
        """
        if self._updating:
            return
        item.content = value
        timer = getattr(edit, '_ogp_commit_timer', None)
        if timer is not None:
            timer.start()  # (re)start the debounce — commit when typing pauses

    def _on_text_content_commit(self, item: "TextItem", edit: QTextEdit) -> None:
        """Commit a text-content edit as one undo step (debounce or focus-out)."""
        timer = getattr(edit, '_ogp_commit_timer', None)
        if timer is not None:
            timer.stop()
        if self._updating or self._command_manager is None:
            return
        old_content = getattr(edit, '_ogp_content_start', item.content)
        new_content = edit.toPlainText()
        if new_content == old_content:
            return

        def apply_func(itm: "TextItem", val: str) -> None:
            itm.content = val

        # The live edit already applied new_content; register without
        # re-executing so undo restores old_content in a single step.
        cmd = ChangePropertyCommand(item, "text content", old_content, new_content, apply_func)
        self._command_manager.register_applied(cmd)
        edit._ogp_content_start = new_content  # type: ignore[attr-defined]

    def _on_text_property_changed(self, item: "TextItem", prop: str, value: object) -> None:
        """Handle font property change from properties panel."""
        if self._updating:
            return
        old_val = getattr(item, prop, None)
        setattr(item, prop, value)
        if self._command_manager:
            def apply_func(itm, val, p=prop):
                setattr(itm, p, val)
            # Clean, translatable description fragment (not "text font_family").
            label = _TEXT_PROPERTY_LABELS.get(prop, prop)
            cmd = ChangePropertyCommand(item, label, old_val, value, apply_func)
            self._command_manager.register_applied(cmd)
        scene = item.scene()
        if scene:
            scene.update()

    def _on_text_color_changed(self, item: "TextItem", btn: "ColorButton") -> None:
        """Handle text color change from the color button."""
        if self._updating:
            return
        old_color = item.text_color
        new_color = btn.color
        item.text_color = new_color
        if self._command_manager:
            def apply_func(itm, val):
                itm.text_color = val
            cmd = ChangePropertyCommand(item, "text color", old_color, new_color, apply_func)
            self._command_manager.register_applied(cmd)
        scene = item.scene()
        if scene:
            scene.update()

    def _add_styling_properties(self, item: QGraphicsItem) -> None:
        """Add styling property fields.

        Args:
            item: Item to show styling for
        """
        if not isinstance(item, (RectangleItem, EllipseItem, PolygonItem, CircleItem, PolylineItem)):
            return

        # Path/fence style preset (only for polylines)
        if isinstance(item, PolylineItem):
            style_combo = QComboBox()
            # Add "Paths" group
            style_combo.addItem(self.tr("── Paths ──"), None)
            idx = style_combo.count() - 1
            model = style_combo.model()
            if model:
                model.item(idx).setEnabled(False)
            for pfs in [
                PathFenceStyle.NONE,
                PathFenceStyle.GRAVEL_PATH,
                PathFenceStyle.STEPPING_STONES,
                PathFenceStyle.PAVED_PATH,
                PathFenceStyle.WOODEN_BOARDWALK,
                PathFenceStyle.DIRT_PATH,
            ]:
                style_combo.addItem(get_translated_path_fence_style_name(pfs), pfs)
            # Add "Fences" group
            style_combo.addItem(self.tr("── Fences ──"), None)
            idx = style_combo.count() - 1
            if model:
                model.item(idx).setEnabled(False)
            for pfs in [
                PathFenceStyle.WOODEN_FENCE,
                PathFenceStyle.METAL_FENCE,
                PathFenceStyle.CHAIN_LINK,
                PathFenceStyle.HEDGE_FENCE,
                PathFenceStyle.STONE_WALL,
            ]:
                style_combo.addItem(get_translated_path_fence_style_name(pfs), pfs)

            current_pfs = item.path_fence_style if hasattr(item, 'path_fence_style') else PathFenceStyle.NONE
            for i in range(style_combo.count()):
                if style_combo.itemData(i) == current_pfs:
                    style_combo.setCurrentIndex(i)
                    break

            style_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'path_fence_style', style_combo.currentData())
                if style_combo.currentData() is not None else None
            )
            self._form_layout.addRow(self.tr("Style:"), style_combo)
            self._register_refresh(
                style_combo,
                lambda c=style_combo, it=item: c.setCurrentIndex(
                    idx if (idx := c.findData(getattr(it, 'path_fence_style', PathFenceStyle.NONE))) >= 0
                    else c.currentIndex()
                ),
            )

        # Fill color (not for polylines)
        if not isinstance(item, PolylineItem):
            def _read_fill(it=item) -> QColor:
                return it.fill_color if getattr(it, 'fill_color', None) else it.brush().color()

            fill_btn = ColorButton(_read_fill())
            fill_btn.clicked.connect(
                lambda: self._on_color_changed(item, 'fill_color', fill_btn)
            )
            self._form_layout.addRow(self.tr("Fill Color:"), fill_btn)
            self._register_refresh(fill_btn, lambda b=fill_btn: b.set_color(_read_fill()))

            # Fill pattern
            pattern_combo = QComboBox()
            _pattern_names = {
                FillPattern.SOLID: self.tr("Solid"),
                FillPattern.GRASS: self.tr("Grass"),
                FillPattern.GRAVEL: self.tr("Gravel"),
                FillPattern.CONCRETE: self.tr("Concrete"),
                FillPattern.WOOD: self.tr("Wood"),
                FillPattern.WATER: self.tr("Water"),
                FillPattern.SOIL: self.tr("Soil"),
                FillPattern.MULCH: self.tr("Mulch"),
                FillPattern.ROOF_TILES: self.tr("Roof Tiles"),
                FillPattern.SAND: self.tr("Sand"),
                FillPattern.STONE: self.tr("Stone"),
                FillPattern.GLASS: self.tr("Glass"),
                FillPattern.HEDGE: self.tr("Hedge"),
                FillPattern.BRICK: self.tr("Brick"),
                FillPattern.BARK: self.tr("Bark"),
                FillPattern.WILDFLOWER: self.tr("Wildflower Meadow"),
                FillPattern.TERRACOTTA: self.tr("Terracotta"),
                FillPattern.PEBBLES: self.tr("Pebbles"),
                FillPattern.SLATE: self.tr("Slate"),
                FillPattern.LATTICE: self.tr("Lattice"),
                FillPattern.COMPOST: self.tr("Compost"),
                FillPattern.FLAGSTONE: self.tr("Flagstone"),
                FillPattern.CLAY: self.tr("Clay"),
            }
            for pattern in FillPattern:
                pattern_combo.addItem(_pattern_names.get(pattern, pattern.name), pattern)

            current_pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            for i in range(pattern_combo.count()):
                if pattern_combo.itemData(i) == current_pattern:
                    pattern_combo.setCurrentIndex(i)
                    break

            pattern_combo.currentIndexChanged.connect(
                lambda: self._on_property_changed(item, 'fill_pattern', pattern_combo.currentData())
            )
            self._form_layout.addRow(self.tr("Fill Pattern:"), pattern_combo)
            self._register_refresh(
                pattern_combo,
                lambda c=pattern_combo, it=item: c.setCurrentIndex(
                    idx if (idx := c.findData(getattr(it, 'fill_pattern', FillPattern.SOLID))) >= 0
                    else c.currentIndex()
                ),
            )

        # Stroke color
        def _read_stroke(it=item) -> QColor:
            return it.stroke_color if getattr(it, 'stroke_color', None) else it.pen().color()

        stroke_btn = ColorButton(_read_stroke())
        stroke_btn.clicked.connect(
            lambda: self._on_color_changed(item, 'stroke_color', stroke_btn)
        )
        self._form_layout.addRow(self.tr("Stroke Color:"), stroke_btn)
        self._register_refresh(stroke_btn, lambda b=stroke_btn: b.set_color(_read_stroke()))

        # Stroke width
        width_spin = QDoubleSpinBox()
        width_spin.setRange(0.5, 20.0)
        width_spin.setSingleStep(0.5)
        width_spin.setDecimals(1)
        width_spin.setSuffix(" px")
        width_spin.setValue(
            item.stroke_width if hasattr(item, 'stroke_width') and item.stroke_width else item.pen().widthF()
        )
        width_spin.valueChanged.connect(
            lambda val: self._on_property_changed(item, 'stroke_width', val)
        )
        self._form_layout.addRow(self.tr("Stroke Width:"), width_spin)
        self._register_refresh(
            width_spin,
            lambda s=width_spin, it=item: s.setValue(
                it.stroke_width if getattr(it, 'stroke_width', None) else it.pen().widthF()
            ),
        )

        # Stroke style
        stroke_style_combo = QComboBox()
        _style_names = {
            StrokeStyle.SOLID: self.tr("Solid"),
            StrokeStyle.DASHED: self.tr("Dashed"),
            StrokeStyle.DOTTED: self.tr("Dotted"),
            StrokeStyle.DASH_DOT: self.tr("Dash Dot"),
        }
        for style in StrokeStyle:
            stroke_style_combo.addItem(_style_names.get(style, style.name), style)

        current_style = item.stroke_style if hasattr(item, 'stroke_style') else StrokeStyle.SOLID
        for i in range(stroke_style_combo.count()):
            if stroke_style_combo.itemData(i) == current_style:
                stroke_style_combo.setCurrentIndex(i)
                break

        stroke_style_combo.currentIndexChanged.connect(
            lambda: self._on_property_changed(item, 'stroke_style', stroke_style_combo.currentData())
        )
        self._form_layout.addRow(self.tr("Stroke Style:"), stroke_style_combo)
        self._register_refresh(
            stroke_style_combo,
            lambda c=stroke_style_combo, it=item: c.setCurrentIndex(
                idx if (idx := c.findData(getattr(it, 'stroke_style', StrokeStyle.SOLID))) >= 0
                else c.currentIndex()
            ),
        )

    def _capture_item_state(self, item: QGraphicsItem) -> dict:
        """Capture the current state of an item for undo purposes.

        Args:
            item: The item to capture state from

        Returns:
            Dictionary with all relevant property values
        """
        state = {}
        if hasattr(item, 'object_type'):
            state['object_type'] = item.object_type
        if hasattr(item, 'name'):
            state['name'] = item.name
        if hasattr(item, 'layer_id'):
            state['layer_id'] = item.layer_id
        if hasattr(item, 'fill_color'):
            state['fill_color'] = QColor(item.fill_color) if item.fill_color else None
        if hasattr(item, 'fill_pattern'):
            state['fill_pattern'] = item.fill_pattern
        if hasattr(item, 'stroke_color'):
            state['stroke_color'] = QColor(item.stroke_color) if item.stroke_color else None
        if hasattr(item, 'stroke_width'):
            state['stroke_width'] = item.stroke_width
        if hasattr(item, 'stroke_style'):
            state['stroke_style'] = item.stroke_style
        if hasattr(item, 'path_fence_style'):
            state['path_fence_style'] = item.path_fence_style
        return state

    def _apply_item_state(self, item: QGraphicsItem, state: dict) -> None:
        """Apply a captured state to an item.

        Args:
            item: The item to apply state to
            state: Dictionary with property values
        """
        if 'object_type' in state and hasattr(item, 'object_type'):
            item.object_type = state['object_type']

        if 'name' in state and hasattr(item, 'name'):
            item.name = state['name']
            if hasattr(item, '_update_label'):
                item._update_label()

        if 'layer_id' in state and hasattr(item, 'layer_id'):
            item.layer_id = state['layer_id']
            scene = item.scene()
            if scene and hasattr(scene, 'get_layer_by_id'):
                layer = scene.get_layer_by_id(state['layer_id'])
                if layer:
                    item.setZValue(layer.z_order * 100)

        if 'fill_color' in state and hasattr(item, 'fill_color'):
            item.fill_color = state['fill_color']
        if 'fill_pattern' in state and hasattr(item, 'fill_pattern'):
            item.fill_pattern = state['fill_pattern']
        if 'stroke_color' in state and hasattr(item, 'stroke_color'):
            item.stroke_color = state['stroke_color']
        if 'stroke_width' in state and hasattr(item, 'stroke_width'):
            item.stroke_width = state['stroke_width']
        if 'stroke_style' in state and hasattr(item, 'stroke_style'):
            item.stroke_style = state['stroke_style']
        if 'path_fence_style' in state and hasattr(item, 'path_fence_style'):
            item.path_fence_style = state['path_fence_style']
            if hasattr(item, 'apply_style_preset'):
                item.apply_style_preset()

        # Update visual appearance
        if not isinstance(item, PolylineItem):
            pattern = state.get('fill_pattern', FillPattern.SOLID)
            color = state.get('fill_color') or item.brush().color()
            brush = create_pattern_brush(pattern, color)
            item.setBrush(brush)

        stroke_color = state.get('stroke_color') or item.pen().color()
        stroke_width = state.get('stroke_width', item.pen().widthF())
        stroke_style = state.get('stroke_style', StrokeStyle.SOLID)
        pen = QPen(stroke_color)
        pen.setWidthF(stroke_width)
        pen.setStyle(stroke_style.to_qt_pen_style())
        item.setPen(pen)

        # Update scene
        scene = item.scene()
        if scene:
            scene.update()

    def _on_position_changed(
        self, item: QGraphicsItem, x_spin: QDoubleSpinBox, y_spin: QDoubleSpinBox
    ) -> None:
        """Handle position change with undo support and constraint solving.

        Args:
            item: Item being moved
            x_spin: X coordinate spin box
            y_spin: Y coordinate spin box
        """
        if self._updating:
            return

        from PyQt6.QtCore import QPointF

        from open_garden_planner.core.commands import AlignItemsCommand, MoveItemsCommand

        # Get new position from spin boxes
        # View transform already flips Y, so scene coords = CAD coords (no conversion)
        new_scene_x = x_spin.value()
        new_scene_y = y_spin.value()

        # Get current position (topLeft of bbox = CAD bottom-left)
        bbox = item.boundingRect()
        top_left_local = bbox.topLeft()
        old_top_left_scene = item.mapToScene(top_left_local)

        scene = item.scene()
        if not scene:
            return

        # Calculate delta in scene coordinates
        delta = QPointF(
            new_scene_x - old_top_left_scene.x(),
            new_scene_y - old_top_left_scene.y()
        )

        # Validate bounds - don't allow moving outside canvas area (0, 0, width, height in scene coords)
        canvas_rect = scene.canvas_rect  # QRectF(0, 0, width_cm, height_cm)
        # Calculate where corners would be after the move (in scene coordinates)
        top_left_after = item.mapToScene(bbox.topLeft()) + delta
        bottom_right_after = item.mapToScene(bbox.bottomRight()) + delta

        # Clamp to canvas bounds (not scene bounds with padding)
        if top_left_after.x() < canvas_rect.left():
            delta.setX(delta.x() + (canvas_rect.left() - top_left_after.x()))
        if top_left_after.y() < canvas_rect.top():
            delta.setY(delta.y() + (canvas_rect.top() - top_left_after.y()))
        if bottom_right_after.x() > canvas_rect.right():
            delta.setX(delta.x() - (bottom_right_after.x() - canvas_rect.right()))
        if bottom_right_after.y() > canvas_rect.bottom():
            delta.setY(delta.y() - (bottom_right_after.y() - canvas_rect.bottom()))

        # Skip if no movement
        if abs(delta.x()) < 0.01 and abs(delta.y()) < 0.01:
            return

        # Check if item is constrained
        scene = item.scene()
        if scene and hasattr(scene, 'constraint_graph'):
            from open_garden_planner.ui.canvas.items import GardenItemMixin

            graph = scene.constraint_graph
            if isinstance(item, GardenItemMixin) and graph.constraints:
                # Compute constraint propagation
                constrained_ids = set()
                for c in graph.constraints.values():
                    constrained_ids.add(c.anchor_a.item_id)
                    constrained_ids.add(c.anchor_b.item_id)

                if item.item_id in constrained_ids:
                    # Get canvas view to compute propagation
                    view = scene.views()[0] if scene.views() else None
                    if view and hasattr(view, '_compute_constraint_propagation'):
                        propagated_deltas = view._compute_constraint_propagation([item], delta)

                        if propagated_deltas:
                            # Combine dragged + propagated into per-item deltas
                            all_deltas = [(item, delta)]
                            all_deltas.extend(propagated_deltas)
                            command = AlignItemsCommand(
                                all_deltas,
                                QCoreApplication.translate(
                                    "Commands", "Move item (constrained)"
                                ),
                            )
                            if self._command_manager:
                                self._command_manager.execute(command)
                            return

        # No constraints or no propagation - simple move
        command = MoveItemsCommand([item], delta)
        if self._command_manager:
            self._command_manager.execute(command)

    def _on_dimension_changed(
        self,
        item: QGraphicsItem,
        dimension_type: str,
        value: float | None = None,
        width_spin: QDoubleSpinBox | None = None,
        height_spin: QDoubleSpinBox | None = None,
    ) -> None:
        """Handle dimension (width/height/diameter) change with undo support.

        Args:
            item: Item being resized
            dimension_type: 'circle_diameter' or 'rect_size'
            value: New diameter value (for circles)
            width_spin: Width spin box (for rectangles)
            height_spin: Height spin box (for rectangles)
        """
        if self._updating:
            return

        from PyQt6.QtCore import QPointF

        from open_garden_planner.core.commands import ResizeItemCommand

        if dimension_type == 'circle_diameter' and isinstance(item, CircleItem):
            new_diameter = value
            if new_diameter is None or new_diameter <= 0:
                return
            new_radius = new_diameter / 2.0

            old_rect = item.rect()
            old_pos = item.pos()
            old_radius = old_rect.width() / 2.0

            # Keep scene-space center fixed
            center_x = old_pos.x() + old_rect.x() + old_radius
            center_y = old_pos.y() + old_rect.y() + old_radius

            new_pos_x = center_x - new_radius
            new_pos_y = center_y - new_radius

            old_geometry = {
                'rect_x': old_rect.x(),
                'rect_y': old_rect.y(),
                'diameter': old_rect.width(),
                'center_x': old_rect.x() + old_radius,
                'center_y': old_rect.y() + old_radius,
                'radius': old_radius,
                'pos_x': old_pos.x(),
                'pos_y': old_pos.y(),
            }
            new_geometry = {
                'rect_x': 0.0,
                'rect_y': 0.0,
                'diameter': new_diameter,
                'center_x': new_radius,
                'center_y': new_radius,
                'radius': new_radius,
                'pos_x': new_pos_x,
                'pos_y': new_pos_y,
            }

            def apply_circle(itm: QGraphicsItem, geom: dict) -> None:
                if isinstance(itm, CircleItem):
                    itm.setRect(
                        geom['rect_x'], geom['rect_y'],
                        geom['diameter'], geom['diameter'],
                    )
                    itm._center = QPointF(geom['center_x'], geom['center_y'])
                    itm._radius = geom['radius']
                    itm.setPos(geom['pos_x'], geom['pos_y'])
                    itm.update_resize_handles()
                    itm._position_label()
                    itm._update_circle_annotations()

            apply_circle(item, new_geometry)

            if self._command_manager:
                cmd = ResizeItemCommand(item, old_geometry, new_geometry, apply_circle)
                self._command_manager.register_applied(cmd)

        elif (
            dimension_type == 'rect_size'
            and isinstance(item, RectangleItem)
            and width_spin is not None
            and height_spin is not None
        ):
            new_width = width_spin.value()
            new_height = height_spin.value()
            if new_width <= 0 or new_height <= 0:
                return

            old_rect = item.rect()
            old_pos = item.pos()

            old_geometry = {
                'rect_x': old_rect.x(),
                'rect_y': old_rect.y(),
                'width': old_rect.width(),
                'height': old_rect.height(),
                'pos_x': old_pos.x(),
                'pos_y': old_pos.y(),
            }
            new_geometry = {
                'rect_x': old_rect.x(),
                'rect_y': old_rect.y(),
                'width': new_width,
                'height': new_height,
                'pos_x': old_pos.x(),
                'pos_y': old_pos.y(),
            }

            def apply_rect(itm: QGraphicsItem, geom: dict) -> None:
                if isinstance(itm, RectangleItem):
                    itm.setRect(
                        geom['rect_x'], geom['rect_y'],
                        geom['width'], geom['height'],
                    )
                    itm.setPos(geom['pos_x'], geom['pos_y'])
                    itm.update_resize_handles()
                    itm._position_label()

            apply_rect(item, new_geometry)

            if self._command_manager:
                cmd = ResizeItemCommand(item, old_geometry, new_geometry, apply_rect)
                self._command_manager.register_applied(cmd)

        elif (
            dimension_type == 'ellipse_axes'
            and isinstance(item, EllipseItem)
            and width_spin is not None
            and height_spin is not None
        ):
            new_rx = width_spin.value()
            new_ry = height_spin.value()
            if new_rx <= 0 or new_ry <= 0:
                return

            old_rect = item.rect()
            old_pos = item.pos()

            old_geometry = {
                'rect_x': old_rect.x(), 'rect_y': old_rect.y(),
                'width': old_rect.width(), 'height': old_rect.height(),
                'pos_x': old_pos.x(), 'pos_y': old_pos.y(),
            }
            new_geometry = {
                'rect_x': old_rect.x(), 'rect_y': old_rect.y(),
                'width': new_rx * 2, 'height': new_ry * 2,
                'pos_x': old_pos.x(), 'pos_y': old_pos.y(),
            }

            def apply_ellipse(itm: QGraphicsItem, geom: dict) -> None:
                if isinstance(itm, EllipseItem):
                    itm.setRect(geom['rect_x'], geom['rect_y'], geom['width'], geom['height'])
                    itm.setPos(geom['pos_x'], geom['pos_y'])
                    itm.update_resize_handles()
                    itm._position_label()

            apply_ellipse(item, new_geometry)

            if self._command_manager:
                cmd = ResizeItemCommand(item, old_geometry, new_geometry, apply_ellipse)
                self._command_manager.register_applied(cmd)

        else:
            return

        # Update scene and run constraint solver
        scene = item.scene()
        if scene:
            scene.update()
            views = scene.views()
            if views and hasattr(views[0], 'apply_constraint_solver'):
                views[0].apply_constraint_solver()

    def _attach_commit_timer(self, edit: QWidget, on_commit: Callable[[], None]) -> None:
        """Attach a single-shot debounce timer that commits a free-text edit.

        The timer is stored on the widget as ``_ogp_commit_timer`` (restarted on
        each keystroke by the live handler, stopped by the commit handler). The
        same ``on_commit`` callback is also queued in ``_pending_text_commits``
        so a rebuild flushes the edit before the widget is destroyed. See
        _TEXT_COMMIT_DEBOUNCE_MS (issue #210).
        """
        timer = QTimer(edit)
        timer.setSingleShot(True)
        timer.setInterval(_TEXT_COMMIT_DEBOUNCE_MS)
        timer.timeout.connect(on_commit)
        edit._ogp_commit_timer = timer  # type: ignore[attr-defined]
        self._pending_text_commits.append(on_commit)

    def _on_name_text_changed(self, item: QGraphicsItem, text: str, edit: QLineEdit) -> None:
        """Live-update the canvas label as the user types the Name field.

        Visual feedback only — no undo command and no calendar refresh; the
        single command is committed by _on_name_commit after a typing pause
        (debounce) or on focus-out (issue #210). Guarded by _updating so
        programmatic setText during a panel rebuild does not mutate the item.
        """
        if self._updating:
            return
        item.name = text  # type: ignore[attr-defined]
        if hasattr(item, '_update_label'):
            item._update_label()
        timer = getattr(edit, '_ogp_commit_timer', None)
        if timer is not None:
            timer.start()  # (re)start the debounce — commit when typing pauses

    def _on_name_commit(self, item: QGraphicsItem, edit: QLineEdit) -> None:
        """Commit a Name edit as one undo step (debounce timeout or focus-out).

        Compares against the value captured when the field was built; registers
        a single ChangePropertyCommand only if it actually changed, then resets
        the captured start so the debounce-then-focus-out double fire (or a no-op
        focus-out) does not push a duplicate command.
        """
        timer = getattr(edit, '_ogp_commit_timer', None)
        if timer is not None:
            timer.stop()
        if self._updating or self._command_manager is None:
            return
        old_name = getattr(edit, '_ogp_name_start', item.name)
        new_name = edit.text()
        if new_name == old_name:
            return

        def apply_name(itm: QGraphicsItem, val: str) -> None:
            itm.name = val  # type: ignore[attr-defined]
            if hasattr(itm, '_update_label'):
                itm._update_label()

        # The live edit already applied new_name to the item; register without
        # re-executing so undo restores old_name in a single step.
        cmd = ChangePropertyCommand(item, "name", old_name, new_name, apply_name)
        self._command_manager.register_applied(cmd)
        edit._ogp_name_start = new_name  # type: ignore[attr-defined]

    def _on_property_changed(self, item: QGraphicsItem, property_name: str, value) -> None:
        """Handle property change with undo support.

        Args:
            item: Item being edited
            property_name: Name of the property
            value: New value
        """
        if self._updating:
            return

        # Capture old state for undo
        old_state = self._capture_item_state(item)

        # Apply the change to the item
        if property_name == 'object_type' and hasattr(item, 'object_type'):
            # Object type change affects many properties
            style = get_style(value)
            new_state = {
                'object_type': value,
                'fill_color': style.fill_color,
                'fill_pattern': style.fill_pattern,
                'stroke_color': style.stroke_color,
                'stroke_width': style.stroke_width,
                'stroke_style': style.stroke_style,
            }
            self._apply_item_state(item, new_state)

            # Create undo command if we have a command manager
            if self._command_manager:
                def apply_func(itm, state):
                    self._apply_item_state(itm, state)
                cmd = ChangePropertyCommand(item, "type", old_state, new_state, apply_func)
                # Don't execute - already applied, just add to stack
                self._command_manager.register_applied(cmd)

            # Defer panel refresh to avoid destroying widgets while signal is processing
            QTimer.singleShot(0, lambda: self.set_selected_items([item]))

            # Notify other panels that the object type changed
            QTimer.singleShot(0, self.object_type_changed.emit)


        elif property_name == 'label_visible' and hasattr(item, 'label_visible'):
            old_visible = item.label_visible
            item.label_visible = value

            if self._command_manager:
                def apply_label_visible(itm, val):
                    itm.label_visible = val
                cmd = ChangePropertyCommand(item, "label visibility", old_visible, value, apply_label_visible)
                self._command_manager.register_applied(cmd)

        elif property_name == 'layer_id' and hasattr(item, 'layer_id'):
            old_layer = item.layer_id
            item.layer_id = value
            scene = item.scene()
            if scene and hasattr(scene, 'get_layer_by_id'):
                layer = scene.get_layer_by_id(value)
                if layer:
                    item.setZValue(layer.z_order * 100)

            if self._command_manager:
                def apply_layer(itm, val):
                    itm.layer_id = val
                    sc = itm.scene()
                    if sc and hasattr(sc, 'get_layer_by_id'):
                        lyr = sc.get_layer_by_id(val)
                        if lyr:
                            itm.setZValue(lyr.z_order * 100)
                cmd = ChangePropertyCommand(item, "layer", old_layer, value, apply_layer)
                self._command_manager.register_applied(cmd)

        elif property_name == 'fill_pattern':
            old_pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            if hasattr(item, 'fill_pattern'):
                item.fill_pattern = value
            color = item.fill_color if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()
            brush = create_pattern_brush(value, color)
            item.setBrush(brush)

            if self._command_manager:
                def apply_pattern(itm, val):
                    if hasattr(itm, 'fill_pattern'):
                        itm.fill_pattern = val
                    c = itm.fill_color if hasattr(itm, 'fill_color') and itm.fill_color else itm.brush().color()
                    itm.setBrush(create_pattern_brush(val, c))
                cmd = ChangePropertyCommand(item, "fill pattern", old_pattern, value, apply_pattern)
                self._command_manager.register_applied(cmd)

        elif property_name == 'stroke_width':
            old_width = item.stroke_width if hasattr(item, 'stroke_width') else item.pen().widthF()
            if hasattr(item, 'stroke_width'):
                item.stroke_width = value
            pen = item.pen()
            pen.setWidthF(value)
            item.setPen(pen)

            if self._command_manager:
                def apply_width(itm, val):
                    if hasattr(itm, 'stroke_width'):
                        itm.stroke_width = val
                    p = itm.pen()
                    p.setWidthF(val)
                    itm.setPen(p)
                cmd = ChangePropertyCommand(item, "stroke width", old_width, value, apply_width)
                self._command_manager.register_applied(cmd)

        elif property_name == 'stroke_style':
            old_style = item.stroke_style if hasattr(item, 'stroke_style') else StrokeStyle.SOLID
            if hasattr(item, 'stroke_style'):
                item.stroke_style = value
            pen = item.pen()
            pen.setStyle(value.to_qt_pen_style())
            item.setPen(pen)

            if self._command_manager:
                def apply_stroke_style(itm, val):
                    if hasattr(itm, 'stroke_style'):
                        itm.stroke_style = val
                    p = itm.pen()
                    p.setStyle(val.to_qt_pen_style())
                    itm.setPen(p)
                cmd = ChangePropertyCommand(item, "stroke style", old_style, value, apply_stroke_style)
                self._command_manager.register_applied(cmd)

        elif property_name == 'path_fence_style':
            old_pfs = item.path_fence_style if hasattr(item, 'path_fence_style') else PathFenceStyle.NONE
            if hasattr(item, 'path_fence_style'):
                item.path_fence_style = value
            if hasattr(item, 'apply_style_preset'):
                item.apply_style_preset()
            item.update()

            if self._command_manager:
                def apply_pfs(itm, val):
                    if hasattr(itm, 'path_fence_style'):
                        itm.path_fence_style = val
                    if hasattr(itm, 'apply_style_preset'):
                        itm.apply_style_preset()
                    itm.update()
                cmd = ChangePropertyCommand(item, "path/fence style", old_pfs, value, apply_pfs)
                self._command_manager.register_applied(cmd)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()

    def _on_color_changed(self, item: QGraphicsItem, property_name: str, button: ColorButton) -> None:
        """Handle color button change with undo support.

        Args:
            item: Item being edited
            property_name: Name of the color property ('fill_color' or 'stroke_color')
            button: The color button that was changed
        """
        if self._updating:
            return

        color = button.color

        if property_name == 'fill_color':
            # Capture old value for undo
            old_color = QColor(item.fill_color) if hasattr(item, 'fill_color') and item.fill_color else item.brush().color()

            # Store the color
            if hasattr(item, 'fill_color'):
                item.fill_color = color
            # Apply to brush
            pattern = item.fill_pattern if hasattr(item, 'fill_pattern') else FillPattern.SOLID
            brush = create_pattern_brush(pattern, color)
            item.setBrush(brush)

            # Create undo command
            if self._command_manager:
                def apply_fill_color(itm, val):
                    if hasattr(itm, 'fill_color'):
                        itm.fill_color = val
                    p = itm.fill_pattern if hasattr(itm, 'fill_pattern') else FillPattern.SOLID
                    itm.setBrush(create_pattern_brush(p, val))
                cmd = ChangePropertyCommand(item, "fill color", old_color, color, apply_fill_color)
                self._command_manager.register_applied(cmd)

        elif property_name == 'stroke_color':
            # Capture old value for undo
            old_color = QColor(item.stroke_color) if hasattr(item, 'stroke_color') and item.stroke_color else item.pen().color()

            # Store the color
            if hasattr(item, 'stroke_color'):
                item.stroke_color = color
            # Apply to pen
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)

            # Create undo command
            if self._command_manager:
                def apply_stroke_color(itm, val):
                    if hasattr(itm, 'stroke_color'):
                        itm.stroke_color = val
                    p = itm.pen()
                    p.setColor(val)
                    itm.setPen(p)
                cmd = ChangePropertyCommand(item, "stroke color", old_color, color, apply_stroke_color)
                self._command_manager.register_applied(cmd)

        # Mark scene as modified
        scene = item.scene()
        if scene:
            scene.update()
