"""Integration tests for the CategoryToolbar (object dropdowns + global search).

The CategoryToolbar sits to the right of MainToolbar (core tools) and
ConstraintToolbar (CAD constraints). It holds:
  - 11 category icon-buttons, each opens a dropdown of placeable objects
  - a global search field that searches across every gallery item
"""


import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.i18n import load_translator
from open_garden_planner.core.tools import ToolType
from open_garden_planner.services.bundled_species_db import lookup_species
from open_garden_planner.ui.theme import ThemeMode, generate_stylesheet
from open_garden_planner.ui.widgets.category_dropdown import CategoryDropdown
from open_garden_planner.ui.widgets.category_toolbar import CategoryToolbar
from open_garden_planner.ui.widgets.gallery_data import build_toolbar_categories
from open_garden_planner.ui.widgets.global_search import GlobalSearchField


@pytest.fixture
def themed_gallery(qapp):
    original = qapp.styleSheet()
    qapp.setStyleSheet(generate_stylesheet(ThemeMode.LIGHT))
    yield
    qapp.setStyleSheet(original)


def test_constructing_the_toolbar_does_not_show_a_detached_scroll_area(qtbot, qapp) -> None:
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtWidgets import QScrollArea

    shown = []

    class Watch(QObject):
        def eventFilter(self, watched, event):
            if (
                event.type() == QEvent.Type.Show
                and isinstance(watched, QScrollArea)
                and watched.isWindow()
            ):
                shown.append(watched)
            return False

    watch = Watch()
    qapp.installEventFilter(watch)
    try:
        qtbot.addWidget(CategoryToolbar())
    finally:
        qapp.removeEventFilter(watch)

    assert shown == []


class TestCategoryToolbarStructure:
    """Static structure: categories, icons, and search field are all wired up."""

    def test_toolbar_has_11_categories_and_search(self, qtbot: object) -> None:
        tb = CategoryToolbar()
        qtbot.addWidget(tb)  # type: ignore[attr-defined]
        assert len(tb._category_buttons) == 11
        assert len(tb._category_dropdowns) == 11
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

    def test_german_flower_search_selects_distinct_species(self, qtbot, qapp) -> None:
        assert load_translator(qapp, "de")
        try:
            toolbar = CategoryToolbar()
            qtbot.addWidget(toolbar)
            toolbar.show()
            index = next(i for i, category in enumerate(toolbar._categories)
                         if category.icon_name == "flower")
            anchor = toolbar._category_buttons[index]
            dropdown = toolbar._category_dropdowns[index]
            for name, scientific in (("Ringelblume", "Calendula officinalis"),
                                     ("Studentenblume", "Tagetes erecta"),
                                     ("Geranie", "Pelargonium x hortorum")):
                qtbot.mouseClick(anchor, Qt.MouseButton.LeftButton)
                dropdown._search_box.setText(name)
                matches = [button for button in dropdown._buttons if button.isVisible()]
                assert [button.item.name for button in matches] == [name]
                [button] = matches
                assert button.item.thumbnail is not None
                with qtbot.waitSignal(toolbar.item_selected) as selected:
                    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
                record = lookup_species(selected.args[0].species)
                assert record is not None and record["scientific_name"] == scientific
        finally:
            load_translator(qapp, "en")

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

    @pytest.mark.parametrize("dimensions", ((800, 800), (400, 360), (267, 260)))
    def test_vegetable_popup_stays_on_screen_and_places_filtered_item(
        self, qtbot, themed_gallery, monkeypatch, dimensions
    ) -> None:
        tb = CategoryToolbar()
        qtbot.addWidget(tb)
        tb.show()
        index = next(i for i, category in enumerate(tb._categories)
                     if category.icon_name == "vegetable")
        anchor = tb._category_buttons[index]
        dropdown = tb._category_dropdowns[index]
        work_area = QRect(0, 0, *dimensions)
        monkeypatch.setattr(anchor.screen(), "availableGeometry", lambda: work_area)
        tb.move(work_area.topLeft() + QPoint(0, work_area.height() // 3))
        qtbot.mouseClick(anchor, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert work_area.contains(dropdown.frameGeometry())
        assert dropdown._results.viewport().height() >= dropdown._buttons[0].height()
        assert dropdown._results.verticalScrollBar().maximum() > 0
        dropdown._results.verticalScrollBar().setValue(
            dropdown._results.verticalScrollBar().maximum()
        )

        dropdown._search_box.setText("Carrot")
        QApplication.processEvents()
        [carrot] = [button for button in dropdown._buttons if button.isVisible()]
        viewport = dropdown._results.viewport()
        assert viewport.rect().contains(carrot.mapTo(viewport, carrot.rect().center()))
        assert dropdown._grid.getItemPosition(dropdown._grid.indexOf(carrot))[:2] == (0, 0)

        dropdown.trait_filters.layer_buttons["vine"].click()
        assert all(button.isHidden() for button in dropdown._buttons)
        dropdown.close()
        qtbot.mouseClick(anchor, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert not dropdown.trait_filters.layers
        assert dropdown._search_box.text() == ""
        assert carrot.isVisible()
        assert dropdown._results.verticalScrollBar().value() == 0

        dropdown._search_box.setText("Carrot")
        with qtbot.waitSignal(tb.item_selected) as signal:
            qtbot.mouseClick(carrot, Qt.MouseButton.LeftButton)
        assert signal.args[0].species == carrot.item.species
        assert not dropdown.isVisible()


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
        )
        from open_garden_planner.ui.widgets import (
            ConstraintToolbar as ConT,
        )
        from open_garden_planner.ui.widgets import (
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

    def test_global_search_shortcut_is_ctrl_f(self, qtbot: object) -> None:
        from PyQt6.QtWidgets import QApplication

        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)  # type: ignore[attr-defined]
        try:
            win.showNormal()
            win.resize(1800, 1000)
            QApplication.processEvents()

            # Verify Find & Replace action is Ctrl+H to avoid ambiguous overload with Ctrl+F
            assert win._find_replace_action.shortcut().toString() == "Ctrl+H"

            # Verify CategoryToolbar has Ctrl+F shortcut
            assert win.category_toolbar._focus_shortcut is not None
            assert win.category_toolbar._focus_shortcut.key().toString() == "Ctrl+F"

            # Activating the shortcut focuses the global search field
            win.category_toolbar._focus_shortcut.activated.emit()
            QApplication.processEvents()
            assert win.focusWidget() is win.category_toolbar._search_field
        finally:
            win.close()

    def test_no_duplicate_window_shortcuts(self, qtbot: object) -> None:
        from PyQt6.QtGui import QAction, QShortcut

        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)  # type: ignore[attr-defined]
        try:
            seen_shortcuts: dict[str, list[str]] = {}
            for action in win.findChildren(QAction):
                sc = action.shortcut().toString()
                if sc:
                    seen_shortcuts.setdefault(sc, []).append(f"QAction({action.text()})")
            for shortcut in win.findChildren(QShortcut):
                sc = shortcut.key().toString()
                if sc:
                    seen_shortcuts.setdefault(sc, []).append("QShortcut")

            duplicates = {k: v for k, v in seen_shortcuts.items() if len(v) > 1}
            assert duplicates == {}, f"Found duplicate shortcut registrations: {duplicates}"
        finally:
            win.close()
