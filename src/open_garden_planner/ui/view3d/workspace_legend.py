"""Sun-path legend and locale formatting helpers (Phase 17 L2, issue #583)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from PyQt6.QtCore import QCoreApplication, QDate, QLocale, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from open_garden_planner.core.scene3d.sun_path import ARC_KINDS, ARC_RGBA

#: When two solar arcs are within this angular distance, they are treated as twins.
TWIN_ARC_DEG: Final = 0.5


def _twin_arcs(arcs: Sequence[Any]) -> frozenset[str]:
    """The key days whose arc the plan date's arc covers: their solar noon within
    ``TWIN_ARC_DEG`` of the plan date's (3D review round 2 of #386)."""
    today = next((arc for arc in arcs if getattr(arc, "kind", "") == "today"), None)
    if today is None or getattr(today, "noon", None) is None:
        return frozenset()
    return frozenset(
        arc.kind
        for arc in arcs
        if getattr(arc, "kind", "") != "today"
        and getattr(arc, "noon", None) is not None
        and abs(arc.noon.elevation_deg - today.noon.elevation_deg) <= TWIN_ARC_DEG
    )


def _locale_date(day: Any) -> str:
    """A date in the locale's short format ("" for none)."""
    if day is None:
        return ""
    return QLocale().toString(QDate(day.year, day.month, day.day), QLocale.FormatType.ShortFormat)


def _locale_number(value: float) -> str:
    return QLocale().toString(float(value), "f", 1)


class SunPathLegend(QWidget):
    """The sun-path legend displayed in the 3D pane notices area."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        names = {
            "today": QCoreApplication.translate("Workspace", "Plan date"),
            "june_solstice": QCoreApplication.translate("Workspace", "21 June"),
            "december_solstice": QCoreApplication.translate("Workspace", "21 December"),
            "march_equinox": QCoreApplication.translate("Workspace", "20 March"),
        }
        self._swatches: list[QWidget] = []
        self._names = names
        self._labels: dict[str, QLabel] = {}

        for kind in ARC_KINDS:
            swatch = QFrame(self)
            swatch.setFixedSize(16, 4)
            red, green, blue, _alpha = ARC_RGBA[kind]
            palette = swatch.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor(red, green, blue))
            swatch.setPalette(palette)
            swatch.setAutoFillBackground(True)
            layout.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)

            label = QLabel(names[kind], self)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
            layout.addSpacing(6)
            self._swatches.extend((swatch, label))
            self._labels[kind] = label

        self._note = QLabel(
            QCoreApplication.translate("Workspace", "Set a garden location to draw the sun path."),
            self,
        )
        self._note.setTextFormat(Qt.TextFormat.PlainText)
        self._note.setWordWrap(True)
        layout.addWidget(self._note, 1)
        layout.addStretch(1)
        self.hide()

    def legend_text(self) -> str:
        """What the legend says ("" while it is hidden) — the tests' read."""
        if self.isHidden():
            return ""
        if not self._note.isHidden():
            return self._note.text()
        return " ".join(
            widget.text()
            for widget in self._swatches
            if isinstance(widget, QLabel) and widget.text()
        )

    def update_legend(self, analysis: Any, chrome_visible: bool = True) -> bool:
        """Update visibility and labels based on the active analysis.

        Returns True if the legend is visible, False otherwise.
        """
        shown = analysis is not None and analysis.sun_path_visible and chrome_visible
        if shown and analysis is not None:
            located = analysis.has_location()
            for widget in self._swatches:
                widget.setVisible(located)
            self._note.setVisible(not located)
            twins = _twin_arcs(analysis.arcs())
            for kind, label in self._labels.items():
                name = self._names[kind]
                if kind in twins:
                    label.setText(
                        QCoreApplication.translate(
                            "Workspace", "{day} — same path as the plan date"
                        ).format(day=name)
                    )
                else:
                    label.setText(name)
        self.setVisible(shown)
        return shown

