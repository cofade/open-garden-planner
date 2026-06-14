"""Integration test: 'Find Plants' panel reliably selects plants on the canvas.

Regression cover for issue #212. Exercises the full wiring through the real
``GardenPlannerApp``:

  click a row in the Find Plants list
    -> plant search panel resolves the live item by id and selects it
    -> scene.selectionChanged fires
    -> properties panel updates to show the selected plant

and that clicking a row whose item was deleted does not crash.
"""

# ruff: noqa: ARG002

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import CircleItem


class TestFindPlantsSelection:
    def _add_tree(self, win, name: str, x: float, y: float) -> CircleItem:
        tree = CircleItem(x, y, 50, object_type=ObjectType.TREE)
        tree.name = name
        win.canvas_scene.addItem(tree)
        return tree

    def test_click_selects_plant_and_shows_properties(self, qtbot: object) -> None:
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)  # type: ignore[attr-defined]

        apple = self._add_tree(win, "Apple Tree", 200, 200)
        birch = self._add_tree(win, "Birch Tree", 1000, 1000)

        panel = win.plant_search_panel
        panel.refresh_plant_list()
        assert panel.results_list.count() == 2

        # Click the first row (Apple Tree, alphabetically first).
        panel._on_item_clicked(panel.results_list.item(0))

        # Selection is deferred; wait for it to land on the canvas.
        qtbot.waitUntil(lambda: apple.isSelected())  # type: ignore[attr-defined]
        assert not birch.isSelected()

        # The properties panel must reflect the canvas selection.
        qtbot.waitUntil(  # type: ignore[attr-defined]
            lambda: apple in win.properties_panel._current_items
        )

    def test_click_stale_row_after_delete_does_not_crash(self, qtbot: object) -> None:
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)  # type: ignore[attr-defined]

        apple = self._add_tree(win, "Apple Tree", 200, 200)

        panel = win.plant_search_panel
        panel.refresh_plant_list()
        assert panel.results_list.count() == 1

        stale_row = panel.results_list.item(0)

        # Delete the plant; the row's stored id is now stale.
        win.canvas_scene.removeItem(apple)

        # Clicking the stale row must not raise and must heal the list.
        panel._on_item_clicked(stale_row)
        qtbot.waitUntil(lambda: panel.results_list.count() == 0)  # type: ignore[attr-defined]
