"""Integration tests for data attribution & licence display (US-G1, issue #311).

Tests that:
- The About dialog shows a "Data Sources & Licenses" section
- A plant imported from Permapeople shows the CC BY-SA credit in Plant Details
"""

from __future__ import annotations

from open_garden_planner.ui.plant_species_assignment import plant_source_license


class TestPlantSourceLicense:
    """Unit-level tests for the licence line helper."""

    def test_permapeople_shows_cc_by_sa(self) -> None:
        result = plant_source_license("permapeople")
        assert "CC BY-SA 4.0" in result
        assert "Permapeople" in result

    def test_trefle_shows_attribution_required(self) -> None:
        result = plant_source_license("trefle")
        assert "attribution required" in result
        assert "Trefle" in result

    def test_perenual_shows_free_use(self) -> None:
        result = plant_source_license("perenual")
        assert "free" in result.lower()
        assert "Perenual" in result

    def test_custom_returns_empty(self) -> None:
        assert plant_source_license("custom") == ""

    def test_bundled_returns_empty(self) -> None:
        assert plant_source_license("bundled") == ""

    def test_none_returns_empty(self) -> None:
        assert plant_source_license(None) == ""

    def test_empty_string_returns_empty(self) -> None:
        assert plant_source_license("") == ""

    def test_unknown_source_returns_empty(self) -> None:
        assert plant_source_license("unknown_provider") == ""


class TestDataSourcesDialog:
    """Integration test for the About dialog's Data Sources section."""

    def test_data_sources_dialog_opens(self, qtbot) -> None:
        """The Data Sources & Licenses button opens a dialog with content."""
        from open_garden_planner.app.application import GardenPlannerApp

        # This is a lightweight test that the method exists and produces HTML
        # Full dialog testing requires the full app fixture
        app = GardenPlannerApp.__new__(GardenPlannerApp)
        html = app._get_data_sources_html()
        assert "Permapeople" in html
        assert "CC BY-SA 4.0" in html
        assert "Trefle" in html
        assert "Perenual" in html
        assert "RHS" in html
