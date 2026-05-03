"""Integration tests for US-12.10c — Amendment Calculator.

Covers:
  * Pure ``SoilService.calculate_amendments`` rules (None / zero-area /
    pH formula / NPK formula / priority order).
  * ``AmendmentLoader`` validation on malformed JSON.
  * ``AmendmentPlanDialog`` aggregation by substance + clipboard copy.
  * ``SoilTestDialog`` inline section visibility & live recompute.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.services.amendment_loader import AmendmentLoader
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.dialogs.amendment_plan_dialog import AmendmentPlanDialog
from open_garden_planner.ui.dialogs.soil_test_dialog import SoilTestDialog


# ---------------------------------------------------------------------------
# Pure calculator rules
# ---------------------------------------------------------------------------


class TestCalculatorRules:
    def test_no_record_returns_empty_list(self) -> None:
        assert SoilService.calculate_amendments(None, bed_area_m2=2.0) == []

    def test_zero_area_returns_empty_list(self) -> None:
        record = SoilTestRecord(date="2026-04-01", ph=5.8, n_level=1)
        assert SoilService.calculate_amendments(record, bed_area_m2=0.0) == []

    def test_ph_uses_roadmap_formula(self) -> None:
        """Roadmap §2120-2125 formula: (target - current) / effect * 100 * area."""
        record = SoilTestRecord(
            date="2026-04-01", ph=5.8, n_level=3, p_level=3, k_level=3,
        )
        recs = SoilService.calculate_amendments(
            record, target_ph=6.5, bed_area_m2=2.0
        )
        assert len(recs) == 1
        rec = recs[0]
        assert rec.amendment.id == "dolomite_lime"
        # 0.7 / 0.25 * 100 * 2.0 = 560 g
        assert rec.quantity_g == pytest.approx(560.0, abs=0.5)

    def test_npk_uses_application_rate(self) -> None:
        """N=1, target=3, 3 m², blood_meal at 200 g/m² → (3-1)*200*3 = 1200 g."""
        record = SoilTestRecord(
            date="2026-04-01", ph=6.5, n_level=1, p_level=3, k_level=3,
        )
        recs = SoilService.calculate_amendments(
            record, target_n=3, bed_area_m2=3.0
        )
        n_picks = [r for r in recs if r.target_kind == "n"]
        assert len(n_picks) == 1
        assert n_picks[0].amendment.id == "blood_meal"
        assert n_picks[0].quantity_g == pytest.approx(1200.0, abs=0.5)

    def test_priority_pH_before_NPK(self) -> None:
        """When both pH and N are deficient, pH recommendation is first."""
        record = SoilTestRecord(
            date="2026-04-01", ph=5.8, n_level=1, p_level=3, k_level=3,
        )
        recs = SoilService.calculate_amendments(
            record, target_ph=6.5, target_n=3, bed_area_m2=2.0
        )
        assert len(recs) >= 2
        assert recs[0].target_kind == "ph"
        assert recs[1].target_kind == "n"


# ---------------------------------------------------------------------------
# Loader validation
# ---------------------------------------------------------------------------


class TestAmendmentLoader:
    def test_validates_schema_raises_on_malformed_json(
        self, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad_amendments.json"
        bad.write_text("{ this is not valid json", encoding="utf-8")
        loader = AmendmentLoader(path=bad)
        with pytest.raises(ValueError):
            loader.get_amendments()

    def test_validates_schema_raises_on_missing_substances_key(
        self, tmp_path: Path
    ) -> None:
        wrong = tmp_path / "no_substances.json"
        wrong.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")
        loader = AmendmentLoader(path=wrong)
        with pytest.raises(ValueError):
            loader.get_amendments()


# ---------------------------------------------------------------------------
# AmendmentPlanDialog
# ---------------------------------------------------------------------------


@pytest.fixture()
def scene_with_two_deficient_beds(qtbot: object) -> tuple[CanvasScene, SoilService, list]:
    """A scene with two N-deficient beds backed by a real SoilService."""
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    pm = ProjectManager()
    svc = SoilService(pm)

    # Bed A: 200x100 cm = 2 m², N-deficient
    bed_a = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED)
    bed_a._name = "Bed A"
    scene.addItem(bed_a)

    # Bed B: 300x100 cm = 3 m², N-deficient
    bed_b = RectangleItem(400, 0, 300, 100, object_type=ObjectType.GARDEN_BED)
    bed_b._name = "Bed B"
    scene.addItem(bed_b)

    for bed in (bed_a, bed_b):
        record = SoilTestRecord(
            date="2026-04-01", ph=6.5, n_level=1, p_level=3, k_level=3,
        )
        history = SoilTestHistory(target_id=str(bed.item_id), records=[record])
        pm.set_soil_test_history(str(bed.item_id), history)

    return scene, svc, [bed_a, bed_b]


class TestAmendmentPlanDialog:
    def test_dialog_groups_by_substance(
        self, qtbot: object, scene_with_two_deficient_beds: tuple
    ) -> None:
        scene, svc, _ = scene_with_two_deficient_beds
        dialog = AmendmentPlanDialog(canvas_scene=scene, soil_service=svc)
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]

        # Both beds need blood_meal — should be one row only.
        assert dialog._table.rowCount() == 1
        substance = dialog._table.item(0, 0).text()
        assert "Blood meal" in substance
        # Total: bed A 2 m² * 2 deficit * 200 g/m² + bed B 3 m² * 2 * 200
        # = 800 + 1200 = 2000 g = "2.00 kg"
        total_text = dialog._table.item(0, 1).text()
        assert "2.00" in total_text and "kg" in total_text
        # Bed names listed
        beds = dialog._table.item(0, 2).text()
        assert "Bed A" in beds and "Bed B" in beds

    def test_clipboard_copy(
        self, qtbot: object, scene_with_two_deficient_beds: tuple
    ) -> None:
        scene, svc, _ = scene_with_two_deficient_beds
        dialog = AmendmentPlanDialog(canvas_scene=scene, soil_service=svc)
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]

        # Clear clipboard, then click copy.
        clipboard = QApplication.clipboard()
        clipboard.clear()
        dialog._on_copy_clicked()
        text = clipboard.text()
        assert "Blood meal" in text
        assert "Bed A" in text and "Bed B" in text

    def test_empty_state_when_no_deficient_beds(self, qtbot: object) -> None:
        """Dialog shows the 'no deficient beds' label and disables Copy."""
        scene = CanvasScene(width_cm=2000, height_cm=2000)
        pm = ProjectManager()
        svc = SoilService(pm)
        dialog = AmendmentPlanDialog(canvas_scene=scene, soil_service=svc)
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]

        assert dialog._table.rowCount() == 0
        # isVisible returns False until the parent is shown — check the
        # underlying flag instead.
        assert dialog._empty_label.isVisibleTo(dialog) is True
        assert dialog._copy_button.isEnabled() is False


# ---------------------------------------------------------------------------
# SoilTestDialog inline section
# ---------------------------------------------------------------------------


class TestInlineAmendments:
    def test_section_hidden_for_global_default(self, qtbot: object) -> None:
        """Global default (bed_area_m2=0.0) hides the amendments section."""
        dialog = SoilTestDialog(target_id="global", bed_area_m2=0.0)
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]
        assert dialog._amendments_box.isVisible() is False

    def test_section_visible_for_real_bed(self, qtbot: object) -> None:
        """A bed with non-zero area shows the amendments section."""
        dialog = SoilTestDialog(target_id="bed-1", bed_area_m2=2.0)
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]
        dialog.show()  # widget needs a top-level show for visibility check
        assert dialog._amendments_box.isVisibleTo(dialog) is True

    def test_section_recomputes_on_target_change(self, qtbot: object) -> None:
        """Changing target pH spinbox updates the recommendation list live."""
        existing = SoilTestRecord(
            date="2026-04-01", ph=5.8, n_level=3, p_level=3, k_level=3,
        )
        dialog = SoilTestDialog(
            target_id="bed-1",
            target_name="Bed 1",
            existing_latest=existing,
            bed_area_m2=2.0,
        )
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]

        # Initial: target pH 6.5 → 560 g of dolomite lime.
        first_text = dialog._amendments_list.item(0).text()
        assert "Dolomite lime" in first_text

        # Bump target pH to 7.5 — quantity should increase.
        dialog._target_ph_spin.setValue(7.5)
        QApplication.processEvents()
        new_text = dialog._amendments_list.item(0).text()
        assert "Dolomite lime" in new_text
        # New qty: (7.5-5.8)/0.25 * 100 * 2.0 = 1360 g = "1.36 kg".
        assert "1.36" in new_text or "1360" in new_text
