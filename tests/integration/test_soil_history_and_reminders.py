"""Integration tests for US-12.10e — History sparklines & seasonal reminder badge.

Covers:
  * Pure ``SoilService.is_test_overdue`` rules.
  * ``SoilSparklineWidget`` rendering with empty / single / multi-record data.
  * ``SoilTestDialog`` History tab structure and population.
  * ``SoilBadgeItem`` click signal.
  * ``CanvasView._update_soil_badges`` add/remove lifecycle.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.soil_badge_item import SoilBadgeItem
from open_garden_planner.ui.dialogs.soil_test_dialog import SoilTestDialog
from open_garden_planner.ui.widgets.soil_sparkline_widget import SoilSparklineWidget


# ---------------------------------------------------------------------------
# Helpers


def _record(d: str, **kwargs) -> SoilTestRecord:
    return SoilTestRecord(date=d, **kwargs)


def _history(*records: SoilTestRecord, target_id: str = "bed-1") -> SoilTestHistory:
    return SoilTestHistory(target_id=target_id, records=list(records))


# ---------------------------------------------------------------------------
# TestIsTestOverdue — pure-function tests


class TestIsTestOverdue:
    @pytest.mark.parametrize("month", [1, 2, 5, 6, 7, 8, 11, 12])
    def test_off_season_never_overdue(self, month: int) -> None:
        history = _history(_record("2020-01-01", ph=6.5))
        today = date(2026, month, 15)
        assert SoilService.is_test_overdue(history, today) is False

    def test_none_history_not_overdue(self) -> None:
        # Untested beds get no nag, even in season — locked design decision.
        today = date(2026, 4, 1)
        assert SoilService.is_test_overdue(None, today) is False

    def test_empty_records_not_overdue(self) -> None:
        history = SoilTestHistory(target_id="bed-1", records=[])
        today = date(2026, 4, 1)
        assert SoilService.is_test_overdue(history, today) is False

    @pytest.mark.parametrize("month", [3, 4, 9, 10])
    def test_in_season_old_test_is_overdue(self, month: int) -> None:
        today = date(2026, month, 15)
        last = today - timedelta(days=200)
        history = _history(_record(last.isoformat(), ph=6.5))
        assert SoilService.is_test_overdue(history, today) is True

    @pytest.mark.parametrize("month", [3, 4, 9, 10])
    def test_in_season_recent_test_not_overdue(self, month: int) -> None:
        today = date(2026, month, 15)
        last = today - timedelta(days=30)
        history = _history(_record(last.isoformat(), ph=6.5))
        assert SoilService.is_test_overdue(history, today) is False

    def test_boundary_180_days_not_overdue(self) -> None:
        # > 180, not >=180 — exactly 180 days is still fine.
        today = date(2026, 4, 1)
        last = today - timedelta(days=180)
        history = _history(_record(last.isoformat()))
        assert SoilService.is_test_overdue(history, today) is False

    def test_boundary_181_days_overdue(self) -> None:
        today = date(2026, 4, 1)
        last = today - timedelta(days=181)
        history = _history(_record(last.isoformat()))
        assert SoilService.is_test_overdue(history, today) is True

    def test_malformed_date_treated_as_overdue(self) -> None:
        history = _history(_record("not-a-date"))
        today = date(2026, 4, 1)
        assert SoilService.is_test_overdue(history, today) is True


# ---------------------------------------------------------------------------
# TestSoilSparklineWidget — render smoke tests


class TestSoilSparklineWidget:
    def test_rejects_unknown_parameter(self, qtbot) -> None:
        with pytest.raises(ValueError, match="Unknown sparkline parameter"):
            SoilSparklineWidget("zinc")

    @pytest.mark.parametrize("param", ["ph", "n", "p", "k"])
    def test_empty_data_renders_placeholder(self, qtbot, param: str) -> None:
        widget = SoilSparklineWidget(param)
        qtbot.addWidget(widget)
        widget.set_data([])
        widget.resize(200, 80)
        widget.show()
        qtbot.waitExposed(widget)  # paint event runs without raising

    def test_single_record_paints_dot(self, qtbot) -> None:
        widget = SoilSparklineWidget("ph")
        qtbot.addWidget(widget)
        widget.set_data([_record("2026-04-01", ph=6.5)])
        widget.resize(200, 80)
        widget.show()
        qtbot.waitExposed(widget)

    def test_multiple_records_paint_polyline(self, qtbot) -> None:
        widget = SoilSparklineWidget("n")
        qtbot.addWidget(widget)
        widget.set_data([
            _record("2024-04-01", n_level=2),
            _record("2025-04-01", n_level=3),
            _record("2026-04-01", n_level=1),
        ])
        widget.resize(240, 80)
        widget.show()
        qtbot.waitExposed(widget)

    def test_set_data_is_idempotent(self, qtbot) -> None:
        widget = SoilSparklineWidget("k")
        qtbot.addWidget(widget)
        records = [_record("2026-01-01", k_level=2), _record("2026-04-01", k_level=4)]
        widget.set_data(records)
        widget.set_data(records)
        widget.set_data(records)
        # Sorting + repaint must not blow up
        widget.resize(200, 80)
        widget.show()
        qtbot.waitExposed(widget)


# ---------------------------------------------------------------------------
# TestSoilTestDialogHistoryTab — tab structure


class TestSoilTestDialogHistoryTab:
    def test_dialog_has_two_tabs(self, qtbot) -> None:
        history = _history(_record("2026-04-01", ph=6.5))
        dialog = SoilTestDialog(
            target_id="bed-1",
            target_name="Bed 1",
            existing_history=history,
        )
        qtbot.addWidget(dialog)
        assert dialog._tabs.count() == 2

    def test_history_tab_lists_records_descending(self, qtbot) -> None:
        from PyQt6.QtWidgets import QLabel

        history = _history(
            _record("2024-04-01", ph=6.0),
            _record("2025-04-01", ph=6.5),
            _record("2026-04-01", ph=7.0),
        )
        dialog = SoilTestDialog(
            target_id="bed-1",
            target_name="Bed 1",
            existing_history=history,
        )
        qtbot.addWidget(dialog)

        layout = dialog._history_records_layout
        labels: list[str] = []
        for i in range(layout.count()):
            row = layout.itemAt(i).widget()
            if row is None:
                continue
            for child in row.findChildren(QLabel):
                labels.append(child.text())
                break
        assert len(labels) == 3
        assert labels[0].startswith("2026-04-01")
        assert labels[1].startswith("2025-04-01")
        assert labels[2].startswith("2024-04-01")

    def test_history_tab_has_four_sparklines(self, qtbot) -> None:
        history = _history(_record("2026-04-01", ph=6.5))
        dialog = SoilTestDialog(
            target_id="bed-1",
            target_name="Bed 1",
            existing_history=history,
        )
        qtbot.addWidget(dialog)

        assert set(dialog._sparklines.keys()) == {"ph", "n", "p", "k"}

    def test_empty_history_shows_placeholder_row(self, qtbot) -> None:
        from PyQt6.QtWidgets import QLabel

        dialog = SoilTestDialog(
            target_id="bed-1",
            target_name="Bed 1",
            existing_history=None,
        )
        qtbot.addWidget(dialog)
        layout = dialog._history_records_layout
        assert layout.count() == 1
        placeholder = layout.itemAt(0).widget()
        assert isinstance(placeholder, QLabel)


# ---------------------------------------------------------------------------
# TestSoilBadgeItem — click signal


class TestSoilBadgeItem:
    def test_emits_clicked_signal_with_bed_id(self, qtbot) -> None:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        bed = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED, name="Bed",
        )
        scene.addItem(bed)
        badge = SoilBadgeItem(bed, "bed-uuid-1")
        scene.addItem(badge)

        from PyQt6.QtCore import Qt

        # QGraphicsSceneMouseEvent can't be instantiated from Python in PyQt6;
        # MagicMock with the methods the handler reads is sufficient here.
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.LeftButton

        with qtbot.waitSignal(badge.clicked, timeout=500) as blocker:
            badge.mousePressEvent(event)

        assert blocker.args == ["bed-uuid-1"]
        event.accept.assert_called_once()


# ---------------------------------------------------------------------------
# TestCanvasBadgeUpdates — add/remove lifecycle


class TestCanvasBadgeUpdates:
    def _make_canvas(self, qtbot) -> tuple[CanvasView, RectangleItem]:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)

        bed = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED, name="Bed 1",
        )
        scene.addItem(bed)
        return view, bed

    def test_overdue_bed_gets_badge(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        bed_id = str(bed.item_id)

        old = (date(2026, 4, 1) - timedelta(days=200)).isoformat()
        history = _history(_record(old, ph=6.5), target_id=bed_id)

        svc = MagicMock()
        svc.get_history.return_value = history
        svc.get_effective_record.return_value = None
        view.set_soil_service(svc)
        view._update_soil_badges(today=date(2026, 4, 1))

        assert bed_id in view._soil_badges

    def test_recent_test_no_badge(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        bed_id = str(bed.item_id)

        recent = (date(2026, 4, 1) - timedelta(days=30)).isoformat()
        history = _history(_record(recent, ph=6.5), target_id=bed_id)

        svc = MagicMock()
        svc.get_history.return_value = history
        svc.get_effective_record.return_value = None
        view.set_soil_service(svc)
        view._update_soil_badges(today=date(2026, 4, 1))

        assert bed_id not in view._soil_badges

    def test_off_season_no_badge_even_for_old_tests(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        bed_id = str(bed.item_id)

        old = "2020-01-01"
        history = _history(_record(old, ph=6.5), target_id=bed_id)

        svc = MagicMock()
        svc.get_history.return_value = history
        svc.get_effective_record.return_value = None
        view.set_soil_service(svc)
        view._update_soil_badges(today=date(2026, 7, 1))  # off-season

        assert bed_id not in view._soil_badges

    def test_badge_removed_after_recent_test(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        bed_id = str(bed.item_id)

        old = (date(2026, 4, 1) - timedelta(days=200)).isoformat()
        old_history = _history(_record(old, ph=6.5), target_id=bed_id)

        svc = MagicMock()
        svc.get_history.return_value = old_history
        svc.get_effective_record.return_value = None
        view.set_soil_service(svc)
        view._update_soil_badges(today=date(2026, 4, 1))
        assert bed_id in view._soil_badges

        # Now simulate adding a recent test:
        new_history = _history(
            _record(old, ph=6.5),
            _record("2026-03-25", ph=6.7),
            target_id=bed_id,
        )
        svc.get_history.return_value = new_history
        view._update_soil_badges(today=date(2026, 4, 1))

        assert bed_id not in view._soil_badges

    def test_untested_bed_gets_no_badge(self, qtbot) -> None:
        view, bed = self._make_canvas(qtbot)
        bed_id = str(bed.item_id)

        # Empty history — locked design decision: no nag for untested beds.
        empty_history = SoilTestHistory(target_id=bed_id, records=[])
        svc = MagicMock()
        svc.get_history.return_value = empty_history
        svc.get_effective_record.return_value = None
        view.set_soil_service(svc)
        view._update_soil_badges(today=date(2026, 4, 1))

        assert bed_id not in view._soil_badges
