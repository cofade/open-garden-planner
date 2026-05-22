"""End-to-end test for the Paper Space layout tab (Phase 13 Package B — US-B7)."""

from __future__ import annotations

import pytest

from open_garden_planner.app.application import GardenPlannerApp


@pytest.fixture()
def window(qtbot) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(1000, 700)
    win.show()
    qtbot.waitExposed(win)
    return win


class TestLayoutTab:
    def test_layout_tab_present(self, window: GardenPlannerApp) -> None:
        # Tab 0 = Garden Plan, 1 = Calendar, 2 = Seeds, 3 = Layout.
        assert window._tab_widget.count() == 4
        assert window._tab_widget.tabText(3) == "Layout"

    def test_layout_tab_lazy_creation(self, window: GardenPlannerApp) -> None:
        """The paper-space scene is not built until the tab is visited."""
        assert window._paper_space_scene is None
        window._tab_widget.setCurrentIndex(3)
        assert window._paper_space_scene is not None
        assert window._paper_space_view is not None

    def test_default_layout_has_three_items(self, window: GardenPlannerApp) -> None:
        window._tab_widget.setCurrentIndex(3)
        items = window._paper_space_scene.items()
        # Viewport + title block + scale bar.
        assert len(items) == 3

    def test_save_without_visiting_layout_tab_preserves_loaded_layout(
        self, window: GardenPlannerApp, tmp_path
    ) -> None:
        """Regression for P0 data-loss bug.

        Scenario: user opens a 1.4 file that has a stored layout,
        edits only the Garden Plan tab, and saves. The Layout tab is
        never built. Without the fix, ``_paper_space_scene`` stays
        ``None``, ``_paper_layouts_for_save()`` returns ``[]``, and
        the loaded layout gets stripped from the file on save.
        """
        from open_garden_planner.ui.paper_space import PaperSpaceScene

        # Step 1: stash a layout on the project manager and save it.
        ps = PaperSpaceScene(window.canvas_scene)
        original_layout = ps.to_dict()
        window._project_manager.set_paper_layouts([original_layout])
        out_path = tmp_path / "with_layout.ogp"
        window._save_to_file(out_path)

        # Step 2: load the file back. Do NOT touch the Layout tab.
        window._project_manager.load(window.canvas_scene, out_path)
        assert window._paper_space_scene is None  # tab never opened
        assert len(window._project_manager.paper_layouts) == 1

        # Step 3: save back to disk. The bug stripped layouts here.
        window._save_to_file(out_path)

        # Step 4: load again and verify the layout survived.
        window._project_manager.load(window.canvas_scene, out_path)
        assert len(window._project_manager.paper_layouts) == 1
        assert window._project_manager.paper_layouts[0]["page_name"] == \
            original_layout["page_name"]

    def test_layout_persists_through_save_reload(
        self, window: GardenPlannerApp, tmp_path
    ) -> None:
        from open_garden_planner.ui.canvas.items import CircleItem

        # Drop a recognisable item on the canvas so we know the source
        # scene actually round-trips along with the layout.
        window.canvas_scene.addItem(CircleItem(500, 500, 100))

        # Visit the layout tab so the paper-space scene is built.
        window._tab_widget.setCurrentIndex(3)
        assert window._paper_space_scene is not None
        page_name_before = window._paper_space_scene.page_name

        # Save the project.
        out_path = tmp_path / "round_trip.ogp"
        window._save_to_file(out_path)
        assert out_path.exists()

        # Load into a fresh window.
        win2 = GardenPlannerApp()
        win2.resize(800, 600)
        win2._project_manager.load(win2.canvas_scene, out_path)
        win2._tab_widget.setCurrentIndex(3)
        assert win2._paper_space_scene is not None
        assert win2._paper_space_scene.page_name == page_name_before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
