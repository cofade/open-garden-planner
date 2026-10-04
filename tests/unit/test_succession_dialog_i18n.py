"""German-locale test for the succession dialog's season labels (US-D3.2).

The dialog's segment labels are the one piece of GUI text this change sits next
to: US-D3.2 moved `_FALLBACK_BOUNDARIES` / `_fallback_segments` out of the
dialog into `models/succession.py`, so the dialog now delegates its segmentation
to `resolve_season_segments`. If that move had disturbed the labels, a German
user would see English season names in the succession dialog while the rest of
the UI is translated.

This closes what would otherwise be a manual-test item: it installs the real
German translator and asserts the four labels come out translated.
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator

from open_garden_planner.ui.dialogs.succession_plan_dialog import _SEGMENT_LABELS


@pytest.fixture
def german(qtbot: Any):  # noqa: ARG001 - qtbot initialises QApplication
    """Install the compiled German translator for the duration of one test."""
    from open_garden_planner.core.i18n import _TRANSLATIONS_DIR

    translator = QTranslator()
    qm = _TRANSLATIONS_DIR / "open_garden_planner_de.qm"
    assert qm.exists(), f"German .qm not found: {qm}"
    assert translator.load(str(qm)), "German .qm failed to load"
    QCoreApplication.installTranslator(translator)
    try:
        yield translator
    finally:
        QCoreApplication.removeTranslator(translator)


class TestGermanSeasonLabels:
    def test_all_four_segment_labels_translate(self, german: Any) -> None:
        assert set(_SEGMENT_LABELS) == {
            "early_spring",
            "late_spring",
            "summer",
            "fall",
        }
        untranslated = []
        for key, english in _SEGMENT_LABELS.items():
            german_text = QCoreApplication.translate(
                "SuccessionPlanDialog", english
            )
            if german_text == english:
                untranslated.append(key)
        assert not untranslated, (
            "these season labels are not translated in German: "
            f"{untranslated}"
        )

    def test_the_dialog_still_segments_through_the_shared_resolver(self) -> None:
        """The extraction must not have left the dialog with its own copy."""

        from open_garden_planner.models.succession import (
            SEASON_SEGMENTS,
            compute_fallback_segments,
            resolve_season_segments,
        )
        from open_garden_planner.ui.dialogs import succession_plan_dialog as dlg

        # The private table this change moved must be GONE from the dialog.
        assert not hasattr(dlg, "_FALLBACK_BOUNDARIES"), (
            "the dialog still owns a private fallback table; it must delegate to "
            "models/succession.py or the agent can disagree with the GUI"
        )
        assert not hasattr(dlg, "_fallback_segments"), (
            "the dialog still owns a private fallback function"
        )

        # No location -> the shared month fallback, identical either way.
        from_dialog = dlg.SuccessionPlanDialog.__new__(dlg.SuccessionPlanDialog)
        from_dialog._frost_dates_raw = None
        got = from_dialog._build_segments(2026, None)
        assert got == compute_fallback_segments(2026)
        assert got == resolve_season_segments(2026, None)[0]
        assert set(got) == set(SEASON_SEGMENTS)

    def test_frost_dates_still_win_over_the_fallback(self) -> None:
        from open_garden_planner.models.succession import compute_season_segments
        from open_garden_planner.ui.dialogs import succession_plan_dialog as dlg

        d = dlg.SuccessionPlanDialog.__new__(dlg.SuccessionPlanDialog)
        location = {
            "frost_dates": {
                "last_spring_frost": "04-15",
                "first_fall_frost": "10-15",
            }
        }
        assert d._build_segments(2026, location) == compute_season_segments(
            "04-15", "10-15", 2026
        )
