"""#774 / #775: the layers list shows whole rows, and a rename cannot shrink one.

#774: the list's fixed height was ``count * 36`` — it ignored the rows' real size
hints (fonts and DPI make a row taller) and the list's frame, so the last row
was clipped and an empty band appeared under it; the highest layer needed a
scroll to be seen.

#775: double-clicking a layer name swaps its QLabel for a QLineEdit, whose size
hint is shorter in some styles, and the row shrank under the editor.
"""

from __future__ import annotations

from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.panels.layers_panel import ROW_HEIGHT, LayerListItem, LayersPanel


def _layers(count: int) -> list[Layer]:
    return [Layer(name=f"Layer {index}") for index in range(count)]


class TestTheListHeight:
    def test_three_layers_are_three_whole_rows_plus_the_frame(self, qtbot: object) -> None:
        panel = LayersPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_layers(_layers(3))
        panel.show()

        rows = [panel.layer_list.sizeHintForRow(i) for i in range(3)]
        row_height = max([ROW_HEIGHT, *rows])
        expected = 3 * row_height + 2 * panel.layer_list.frameWidth()
        assert panel.layer_list.height() == expected
        # no empty band: the viewport holds all three rows exactly
        assert panel.layer_list.viewport().height() >= 3 * row_height

    def test_more_than_five_layers_scroll_at_five_rows(self, qtbot: object) -> None:
        panel = LayersPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_layers(_layers(7))
        panel.show()

        rows = [panel.layer_list.sizeHintForRow(i) for i in range(7)]
        row_height = max([ROW_HEIGHT, *rows])
        expected = 5 * row_height + 2 * panel.layer_list.frameWidth()
        assert panel.layer_list.height() == expected
        assert panel.layer_list.verticalScrollBar().maximum() > 0

    def test_a_long_name_cannot_add_a_horizontal_scrollbar(self, qtbot: object) -> None:
        """An h-scrollbar takes viewport height and would clip the last row (#774)."""
        from PyQt6.QtCore import Qt

        panel = LayersPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_layers([Layer(name="A very long layer name " * 20)])
        panel.show()

        assert panel.layer_list.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        widget = panel.layer_list.itemWidget(panel.layer_list.item(0))
        assert isinstance(widget, LayerListItem)
        assert widget.name_label.toolTip() == widget.layer.name
        rows = [panel.layer_list.sizeHintForRow(i) for i in range(1)]
        row_height = max([ROW_HEIGHT, *rows])
        assert panel.layer_list.height() == row_height + 2 * panel.layer_list.frameWidth()

    def test_a_refresh_uses_the_same_height_in_both_branches(self, qtbot: object) -> None:
        """Growing past five then shrinking back must not leave a stale maximum."""
        panel = LayersPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_layers(_layers(7))
        panel.show()
        panel.set_layers(_layers(2))

        rows = [panel.layer_list.sizeHintForRow(i) for i in range(2)]
        row_height = max([ROW_HEIGHT, *rows])
        assert panel.layer_list.height() == 2 * row_height + 2 * panel.layer_list.frameWidth()


class TestTheRowDoesNotShrink:
    def test_the_inline_editor_keeps_the_row_height(self, qtbot: object) -> None:
        item = LayerListItem(Layer(name="Bed"))
        qtbot.addWidget(item)  # type: ignore[attr-defined]
        item.adjustSize()
        before = item.height()
        assert before >= ROW_HEIGHT

        item._start_editing()
        item.adjustSize()
        assert item.height() >= ROW_HEIGHT
        assert not item.name_edit.isHidden()

    def test_the_row_widget_has_a_minimum_height(self, qtbot: object) -> None:
        item = LayerListItem(Layer(name="Bed"))
        qtbot.addWidget(item)  # type: ignore[attr-defined]
        assert item.minimumHeight() >= ROW_HEIGHT
