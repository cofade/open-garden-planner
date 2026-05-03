"""Integration tests for US-12.10a — soil test data model, entry, persistence.

Covers:
  * Adding a record via SoilTestDialog → AddSoilTestCommand → ProjectManager
  * Round-trip through .ogp save/load
  * Undo restores prior state
  * Effective-record hierarchy: bed → global default
"""
from __future__ import annotations

from pathlib import Path

import pytest

from open_garden_planner.core import AddSoilTestCommand, CommandManager, ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services.soil_service import GLOBAL_TARGET_ID, SoilService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001 — Qt init required
    return CanvasScene(width_cm=1000, height_cm=800)


@pytest.fixture()
def project_manager(qtbot: object) -> ProjectManager:  # noqa: ARG001
    return ProjectManager()


def _make_bed() -> RectangleItem:
    """Make a rectangular bed with a known area."""
    bed = RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)
    return bed


# ---------------------------------------------------------------------------
# Data model: serialisation round-trip
# ---------------------------------------------------------------------------

class TestSoilTestRecord:
    def test_round_trip_with_all_fields_set(self) -> None:
        rec = SoilTestRecord(
            date="2026-04-25",
            ph=6.2,
            n_level=1, p_level=2, k_level=3,
            ca_level=1, mg_level=2, s_level=0,
            n_ppm=15.0, p_ppm=8.5,
            notes="rich loam",
        )
        round = SoilTestRecord.from_dict(rec.to_dict())
        assert round.date == "2026-04-25"
        assert round.ph == 6.2
        assert round.n_level == 1
        assert round.k_level == 3
        assert round.s_level == 0
        assert round.n_ppm == 15.0
        assert round.p_ppm == 8.5
        assert round.notes == "rich loam"
        assert round.id == rec.id

    def test_optionals_omitted_in_dict(self) -> None:
        rec = SoilTestRecord(date="2026-01-01")
        d = rec.to_dict()
        assert "ph" not in d
        assert "n_level" not in d
        assert "n_ppm" not in d
        assert "notes" not in d
        # but id and date must always be present
        assert d["date"] == "2026-01-01"
        assert "id" in d


# ---------------------------------------------------------------------------
# Service hierarchy: bed → global → None
# ---------------------------------------------------------------------------

class TestSoilServiceHierarchy:
    def test_no_records_returns_none(self, project_manager: ProjectManager) -> None:
        svc = SoilService(project_manager)
        assert svc.get_effective_record("bed-uuid-1") is None

    def test_bed_record_takes_precedence_over_global(
        self, project_manager: ProjectManager
    ) -> None:
        svc = SoilService(project_manager)
        svc.add_record(GLOBAL_TARGET_ID, SoilTestRecord(date="2026-01-01", ph=7.0))
        svc.add_record("bed-1", SoilTestRecord(date="2026-04-01", ph=5.5))

        eff = svc.get_effective_record("bed-1")
        assert eff is not None
        assert eff.ph == 5.5

    def test_falls_back_to_global_when_bed_has_no_record(
        self, project_manager: ProjectManager
    ) -> None:
        svc = SoilService(project_manager)
        svc.add_record(GLOBAL_TARGET_ID, SoilTestRecord(date="2026-01-01", ph=7.0))

        eff = svc.get_effective_record("bed-without-record")
        assert eff is not None
        assert eff.ph == 7.0

    def test_latest_record_wins_within_target(
        self, project_manager: ProjectManager
    ) -> None:
        svc = SoilService(project_manager)
        svc.add_record("bed-1", SoilTestRecord(date="2025-04-01", ph=5.0))
        svc.add_record("bed-1", SoilTestRecord(date="2026-04-01", ph=6.5))

        eff = svc.get_effective_record("bed-1")
        assert eff is not None
        assert eff.ph == 6.5  # newer date wins


# ---------------------------------------------------------------------------
# Undo / redo via AddSoilTestCommand
# ---------------------------------------------------------------------------

class TestAddSoilTestCommand:
    def test_execute_then_undo_restores_empty(
        self, project_manager: ProjectManager, qtbot: object  # noqa: ARG002
    ) -> None:
        cm = CommandManager()
        record = SoilTestRecord(date="2026-04-25", ph=6.2, n_level=1, p_level=1, k_level=1)
        cmd = AddSoilTestCommand(project_manager, "bed-1", record)
        cm.execute(cmd)

        assert "bed-1" in project_manager.soil_tests
        assert project_manager.soil_tests["bed-1"]["records"][-1]["ph"] == 6.2
        assert project_manager.is_dirty

        cm.undo()
        # Prior state had no record → key is removed entirely
        assert "bed-1" not in project_manager.soil_tests

        cm.redo()
        assert project_manager.soil_tests["bed-1"]["records"][-1]["ph"] == 6.2

    def test_undo_when_prior_record_existed_restores_just_prior(
        self, project_manager: ProjectManager, qtbot: object  # noqa: ARG002
    ) -> None:
        # Seed a prior record
        first = SoilTestRecord(date="2025-04-25", ph=5.5)
        SoilService(project_manager).add_record("bed-1", first)
        project_manager.mark_clean()

        # Add a second record via undoable command
        cm = CommandManager()
        second = SoilTestRecord(date="2026-04-25", ph=6.5)
        cm.execute(AddSoilTestCommand(project_manager, "bed-1", second))

        records = project_manager.soil_tests["bed-1"]["records"]
        assert len(records) == 2

        cm.undo()
        records = project_manager.soil_tests["bed-1"]["records"]
        assert len(records) == 1
        assert records[0]["ph"] == 5.5  # original survives


# ---------------------------------------------------------------------------
# Round-trip through .ogp save / load
# ---------------------------------------------------------------------------

class TestOgpRoundTrip:
    def test_save_then_load_preserves_soil_tests(
        self,
        scene: CanvasScene,
        qtbot: object,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        bed = _make_bed()
        scene.addItem(bed)
        bed_id = str(bed.item_id)

        pm = ProjectManager()
        # Seed both a per-bed and a global record
        svc = SoilService(pm)
        svc.add_record(
            bed_id,
            SoilTestRecord(
                date="2026-04-25",
                ph=6.2,
                n_level=1, p_level=2, k_level=3,
                notes="loamy",
            ),
        )
        svc.add_record(
            GLOBAL_TARGET_ID,
            SoilTestRecord(date="2026-01-01", ph=7.0, n_level=2),
        )

        ogp_path = tmp_path / "round_trip.ogp"
        pm.save(scene, ogp_path)

        # Re-load into a fresh manager + scene
        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2.load(scene2, ogp_path)

        assert bed_id in pm2.soil_tests
        bed_records = pm2.soil_tests[bed_id]["records"]
        assert bed_records[-1]["ph"] == 6.2
        assert bed_records[-1]["n_level"] == 1
        assert bed_records[-1]["k_level"] == 3
        assert bed_records[-1]["notes"] == "loamy"

        assert GLOBAL_TARGET_ID in pm2.soil_tests
        assert pm2.soil_tests[GLOBAL_TARGET_ID]["records"][-1]["ph"] == 7.0

    def test_load_pre_v13_file_has_empty_soil_tests(
        self,
        scene: CanvasScene,
        qtbot: object,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """A v1.2 file (no soil_tests key) loads with an empty soil_tests dict."""
        import json

        legacy = {
            "version": "1.2",
            "metadata": {"modified": "2025-01-01T00:00:00+00:00"},
            "canvas": {"width": 1000.0, "height": 800.0},
            "layers": [],
            "objects": [],
        }
        path = tmp_path / "legacy.ogp"
        path.write_text(json.dumps(legacy), encoding="utf-8")

        pm = ProjectManager()
        pm.load(scene, path)
        assert pm.soil_tests == {}
