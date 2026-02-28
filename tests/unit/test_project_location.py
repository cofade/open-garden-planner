"""Tests for US-8.1: GPS location & climate zone data model."""

import pytest

from open_garden_planner.core.project import FILE_VERSION, ProjectData, ProjectManager


class TestProjectDataLocation:
    """Tests for location field in ProjectData."""

    def test_default_location_is_none(self) -> None:
        """ProjectData has no location by default."""
        data = ProjectData()
        assert data.location is None

    def test_to_dict_omits_location_when_none(self) -> None:
        """to_dict() does not include 'location' key when location is None."""
        data = ProjectData()
        result = data.to_dict()
        assert "location" not in result

    def test_to_dict_includes_location_when_set(self) -> None:
        """to_dict() includes 'location' key when location is set."""
        loc = {"latitude": 51.5, "longitude": 10.2}
        data = ProjectData(location=loc)
        result = data.to_dict()
        assert result["location"] == loc

    def test_to_dict_includes_frost_dates(self) -> None:
        """to_dict() serializes frost dates nested in location."""
        loc = {
            "latitude": 48.0,
            "longitude": 11.5,
            "frost_dates": {
                "last_spring_frost": "04-15",
                "first_fall_frost": "10-20",
                "hardiness_zone": "7b",
            },
        }
        data = ProjectData(location=loc)
        result = data.to_dict()
        assert result["location"]["frost_dates"]["hardiness_zone"] == "7b"

    def test_from_dict_loads_location(self) -> None:
        """from_dict() restores location from dict."""
        raw = {
            "version": FILE_VERSION,
            "canvas": {"width": 5000.0, "height": 3000.0},
            "layers": [],
            "objects": [],
            "location": {
                "latitude": 53.5,
                "longitude": 9.9,
                "frost_dates": {
                    "last_spring_frost": "04-01",
                    "first_fall_frost": "11-01",
                    "hardiness_zone": "8a",
                },
            },
        }
        data = ProjectData.from_dict(raw)
        assert data.location is not None
        assert data.location["latitude"] == 53.5
        assert data.location["longitude"] == 9.9
        assert data.location["frost_dates"]["hardiness_zone"] == "8a"

    def test_from_dict_no_location_gives_none(self) -> None:
        """from_dict() gives None location when key absent."""
        raw = {
            "version": FILE_VERSION,
            "canvas": {"width": 5000.0, "height": 3000.0},
            "layers": [],
            "objects": [],
        }
        data = ProjectData.from_dict(raw)
        assert data.location is None

    def test_file_version_is_1_2(self) -> None:
        """FILE_VERSION has been bumped to 1.2."""
        assert FILE_VERSION == "1.2"

    def test_roundtrip(self) -> None:
        """Location survives to_dict / from_dict roundtrip."""
        loc = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "elevation_m": 10.0,
            "frost_dates": {
                "last_spring_frost": "04-05",
                "first_fall_frost": "11-15",
                "hardiness_zone": "7b",
            },
        }
        data = ProjectData(location=loc)
        restored = ProjectData.from_dict(data.to_dict())
        assert restored.location == loc


class TestProjectManagerLocation:
    """Tests for location management on ProjectManager."""

    def test_initial_location_is_none(self, qtbot) -> None:
        """ProjectManager starts with no location."""
        pm = ProjectManager()
        assert pm.location is None

    def test_set_location(self, qtbot) -> None:
        """set_location() stores location and marks dirty."""
        pm = ProjectManager()
        loc = {"latitude": 51.5, "longitude": 10.0}
        pm.set_location(loc)
        assert pm.location == loc
        assert pm.is_dirty

    def test_set_location_emits_signal(self, qtbot) -> None:
        """set_location() emits location_changed signal."""
        pm = ProjectManager()
        received = []
        pm.location_changed.connect(received.append)
        loc = {"latitude": 51.5, "longitude": 10.0}
        pm.set_location(loc)
        assert len(received) == 1
        assert received[0] == loc

    def test_new_project_clears_location(self, qtbot) -> None:
        """new_project() resets location to None."""
        pm = ProjectManager()
        pm.set_location({"latitude": 51.5, "longitude": 10.0})
        pm.new_project()
        assert pm.location is None

    def test_new_project_emits_location_changed(self, qtbot) -> None:
        """new_project() emits location_changed with None."""
        pm = ProjectManager()
        pm.set_location({"latitude": 51.5, "longitude": 10.0})
        received = []
        pm.location_changed.connect(received.append)
        pm.new_project()
        assert None in received

    def test_set_location_none_clears(self, qtbot) -> None:
        """set_location(None) clears the location."""
        pm = ProjectManager()
        pm.set_location({"latitude": 51.5, "longitude": 10.0})
        pm.set_location(None)
        assert pm.location is None
