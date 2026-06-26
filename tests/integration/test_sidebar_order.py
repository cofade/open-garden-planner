"""Integration test: sidebar panels appear in the design-spec order.

The Object Gallery moved into the top toolbar; the sidebar's remaining
panels are ordered so selection-related panels (Properties, Plant
Details, Companion, Crop Rotation) sit directly under each other, then
plan tools (Layers, Constraints), then garden state (Pests, Find
Plants, Journal).

Since US-226 (accordion), panels live inside the ``SidebarController`` (not
directly under ``sidebar.layout()``), so canonical order is read from
``controller.panels()`` rather than the layout.
"""

# ruff: noqa: ARG002


class TestSidebarOrder:
    def test_panels_appear_in_target_order(self, qtbot: object) -> None:
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)  # type: ignore[attr-defined]

        # Canonical order is owned by the controller (US-226).
        controller = win._sidebar_controller
        actual_keys = controller.panel_keys()

        expected_keys = [
            "properties",
            "plant_details",
            "companion",
            "crop_rotation",
            "layers",
            "constraints",
            "pest_overview",
            "plant_search",
            "journal",
            "smart_symbols",
        ]
        assert actual_keys == expected_keys, (
            f"sidebar order mismatch:\n  expected={expected_keys}\n  actual  ={actual_keys}"
        )

        # The visible layout order must match the canonical order too (the
        # panels are never reparented, so opening one cannot reorder the list).
        layout = controller._layout
        visible_order = sorted(
            controller.panels(), key=lambda p: layout.indexOf(p)
        )
        assert visible_order == controller.panels()
