"""Issue #206 — Properties panel updates incrementally, no rebuild-on-every-signal.

`PropertiesPanel.set_selected_items()` used to tear down and recreate the whole
form on every call (it is wired to fire on every command_executed /
can_undo_changed / can_redo_changed). That per-signal teardown was the root
cause of the #200 focus loss, patched only by a focus guard.

Since #206 the panel rebuilds **only** when the selection set / form structure
actually changes; an unchanged selection pushes fresh model values into the live
widgets in place. These tests lock that contract:

- a pure property edit (same selection) reuses the widgets (no rebuild),
- geometry / colour values stay in sync after a non-panel edit + undo/redo,
- a genuine selection change still rebuilds,
- the in-place refresh never stomps a focused field.
"""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QDoubleSpinBox, QLabel, QLineEdit

from open_garden_planner.core.commands import (
    ChangePropertyCommand,
    CommandManager,
    SetParentBedCommand,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel
from open_garden_planner.ui.panels.properties_panel import ColorButton


def _field_by_label(panel: PropertiesPanel, label_text: str):
    """Return the field widget whose form-row label contains label_text."""
    form = panel._form_layout
    for i in range(form.rowCount()):
        label_item = form.itemAt(i, form.ItemRole.LabelRole)
        field_item = form.itemAt(i, form.ItemRole.FieldRole)
        if label_item is None or field_item is None:
            continue
        label_widget = label_item.widget()
        if isinstance(label_widget, QLabel) and label_text in label_widget.text():
            return field_item.widget()
    return None


def _set_fill_color(item, color: QColor) -> None:
    item.fill_color = color


class TestNoRebuildOnSameSelection:
    """A property edit on the unchanged selection must not tear down the form."""

    def test_widgets_are_reused(self, qtbot) -> None:  # noqa: ARG002
        panel = PropertiesPanel(command_manager=CommandManager())
        item = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item])

        name_before = _field_by_label(panel, "Name")
        fill_before = _field_by_label(panel, "Fill Color")
        assert isinstance(name_before, QLineEdit)
        assert isinstance(fill_before, ColorButton)

        # Re-trigger with the SAME selection (what command_executed does in the
        # real app). The widgets must be the very same objects — not recreated.
        panel.set_selected_items([item])

        assert _field_by_label(panel, "Name") is name_before, "Name widget rebuilt"
        assert _field_by_label(panel, "Fill Color") is fill_before, "Fill widget rebuilt"


class TestValueRefresh:
    """Same-selection refresh keeps displayed values in sync with the model."""

    def test_position_refreshes_after_move(self, qtbot) -> None:  # noqa: ARG002
        """A canvas drag (item.setPos) followed by the deferred panel update must
        show the new position — the staleness a naive same-selection skip causes."""
        panel = PropertiesPanel(command_manager=CommandManager())
        item = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item])

        pos_widget = _field_by_label(panel, "Position")
        spins = pos_widget.findChildren(QDoubleSpinBox)
        assert len(spins) == 2, "Position field should hold X and Y spin boxes"
        x_spin = spins[0]
        x_before = x_spin.value()

        # Move the item (as a canvas drag would) then re-trigger the panel.
        item.setPos(item.pos().x() + 40.0, item.pos().y())
        panel.set_selected_items([item])

        assert x_spin.value() == x_before + 40.0, "Position X must refresh after a move (#206)"

    def test_fill_color_refreshes_on_undo_redo(self, qtbot) -> None:  # noqa: ARG002
        manager = CommandManager()
        panel = PropertiesPanel(command_manager=manager)
        item = RectangleItem(0, 0, 100, 50)
        _set_fill_color(item, QColor("red"))
        panel.set_selected_items([item])

        fill_btn = _field_by_label(panel, "Fill Color")
        assert isinstance(fill_btn, ColorButton)
        assert fill_btn.color.name() == QColor("red").name()

        # Change the fill via a command (as the colour button would), then run
        # the deferred refresh.
        cmd = ChangePropertyCommand(
            item, "fill color", QColor("red"), QColor("blue"), _set_fill_color
        )
        manager.execute(cmd)
        panel.set_selected_items([item])
        assert fill_btn.color.name() == QColor("blue").name(), "fill must refresh"

        # Undo restores the old colour in the panel without a rebuild.
        manager.undo()
        panel.set_selected_items([item])
        assert fill_btn is _field_by_label(panel, "Fill Color"), "widget rebuilt on undo"
        assert fill_btn.color.name() == QColor("red").name(), "undo must refresh fill"

        # Redo re-applies it.
        manager.redo()
        panel.set_selected_items([item])
        assert fill_btn.color.name() == QColor("blue").name(), "redo must refresh fill"

    def test_diameter_refreshes_after_resize(self, qtbot) -> None:  # noqa: ARG002
        panel = PropertiesPanel(command_manager=CommandManager())
        item = CircleItem(0, 0, 20)  # radius 20 -> diameter 40
        panel.set_selected_items([item])

        diameter_spin = _field_by_label(panel, "Diameter")
        assert isinstance(diameter_spin, QDoubleSpinBox)
        assert diameter_spin.value() == 40.0

        item.set_radius_centered(30)
        panel.set_selected_items([item])
        assert diameter_spin.value() == 60.0, "Diameter must refresh after resize"


class TestRebuildOnSelectionChange:
    """A genuine selection change still rebuilds the form."""

    def test_different_item_rebuilds(self, qtbot) -> None:  # noqa: ARG002
        panel = PropertiesPanel(command_manager=CommandManager())
        a = RectangleItem(0, 0, 100, 50)
        b = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([a])
        name_a = _field_by_label(panel, "Name")

        panel.set_selected_items([b])
        name_b = _field_by_label(panel, "Name")
        assert name_b is not name_a, "selecting a different item must rebuild the form"

    def test_empty_selection_clears(self, qtbot) -> None:  # noqa: ARG002
        panel = PropertiesPanel(command_manager=CommandManager())
        item = RectangleItem(0, 0, 100, 50)
        panel.set_selected_items([item])
        assert _field_by_label(panel, "Name") is not None

        panel.set_selected_items([])
        assert _field_by_label(panel, "Name") is None


class TestLayerComboRefresh:
    """The Layer combo's *items* come from mutable external state (`scene.layers`),
    so the refresh path must repopulate the list, not just re-index — a layer
    rename/add while an item stays selected must reach the dropdown (#206/#222
    senior-review P1: a plain re-index left the old name / omitted a new layer)."""

    def _layer_combo(self, panel: PropertiesPanel):
        from PyQt6.QtWidgets import QComboBox

        widget = _field_by_label(panel, "Layer")
        assert isinstance(widget, QComboBox), "Layer combo not found in panel"
        return widget

    def test_layer_rename_reaches_combo_on_refresh(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene(2000, 2000)
        item = RectangleItem(0, 0, 100, 50)
        item.layer_id = scene.layers[0].id
        scene.addItem(item)

        panel = PropertiesPanel(command_manager=CommandManager())
        panel.set_selected_items([item])
        combo = self._layer_combo(panel)
        original = scene.layers[0].name
        assert combo.currentText() == original

        # Rename the layer (model change, no identity delta) then re-trigger the
        # deferred panel update — the refresh path must show the new name.
        scene.layers[0].name = "RENAMED-LAYER"
        panel.set_selected_items([item])
        assert combo is self._layer_combo(panel), "Layer combo rebuilt, not refreshed"
        assert combo.currentText() == "RENAMED-LAYER", (
            "Layer rename must reach the combo on the refresh path (#222)"
        )

    def test_new_layer_appears_in_combo_on_refresh(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.models.layer import Layer

        scene = CanvasScene(2000, 2000)
        item = RectangleItem(0, 0, 100, 50)
        item.layer_id = scene.layers[0].id
        scene.addItem(item)

        panel = PropertiesPanel(command_manager=CommandManager())
        panel.set_selected_items([item])
        combo = self._layer_combo(panel)
        count_before = combo.count()

        scene.add_layer(Layer(name="Extra Layer"))
        panel.set_selected_items([item])
        assert combo.count() == count_before + 1, "new layer must appear on refresh"
        assert "Extra Layer" in [combo.itemText(i) for i in range(combo.count())]


def _label_texts(panel: PropertiesPanel) -> list[str]:
    """All QLabel texts currently shown in the form."""
    return [lbl.text() for lbl in panel.findChildren(QLabel)]


def _set_name(item, value: str) -> None:
    item.name = value


def _make_bed(name: str) -> PolygonItem:
    bed = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 400), QPointF(0, 400)],
        object_type=ObjectType.GARDEN_BED,
    )
    bed.name = name
    return bed


class TestReadOnlySummaryRowsStayFresh:
    """#206 senior-review P1: the Parent Bed / Contained Plants summary rows show
    a *related* item's name. A rename/undo of that related item, while the
    current item stays selected, must not leave the summary stale — the
    relationship summary key in _compute_identity forces a rebuild for it."""

    def test_parent_bed_name_refreshes_on_rename_undo(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene(2000, 2000)
        manager = CommandManager()
        bed = _make_bed("Bed A")
        plant = CircleItem(200, 200, 20, object_type=ObjectType.TREE)
        scene.addItem(bed)
        scene.addItem(plant)
        manager.execute(SetParentBedCommand(scene, plant, None, bed.item_id))

        panel = PropertiesPanel(command_manager=manager)
        panel.set_selected_items([plant])
        assert "Bed A" in _label_texts(panel), "Parent Bed name not shown"

        # Rename the bed (a command) while the PLANT stays selected, then run the
        # deferred panel update. The Parent Bed row must show the new name. The
        # ONLY thing that can flip the plant's identity here is the relationship
        # summary key (id/class/object_type/id-sets are all unchanged) — assert
        # it actually flipped so the rebuild can't be masked by an unrelated cause.
        identity_before = panel._compute_identity([plant])
        manager.execute(ChangePropertyCommand(bed, "name", "Bed A", "Bed B", _set_name))
        assert panel._compute_identity([plant]) != identity_before, (
            "related-item rename must change the plant's structural identity"
        )
        panel.set_selected_items([plant])
        labels = _label_texts(panel)
        assert "Bed B" in labels and "Bed A" not in labels, (
            "Parent Bed summary went stale after a related-item rename (#206 P1)"
        )

        # Undo the rename — the summary must revert too.
        manager.undo()
        panel.set_selected_items([plant])
        labels = _label_texts(panel)
        assert "Bed A" in labels and "Bed B" not in labels, (
            "Parent Bed summary went stale after undo of a related-item rename"
        )

    def test_contained_plants_summary_refreshes_on_rename(self, qtbot) -> None:  # noqa: ARG002
        scene = CanvasScene(2000, 2000)
        manager = CommandManager()
        bed = _make_bed("Bed A")
        plant = CircleItem(200, 200, 20, object_type=ObjectType.TREE)
        plant.name = "Apple"
        scene.addItem(bed)
        scene.addItem(plant)
        manager.execute(SetParentBedCommand(scene, plant, None, bed.item_id))

        panel = PropertiesPanel(command_manager=manager)
        panel.set_selected_items([bed])
        assert any("Apple" in t for t in _label_texts(panel)), "child name not listed"

        # Rename the child plant while the BED stays selected.
        manager.execute(ChangePropertyCommand(plant, "name", "Apple", "Pear", _set_name))
        panel.set_selected_items([bed])
        texts = _label_texts(panel)
        assert any("Pear" in t for t in texts) and not any("Apple" in t for t in texts), (
            "Contained Plants summary went stale after a child rename (#206 P1)"
        )


class TestRefreshSkipsFocusedWidget:
    """An in-place refresh must never overwrite a field the user is editing."""

    def test_focused_field_not_stomped(self, qtbot, monkeypatch) -> None:  # noqa: ARG002
        from PyQt6.QtWidgets import QApplication

        panel = PropertiesPanel(command_manager=CommandManager())
        item = RectangleItem(0, 0, 100, 50)
        item.name = "Original"
        panel.set_selected_items([item])
        name_edit = _field_by_label(panel, "Name")
        assert isinstance(name_edit, QLineEdit)

        # Pretend the Name field holds focus, the model changed underneath, and a
        # refresh is requested. The focus guard short-circuits the whole call, so
        # the field the user is typing in is left untouched.
        monkeypatch.setattr(QApplication, "focusWidget", lambda: name_edit)  # type: ignore[attr-defined]
        item.name = "Changed elsewhere"
        name_edit.setText("user typing")
        panel.set_selected_items([item])

        assert name_edit.text() == "user typing", "refresh must not stomp focused field"

    def test_refresher_skips_only_the_focused_widget(self, qtbot, monkeypatch) -> None:  # noqa: ARG002
        """_refresh_field_values skips the focused widget but still refreshes the
        rest — exercised directly to bypass the whole-call focus backstop."""
        from PyQt6.QtWidgets import QApplication

        panel = PropertiesPanel(command_manager=CommandManager())
        item = RectangleItem(0, 0, 100, 50)
        item.name = "Original"
        panel.set_selected_items([item])
        name_edit = _field_by_label(panel, "Name")
        pos_widget = _field_by_label(panel, "Position")
        x_spin = pos_widget.findChildren(QDoubleSpinBox)[0]
        x_before = x_spin.value()

        # Focus the Name field, mutate both name and position, then refresh in
        # place. Name (focused) is preserved; Position (unfocused) updates.
        monkeypatch.setattr(QApplication, "focusWidget", lambda: name_edit)  # type: ignore[attr-defined]
        name_edit.setText("user typing")
        item.setPos(item.pos().x() + 25.0, item.pos().y())
        panel._refresh_field_values()

        assert name_edit.text() == "user typing", "focused Name must be skipped"
        assert x_spin.value() == x_before + 25.0, "unfocused Position must still refresh"
