"""A9 measurements use real production workflows, including repeated document opens."""

from scripts.benchmark_audit_performance import measure

from open_garden_planner.app.application import GardenPlannerApp


def test_driver_uses_the_application_open_path_and_real_pngs(qtbot, monkeypatch):
    opened = []
    original = GardenPlannerApp._load_project_file
    def load(window, path):
        opened.append(path)
        return original(window, path)
    monkeypatch.setattr(GardenPlannerApp, "_load_project_file", load)
    report = measure(rounds=2, idle_seconds=0.05)
    assert len(opened) == 2
    assert all(path.endswith("audit-2026-10-plan_500.ogp") for path in opened)
    assert len(report["load"]["samples_ms"]) == 2
    assert len(report["save"]["samples_ms"]) == 2
    assert report["png_300dpi_width42cm"]["pixels"] == [4960, 2976]
    assert len(report["png_300dpi_width42cm"]["samples_ms"]) == 2
    assert report["idle"]["scene_changed"] == 0
    assert report["idle"]["minimap_renders"] == 0
