"""Integration test: sidebar panels appear in the design-spec order.

The Object Gallery moved into the top toolbar; the sidebar's remaining
panels are reordered so selection-related panels (Properties, Plant
Details, Companion, Crop Rotation) sit directly under each other, then
plan tools (Layers, Constraints), then garden state (Pests, Find
Plants, Journal).
"""

# ruff: noqa: ARG002


class TestSidebarOrder:
    def test_panels_appear_in_target_order(self, qtbot: object) -> None:
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)  # type: ignore[attr-defined]

        layout = win.sidebar.layout()
        # Filter to widget items only (skip the trailing addStretch spacer).
        order = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                order.append(w)

        # Maps target index → tracked-panel key (matches application.py).
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
        ]
        # Build inverse map: panel widget → key.
        key_by_widget = {w: k for k, w in win._tracked_panels.items()}
        actual_keys = [key_by_widget.get(w, type(w).__name__) for w in order]

        assert actual_keys == expected_keys, (
            f"sidebar order mismatch:\n  expected={expected_keys}\n  actual  ={actual_keys}"
        )
