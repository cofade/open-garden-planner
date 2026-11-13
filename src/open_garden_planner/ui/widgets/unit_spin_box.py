"""Measurement fields whose value unit never follows their display unit.

value(), setValue(), ranges and valueChanged stay in cm (or the explicitly
supplied value_unit_cm), and litres for volumes. Metric uses Qt's native text,
decimals, suffix and steps. A unit switch blocks signals and retains the exact
value; merely focusing a rounded imperial readout never writes it back.
"""

from __future__ import annotations

import math
import re

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QKeyEvent, QValidator
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QInputDialog,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.unit_preference import active_unit_system
from open_garden_planner.core.units import (
    LITRES_PER_US_QUART,
    LengthStyle,
    UnitSystem,
    cm_to_inches,
    format_length,
    format_volume,
    imperial_step_inches,
    inches_to_cm,
    parse_length,
    parse_volume,
)
from open_garden_planner.ui.units_notifier import units_notifier


class _UnitSpinBox(QDoubleSpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        self._system = UnitSystem.METRIC
        self._metric_decimals = 2
        self._metric_suffix = ""
        self._metric_step = 1.0
        self._exact = 0.0
        super().__init__(parent)
        self.valueChanged.connect(self._remember_exact)
        units_notifier().changed.connect(self._on_units_changed)
        self._on_units_changed(active_unit_system())

    def unit_system(self) -> UnitSystem:
        return self._system

    def value(self) -> float:
        return self._exact

    def _remember_exact(self, value: float) -> None:
        self._exact = value

    def setDecimals(self, prec: int) -> None:
        self._metric_decimals = prec
        if self._system == UnitSystem.METRIC:
            super().setDecimals(prec)

    def setSuffix(self, suffix: str | None) -> None:
        self._metric_suffix = suffix or ""
        if self._system == UnitSystem.METRIC:
            super().setSuffix(suffix)

    def setSingleStep(self, val: float) -> None:
        self._metric_step = val
        super().setSingleStep(val)

    def setValue(self, val: float) -> None:
        value = min(self.maximum(), max(self.minimum(), val))
        self._exact = value
        super().setValue(value)
        # Qt rounds its internal value to decimals before emitting. Preserve the
        # caller's value in imperial, including a real US gallon's nine places.
        self._exact = value if self._system == UnitSystem.IMPERIAL else super().value()

    def _on_units_changed(self, system: UnitSystem) -> None:
        exact = self._exact
        self._system = system
        with QSignalBlocker(self):
            super().setDecimals(self._metric_decimals if system == UnitSystem.METRIC else 12)
            super().setSuffix(self._metric_suffix if system == UnitSystem.METRIC else "")
            # One edit reaches the model once, on acceptance, not as each
            # intermediate unit token becomes a temporarily valid number.
            self.setKeyboardTracking(system == UnitSystem.METRIC)
            super().setValue(exact)
        self._exact = exact

    def textFromValue(self, value: float) -> str:
        if self._system == UnitSystem.METRIC:
            return super().textFromValue(value)
        return self._imperial_text(value)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return
        rendered = self.prefix() + self.textFromValue(super().value()) + self.suffix()
        editor = self.lineEdit()
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and editor is not None
            and editor.text() == rendered
        ):
            # Qt deliberately emits valueChanged again on Return, even for
            # unchanged text. After switching to coarse metric precision that
            # can write the rounded display back. Preserve normal key handling
            # (including a dialog's default button) and editingFinished only.
            exact = self._exact
            with QSignalBlocker(self):
                super().keyPressEvent(event)
            self._exact = exact
            self.editingFinished.emit()
            return
        super().keyPressEvent(event)

    def _number_text(self, text: str) -> str:
        prefix = self.prefix()
        return text[len(prefix) :].strip() if prefix and text.startswith(prefix) else text.strip()

    def valueFromText(self, text: str | None) -> float:
        if self._system == UnitSystem.METRIC:
            rendered = self.prefix() + super().textFromValue(super().value()) + self.suffix()
            if text == rendered:
                return self._exact
            return super().valueFromText(text)
        number = self._number_text(text or "")
        if number == self._imperial_text(super().value()):
            return self._exact
        try:
            return self._parse_imperial(number)
        except ValueError:
            return self._exact

    def validate(self, text: str | None, pos: int) -> tuple[QValidator.State, str, int]:
        text = text or ""
        if self._system == UnitSystem.METRIC:
            return super().validate(text, pos)
        if self.specialValueText() and text == self.specialValueText():
            return QValidator.State.Acceptable, text, pos
        number = self._number_text(text)
        try:
            value = self._parse_imperial(number)
            state = (
                QValidator.State.Acceptable
                if self.minimum() <= value <= self.maximum()
                else QValidator.State.Intermediate
            )
        except ValueError:
            state = (
                QValidator.State.Intermediate
                if re.fullmatch(r"[\s\d.,/'\"+\-a-zA-Z]*", number)
                else QValidator.State.Invalid
            )
        return state, text, pos

    def _imperial_text(self, value: float) -> str:
        raise NotImplementedError

    def _parse_imperial(self, text: str) -> float:
        raise NotImplementedError


class LengthSpinBox(_UnitSpinBox):
    def __init__(
        self,
        style: LengthStyle = LengthStyle.AUTO,
        parent: QWidget | None = None,
        *,
        value_unit_cm: float = 1.0,
    ) -> None:
        self._style = style
        self._value_unit_cm = value_unit_cm
        super().__init__(parent)

    def _imperial_text(self, value: float) -> str:
        return format_length(
            value * self._value_unit_cm,
            UnitSystem.IMPERIAL,
            self._style,
            decimal_mark=self.locale().decimalPoint(),
        )

    def _parse_imperial(self, text: str) -> float:
        return (
            parse_length(
                text,
                UnitSystem.IMPERIAL,
                bare_unit_cm=30.48 if self._value_unit_cm == 100 else 2.54,
            )
            / self._value_unit_cm
        )

    def stepBy(self, steps: int) -> None:
        if self._system == UnitSystem.METRIC:
            super().stepBy(steps)
            return
        self.interpretText()
        step = imperial_step_inches(self._metric_step * self._value_unit_cm, self._style)
        inches = cm_to_inches(self.value() * self._value_unit_cm)
        target = (math.floor(inches / step + 0.5) + steps) * step
        self.setValue(inches_to_cm(target) / self._value_unit_cm)


class VolumeSpinBox(_UnitSpinBox):
    def _imperial_text(self, value: float) -> str:
        return format_volume(value, UnitSystem.IMPERIAL, decimal_mark=self.locale().decimalPoint())

    def _parse_imperial(self, text: str) -> float:
        return parse_volume(text, UnitSystem.IMPERIAL)

    def stepBy(self, steps: int) -> None:
        if self._system == UnitSystem.METRIC:
            super().stepBy(steps)
            return
        self.interpretText()
        self.setValue(
            (math.floor(self.value() / LITRES_PER_US_QUART + 0.5) + steps) * LITRES_PER_US_QUART
        )


def get_length(
    parent: QWidget | None,
    title: str,
    label: str,
    value_cm: float,
    minimum_cm: float,
    maximum_cm: float,
    *,
    style: LengthStyle = LengthStyle.AUTO,
) -> tuple[float, bool]:
    if active_unit_system() == UnitSystem.METRIC:
        return QInputDialog.getDouble(parent, title, label, value_cm, minimum_cm, maximum_cm, 2)
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(label))
    box = LengthSpinBox(style)
    box.setRange(minimum_cm, maximum_cm)
    box.setValue(value_cm)
    layout.addWidget(box)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return (box.value() if accepted else value_cm), accepted
