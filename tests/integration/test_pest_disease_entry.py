"""Integration tests for US-12.7 — pest & disease log data model, persistence, undo.

Covers:
  * PestDiseaseRecord / PestDiseaseLog round-trip serialisation
  * Service add / update / delete / get_active_issues
  * AddPestDiseaseCommand / EditPestDiseaseCommand / DeletePestDiseaseCommand
    undo & redo behaviour
  * .ogp file_version 1.4 round-trip with pest_disease_logs preserved
  * Backward-compat: v1.3 (soil-only) file loads with empty pest_disease_logs
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_garden_planner.core import CommandManager, ProjectManager
from open_garden_planner.core.commands import (
    AddPestDiseaseCommand,
    DeletePestDiseaseCommand,
    EditPestDiseaseCommand,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.pest_disease import (
    PestDiseaseLog,
    PestDiseaseRecord,
)
from open_garden_planner.services.pest_disease_service import PestDiseaseService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture()
def scene(qtbot: object) -> CanvasScene:  # noqa: ARG001 — Qt init required
    return CanvasScene(width_cm=1000, height_cm=800)


@pytest.fixture()
def project_manager(qtbot: object) -> ProjectManager:  # noqa: ARG001
    return ProjectManager()


def _make_bed() -> RectangleItem:
    return RectangleItem(100, 100, 200, 150, object_type=ObjectType.GARDEN_BED)


# ---------------------------------------------------------------------------
# Data model: serialisation round-trip
# ---------------------------------------------------------------------------


class TestPestDiseaseRecord:
    def test_round_trip_with_all_fields(self) -> None:
        rec = PestDiseaseRecord(
            date="2026-05-04",
            kind="pest",
            name="Aphid",
            severity="medium",
            treatment="Neem oil weekly",
            resolved_date=None,
            photo_base64="dummy_b64",
            notes="lots of leaves",
        )
        round = PestDiseaseRecord.from_dict(rec.to_dict())
        assert round.date == "2026-05-04"
        assert round.kind == "pest"
        assert round.name == "Aphid"
        assert round.severity == "medium"
        assert round.treatment == "Neem oil weekly"
        assert round.resolved_date is None
        assert round.photo_base64 == "dummy_b64"
        assert round.notes == "lots of leaves"
        assert round.id == rec.id

    def test_optionals_omitted_in_dict(self) -> None:
        rec = PestDiseaseRecord(date="2026-05-04", name="Aphid")
        d = rec.to_dict()
        assert "treatment" not in d
        assert "resolved_date" not in d
        assert "photo_base64" not in d
        assert "notes" not in d
        assert d["date"] == "2026-05-04"
        assert d["kind"] == "pest"
        assert d["severity"] == "low"
        assert "id" in d

    def test_unknown_kind_falls_back_to_pest(self) -> None:
        rec = PestDiseaseRecord.from_dict(
            {"date": "2026-05-04", "kind": "monster", "name": "X", "severity": "low"}
        )
        assert rec.kind == "pest"

    def test_unknown_severity_falls_back_to_low(self) -> None:
        rec = PestDiseaseRecord.from_dict(
            {"date": "2026-05-04", "kind": "pest", "name": "X", "severity": "extreme"}
        )
        assert rec.severity == "low"

    def test_is_active_is_true_when_resolved_date_is_none(self) -> None:
        assert PestDiseaseRecord(name="A").is_active is True
        assert PestDiseaseRecord(name="A", resolved_date="2026-05-10").is_active is False


class TestPestDiseaseLog:
    def test_active_filters_out_resolved_and_sorts_newest_first(self) -> None:
        log = PestDiseaseLog(target_id="t1")
        log.records.append(
            PestDiseaseRecord(date="2026-04-01", name="old", resolved_date="2026-04-15")
        )
        log.records.append(PestDiseaseRecord(date="2026-05-01", name="newer"))
        log.records.append(PestDiseaseRecord(date="2026-05-10", name="newest"))
        active_names = [r.name for r in log.active]
        assert active_names == ["newest", "newer"]

    def test_round_trip_preserves_records_order(self) -> None:
        log = PestDiseaseLog(
            target_id="t1",
            records=[
                PestDiseaseRecord(date="2026-04-01", name="A"),
                PestDiseaseRecord(date="2026-05-01", name="B"),
            ],
        )
        round = PestDiseaseLog.from_dict(log.to_dict())
        assert [r.name for r in round.records] == ["A", "B"]
        assert round.target_id == "t1"


# ---------------------------------------------------------------------------
# Service: add / update / delete / get_active_issues
# ---------------------------------------------------------------------------


class TestPestDiseaseService:
    def test_add_record_persists_to_project_manager(
        self, project_manager: ProjectManager
    ) -> None:
        svc = PestDiseaseService(project_manager)
        svc.add_record("bed-1", PestDiseaseRecord(date="2026-05-04", name="Aphid"))
        assert "bed-1" in project_manager.pest_disease_logs
        records = project_manager.pest_disease_logs["bed-1"]["records"]
        assert records[-1]["name"] == "Aphid"
        assert project_manager.is_dirty

    def test_update_record_replaces_in_place(self, project_manager: ProjectManager) -> None:
        svc = PestDiseaseService(project_manager)
        rec = PestDiseaseRecord(date="2026-05-04", name="Aphid", severity="low")
        svc.add_record("bed-1", rec)
        rec.severity = "high"
        svc.update_record("bed-1", rec)
        records = project_manager.pest_disease_logs["bed-1"]["records"]
        assert records[-1]["severity"] == "high"

    def test_delete_record_removes_only_matching_id(
        self, project_manager: ProjectManager
    ) -> None:
        svc = PestDiseaseService(project_manager)
        a = PestDiseaseRecord(date="2026-04-01", name="A")
        b = PestDiseaseRecord(date="2026-05-01", name="B")
        svc.add_record("bed-1", a)
        svc.add_record("bed-1", b)
        svc.delete_record("bed-1", a.id)
        records = project_manager.pest_disease_logs["bed-1"]["records"]
        assert [r["name"] for r in records] == ["B"]

    def test_get_active_issues_collects_across_targets_sorted_by_date(
        self, project_manager: ProjectManager
    ) -> None:
        svc = PestDiseaseService(project_manager)
        svc.add_record("bed-1", PestDiseaseRecord(date="2026-05-01", name="A"))
        svc.add_record(
            "bed-2",
            PestDiseaseRecord(
                date="2026-04-01", name="B-resolved", resolved_date="2026-04-10"
            ),
        )
        svc.add_record("bed-2", PestDiseaseRecord(date="2026-05-10", name="C"))

        active = svc.get_active_issues()
        names_in_order = [r.name for _, r in active]
        # newest first; resolved excluded
        assert names_in_order == ["C", "A"]


# ---------------------------------------------------------------------------
# Undo / redo via the three commands
# ---------------------------------------------------------------------------


class TestAddPestDiseaseCommand:
    def test_execute_then_undo_when_no_prior_log_removes_key(
        self, project_manager: ProjectManager, qtbot: object  # noqa: ARG002
    ) -> None:
        cm = CommandManager()
        rec = PestDiseaseRecord(date="2026-05-04", name="Aphid")
        cm.execute(AddPestDiseaseCommand(project_manager, "bed-1", rec))
        assert "bed-1" in project_manager.pest_disease_logs

        cm.undo()
        assert "bed-1" not in project_manager.pest_disease_logs

        cm.redo()
        assert "bed-1" in project_manager.pest_disease_logs
        assert (
            project_manager.pest_disease_logs["bed-1"]["records"][-1]["name"]
            == "Aphid"
        )

    def test_undo_with_prior_log_restores_only_prior(
        self, project_manager: ProjectManager, qtbot: object  # noqa: ARG002
    ) -> None:
        svc = PestDiseaseService(project_manager)
        svc.add_record("bed-1", PestDiseaseRecord(date="2026-04-01", name="A"))
        project_manager.mark_clean()

        cm = CommandManager()
        cm.execute(
            AddPestDiseaseCommand(
                project_manager, "bed-1", PestDiseaseRecord(date="2026-05-01", name="B")
            )
        )
        records = project_manager.pest_disease_logs["bed-1"]["records"]
        assert len(records) == 2

        cm.undo()
        records = project_manager.pest_disease_logs["bed-1"]["records"]
        assert len(records) == 1
        assert records[0]["name"] == "A"


class TestEditAndDeletePestDiseaseCommand:
    def test_edit_command_replaces_record_and_undo_restores(
        self, project_manager: ProjectManager, qtbot: object  # noqa: ARG002
    ) -> None:
        svc = PestDiseaseService(project_manager)
        rec = PestDiseaseRecord(date="2026-05-04", name="Aphid", severity="low")
        svc.add_record("bed-1", rec)
        project_manager.mark_clean()

        cm = CommandManager()
        edited = PestDiseaseRecord(
            id=rec.id, date=rec.date, name="Aphid", severity="high"
        )
        cm.execute(EditPestDiseaseCommand(project_manager, "bed-1", edited))
        assert (
            project_manager.pest_disease_logs["bed-1"]["records"][-1]["severity"]
            == "high"
        )

        cm.undo()
        assert (
            project_manager.pest_disease_logs["bed-1"]["records"][-1]["severity"]
            == "low"
        )

    def test_delete_command_removes_record_and_undo_restores(
        self, project_manager: ProjectManager, qtbot: object  # noqa: ARG002
    ) -> None:
        svc = PestDiseaseService(project_manager)
        rec = PestDiseaseRecord(date="2026-05-04", name="Aphid")
        svc.add_record("bed-1", rec)
        project_manager.mark_clean()

        cm = CommandManager()
        cm.execute(DeletePestDiseaseCommand(project_manager, "bed-1", rec.id))
        records = project_manager.pest_disease_logs["bed-1"]["records"]
        assert records == []

        cm.undo()
        records = project_manager.pest_disease_logs["bed-1"]["records"]
        assert len(records) == 1
        assert records[0]["name"] == "Aphid"


# ---------------------------------------------------------------------------
# Round-trip through .ogp save/load (FILE_VERSION 1.4)
# ---------------------------------------------------------------------------


class TestOgpRoundTrip:
    def test_save_then_load_preserves_pest_disease_logs(
        self,
        scene: CanvasScene,
        qtbot: object,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        bed = _make_bed()
        scene.addItem(bed)
        bed_id = str(bed.item_id)

        pm = ProjectManager()
        svc = PestDiseaseService(pm)
        svc.add_record(
            bed_id,
            PestDiseaseRecord(
                date="2026-05-04",
                kind="disease",
                name="Powdery mildew",
                severity="medium",
                treatment="Milk spray",
                photo_base64="abc==",
            ),
        )

        ogp_path = tmp_path / "round_trip.ogp"
        pm.save(scene, ogp_path)

        pm2 = ProjectManager()
        scene2 = CanvasScene(width_cm=1000, height_cm=800)
        pm2.load(scene2, ogp_path)

        assert bed_id in pm2.pest_disease_logs
        rec = pm2.pest_disease_logs[bed_id]["records"][-1]
        assert rec["kind"] == "disease"
        assert rec["name"] == "Powdery mildew"
        assert rec["severity"] == "medium"
        assert rec["treatment"] == "Milk spray"
        assert rec["photo_base64"] == "abc=="

    def test_load_v13_file_has_empty_pest_disease_logs(
        self,
        scene: CanvasScene,
        qtbot: object,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """A v1.3 file (no pest_disease_logs key) loads with an empty dict."""
        legacy = {
            "version": "1.3",
            "metadata": {"modified": "2026-01-01T00:00:00+00:00"},
            "canvas": {"width": 1000.0, "height": 800.0},
            "layers": [],
            "objects": [],
            # soil_tests omitted intentionally — no soil either
        }
        path = tmp_path / "legacy_v13.ogp"
        path.write_text(json.dumps(legacy), encoding="utf-8")

        pm = ProjectManager()
        pm.load(scene, path)
        assert pm.pest_disease_logs == {}
