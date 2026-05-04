"""Integration tests for the PestDiseaseDialog (US-12.7).

Smoke tests that exercise the dialog widgets in offscreen Qt without
showing it: pre-population, result_record() round-trip, edit-mode
preserves the record id, photo attach/remove round-trips through the
preview label.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QImage, qRgb

from open_garden_planner.models.pest_disease import (
    PestDiseaseLog,
    PestDiseaseRecord,
)
from open_garden_planner.ui.dialogs.pest_disease_dialog import PestDiseaseDialog


class TestEntryFormPopulationAndResult:
    def test_default_record_has_today_date_and_pest_low(
        self, qtbot: object  # noqa: ARG002
    ) -> None:
        dlg = PestDiseaseDialog(target_id="bed-1", target_name="Tomatoes")
        # Pre-fill name so result_record passes (the dialog rejects empty names
        # only on accept; result_record itself does not validate).
        dlg._name_edit.setText("Aphid")
        rec = dlg.result_record()
        assert rec.kind == "pest"
        assert rec.severity == "low"
        # ISO date is YYYY-MM-DD; just check shape.
        assert len(rec.date) == 10 and rec.date[4] == "-" and rec.date[7] == "-"

    def test_existing_record_pre_populates_form(self, qtbot: object) -> None:  # noqa: ARG002
        existing = PestDiseaseRecord(
            date="2026-04-25",
            kind="disease",
            name="Powdery mildew",
            severity="high",
            treatment="Milk spray",
            notes="leaves yellowed",
        )
        dlg = PestDiseaseDialog(
            target_id="bed-1",
            target_name="Tomatoes",
            existing_record=existing,
        )
        assert dlg._name_edit.text() == "Powdery mildew"
        assert dlg._kind_combo.currentData() == "disease"
        assert dlg._severity_combo.currentData() == "high"
        assert dlg._treatment_edit.toPlainText() == "Milk spray"
        assert dlg._notes_edit.toPlainText() == "leaves yellowed"

    def test_edit_mode_preserves_record_id(self, qtbot: object) -> None:  # noqa: ARG002
        existing = PestDiseaseRecord(
            id="fixed-id-123", date="2026-05-04", name="Aphid", severity="low"
        )
        dlg = PestDiseaseDialog(
            target_id="bed-1",
            existing_record=existing,
            edit_mode=True,
        )
        out = dlg.result_record()
        assert out.id == "fixed-id-123"

    def test_non_edit_mode_generates_new_id(self, qtbot: object) -> None:  # noqa: ARG002
        existing = PestDiseaseRecord(
            id="fixed-id-123", date="2026-05-04", name="Aphid", severity="low"
        )
        dlg = PestDiseaseDialog(
            target_id="bed-1",
            existing_record=existing,
            edit_mode=False,
        )
        out = dlg.result_record()
        assert out.id != "fixed-id-123"

    def test_history_tab_lists_existing_records_newest_first(
        self, qtbot: object  # noqa: ARG002
    ) -> None:
        log = PestDiseaseLog(target_id="bed-1")
        log.records.append(PestDiseaseRecord(date="2026-04-01", name="OlderName"))
        log.records.append(PestDiseaseRecord(date="2026-05-01", name="NewerName"))
        dlg = PestDiseaseDialog(target_id="bed-1", existing_log=log)
        items = [
            dlg._history_list.item(i).text()
            for i in range(dlg._history_list.count())
        ]
        # Newest first
        assert "NewerName" in items[0]
        assert "OlderName" in items[1]

    def test_history_tab_hidden_in_edit_mode(self, qtbot: object) -> None:  # noqa: ARG002
        log = PestDiseaseLog(target_id="bed-1")
        log.records.append(PestDiseaseRecord(date="2026-04-01", name="A"))
        dlg = PestDiseaseDialog(
            target_id="bed-1",
            existing_log=log,
            existing_record=log.records[0],
            edit_mode=True,
        )
        # Only the Entry tab present.
        assert dlg._tabs.count() == 1


class TestPhotoAttachInDialog:
    def test_photo_attach_decodes_into_preview(
        self, tmp_path: Path, qtbot: object  # noqa: ARG002
    ) -> None:
        from open_garden_planner.services.photo_attachment import (
            encode_photo_to_base64,
        )

        src = tmp_path / "p.png"
        img = QImage(400, 300, QImage.Format.Format_RGB32)
        img.fill(qRgb(50, 50, 50))
        img.save(str(src), "PNG")
        b64 = encode_photo_to_base64(src)

        existing = PestDiseaseRecord(
            date="2026-05-04", name="Aphid", photo_base64=b64
        )
        dlg = PestDiseaseDialog(target_id="bed-1", existing_record=existing)
        # Preview label should hold a non-null pixmap (sized down to thumb).
        assert not dlg._photo_label.pixmap().isNull()
        assert dlg._remove_photo_btn.isEnabled()
        # Result preserves the photo.
        out = dlg.result_record()
        assert out.photo_base64 == b64

    def test_remove_photo_clears_preview_and_record(
        self, tmp_path: Path, qtbot: object  # noqa: ARG002
    ) -> None:
        from open_garden_planner.services.photo_attachment import (
            encode_photo_to_base64,
        )

        src = tmp_path / "p2.png"
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(qRgb(10, 10, 10))
        img.save(str(src), "PNG")
        b64 = encode_photo_to_base64(src)

        existing = PestDiseaseRecord(
            date="2026-05-04", name="Aphid", photo_base64=b64
        )
        dlg = PestDiseaseDialog(target_id="bed-1", existing_record=existing)
        dlg._on_remove_photo()
        assert dlg._photo_b64 is None
        assert not dlg._remove_photo_btn.isEnabled()
        assert dlg.result_record().photo_base64 is None
