"""Integration tests for the CategoryToolbar (object dropdowns + global search).

The CategoryToolbar sits to the right of MainToolbar (core tools) and
ConstraintToolbar (CAD constraints). It holds:
  - 10 category icon-buttons, each opens a dropdown of placeable objects
  - a global search field that searches across every gallery item
"""

# ruff: noqa: ARG002

import pytest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.widgets.category_dropdown import CategoryDropdown
from open_garden_planner.ui.widgets.category_toolbar import CategoryToolbar
from open_garden_planner.ui.widgets.gallery_data import build_toolbar_categories
from open_garden_planner.ui.widgets.global_search import GlobalSearchField


class TestCategoryToolbarStructure:
    """Static structure: categories, icons, and search field are all wired up."""

    def test_toolbar_has_10_categories_and_search(self, qtbot: object) -> None:
        tb = CategoryToolbar()
        qtbot.addWidget(tb)  # type: ignore[attr-defined]
        assert len(tb._category_buttons) == 10
        assert len(tb._category_dropdowns) == 10
        assert tb._search_field is not None

    def test_first_category_is_beds_and_surfaces(self, qtbot: object) -> None:
        """Beds & Surfaces must be first — that's the whole point of the redesign."""
        tb = CategoryToolbar()
        qtbot.addWidget(tb)  # type: ignore[attr-defined]
        first_dropdown = tb._category_dropdowns[0]
        assert first_dropdown._category.name == "Beds & Surfaces"
        item_names = [i.name for i in first_dropdown._category.items]
        assert "Garden Bed" in item_names

    def test_every_category_button_has_icon(self, qtbot: object) -> None:
        """Regression for the bug where category buttons fell back to 2-letter
        text labels because the English→icon map missed translated names."""
        tb = CategoryToolbar()
        qtbot.addWidget(tb)  # type: ignore[attr-defined]
        for btn in tb._category_buttons:
            assert not btn.icon().isNull(), f"missing icon on button {btn.toolTip()!r}"


class TestCategoryDropdownFlow:
    """Clicking a category item activates its tool and emits the toolbar signal."""

    def test_dropdown_click_emits_tool_selected(self, qtbot: object) -> None:
        tb = CategoryToolbar()
        qtbot.addWidget(tb)  # type: ignore[attr-defined]
        received: list[ToolType] = []
        tb.tool_selected.connect(received.append)

        beds_dropdown = tb._category_dropdowns[0]
        garden_bed_btn = next(
            b for b in beds_dropdown._buttons if b.item.name == "Garden Bed"
        )
        garden_bed_btn.click()

        assert received == [ToolType.GARDEN_BED]

    def test_dropdown_click_also_emits_item_selected(self, qtbot: object) -> None:
        tb = CategoryToolbar()
        qtbot.addWidget(tb)  # type: ignore[attr-defined]
        received_items: list = []
        tb.item_selected.connect(received_items.append)

        beds_dropdown = tb._category_dropdowns[0]
        garden_bed_btn = next(
            b for b in beds_dropdown._buttons if b.item.name == "Garden Bed"
        )
        garden_bed_btn.click()

        assert len(received_items) == 1
        assert received_items[0].tool_type == ToolType.GARDEN_BED
        assert received_items[0].name == "Garden Bed"

    def test_dropdown_filter_hides_non_matching(self, qtbot: object) -> None:
        cats = build_toolbar_categories()
        trees = next(c for c in cats if c.name == "Trees")
        dropdown = CategoryDropdown(trees)
        qtbot.addWidget(dropdown)  # type: ignore[attr-defined]

        dropdown._apply_filter("apple")

        # isHidden() reads the local flag — works without the widget being
        # actually shown on screen.
        visible_names = [b.item.name for b in dropdown._buttons if not b.isHidden()]
        hidden_names = [b.item.name for b in dropdown._buttons if b.isHidden()]
        assert "Apple Tree" in visible_names
        assert "Oak" in hidden_names


class TestGlobalSearch:
    """The global search field activates the same flow across all categories."""

    def test_search_finds_garden_bed(self, qtbot: object) -> None:
        cats = build_toolbar_categories()
        field = GlobalSearchField(cats)
        qtbot.addWidget(field)  # type: ignore[attr-defined]

        received_items: list = []
        field.item_selected.connect(received_items.append)

        field.setText("Garden Bed")
        field._popup.activate_current()

        assert len(received_items) == 1
        assert received_items[0].tool_type == ToolType.GARDEN_BED

    def test_search_with_no_hits_hides_popup(self, qtbot: object) -> None:
        cats = build_toolbar_categories()
        field = GlobalSearchField(cats)
        qtbot.addWidget(field)  # type: ignore[attr-defined]

        field.setText("definitelynotaplant")

        assert not field._popup.isVisible()

    def test_search_emptying_clears_popup(self, qtbot: object) -> None:
        cats = build_toolbar_categories()
        field = GlobalSearchField(cats)
        qtbot.addWidget(field)  # type: ignore[attr-defined]

        field.setText("rose")
        field.setText("")

        assert not field._popup.isVisible()

    def test_search_popup_does_not_steal_focus(self, qtbot: object) -> None:
        """Regression for the "only first letter lands in the field" bug.

        Showing the popup must not move keyboard focus away from the field.
        """
        from PyQt6.QtCore import Qt

        cats = build_toolbar_categories()
        field = GlobalSearchField(cats)
        qtbot.addWidget(field)  # type: ignore[attr-defined]
        field.show()
        qtbot.waitExposed(field)  # type: ignore[attr-defined]
        field.setFocus(Qt.FocusReason.OtherFocusReason)

        # Typing a letter shows the popup with hits — caret must stay in the field.
        field.setText("a")
        QApplication.processEvents()

        assert field._popup.isVisible(), "popup should be open while we type"
        assert QApplication.focusWidget() is field, (
            "keyboard focus must stay in the search field "
            f"(actually at {type(QApplication.focusWidget()).__name__})"
        )


class TestGalleryRemoved:
    """The Object Gallery panel must no longer be exported or used in the sidebar."""

    def test_gallery_panel_no_longer_exported(self) -> None:
        import open_garden_planner.ui.panels as panels
        assert not hasattr(panels, "GalleryPanel")

    def test_gallery_panel_module_removed(self) -> None:
        with pytest.raises(ImportError):
            from open_garden_planner.ui.panels import gallery_panel  # noqa: F401


class TestMainWindowToolbarLayout:
    """Top toolbars must appear in this left-to-right order:
    MainToolbar  →  ConstraintToolbar  →  CategoryToolbar.
    """

    def test_three_toolbars_in_expected_order(self, qtbot: object) -> None:
        from PyQt6.QtWidgets import QToolBar

        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.ui.widgets import (
            CategoryToolbar as CT,
            ConstraintToolbar as ConT,
            MainToolbar as MT,
        )

        win = GardenPlannerApp()
        qtbot.addWidget(win)  # type: ignore[attr-defined]

        # Pick our three named toolbars in their addToolBar() / findChildren order.
        named = [
            type(tb)
            for tb in win.findChildren(QToolBar)
            if isinstance(tb, (MT, ConT, CT))
        ]
        assert named == [MT, ConT, CT], f"unexpected toolbar order: {named}"
