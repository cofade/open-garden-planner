"""Shared translated trait controls; values always remain language independent."""

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QToolButton, QWidget

from open_garden_planner.models.plant_data import PermacultureLayer, PlantFunction


def trait_label(value: str) -> str:
    labels = {
        "canopy": QT_TR_NOOP("Canopy"), "sub_canopy": QT_TR_NOOP("Sub-canopy"), "shrub": QT_TR_NOOP("Shrubs"),
        "herbaceous": QT_TR_NOOP("Herbaceous"), "ground_cover": QT_TR_NOOP("Ground cover"), "root": QT_TR_NOOP("Roots"),
        "vine": QT_TR_NOOP("Vines"), "unknown": QT_TR_NOOP("Unspecified"), "nitrogen_fixer": QT_TR_NOOP("Nitrogen fixer"),
        "dynamic_accumulator": QT_TR_NOOP("Dynamic accumulator"), "pollinator_attractor": QT_TR_NOOP("Pollinator attractor"),
        "pest_deterrent": QT_TR_NOOP("Pest deterrent"), "mulch_maker": QT_TR_NOOP("Mulch maker"), "windbreak": QT_TR_NOOP("Windbreak"),
        "hedgerow": QT_TR_NOOP("Hedgerow"), "animal_feed": QT_TR_NOOP("Animal feed"), "medicinal": QT_TR_NOOP("Medicinal"),
        "dye": QT_TR_NOOP("Dye"), "fiber": QT_TR_NOOP("Fiber"),
    }
    return QCoreApplication.translate("Permaculture", labels[value])


class TraitFilters(QWidget):
    """Compact multi-select chips with OR layers and AND functions."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self.layer_buttons: dict[str, QToolButton] = {}
        self.function_buttons: dict[str, QToolButton] = {}
        for values, buttons in ((PermacultureLayer, self.layer_buttons),
                                (PlantFunction, self.function_buttons)):
            for value in values:
                button = QToolButton(self)
                button.setText(trait_label(value.value))
                button.setCheckable(True)
                button.toggled.connect(self.changed)
                buttons[value.value] = button
        self._columns = 0
        self._arrange(4)

    def fit_width(self, width: int) -> None:
        """Use fewer columns when translated or styled chips need more room."""
        buttons = [*self.layer_buttons.values(), *self.function_buttons.values()]
        spacing = max(0, self._grid.horizontalSpacing())
        widest = max(button.sizeHint().width() for button in buttons)
        self._arrange(max(1, min(4, (width + spacing) // (widest + spacing))))

    def _arrange(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        row_offset = 0
        for buttons in (self.layer_buttons, self.function_buttons):
            for i, button in enumerate(buttons.values()):
                self._grid.removeWidget(button)
                row, col = divmod(i, columns)
                self._grid.addWidget(button, row + row_offset, col)
            row_offset += (len(buttons) + columns - 1) // columns

    @property
    def layers(self) -> set[str]:
        return {key for key, button in self.layer_buttons.items() if button.isChecked()}

    @property
    def functions(self) -> set[str]:
        return {key for key, button in self.function_buttons.items() if button.isChecked()}

    def clear(self) -> None:
        """Reset the controls as part of a caller's batched filter update."""
        for button in (*self.layer_buttons.values(), *self.function_buttons.values()):
            with QSignalBlocker(button):
                button.setChecked(False)
