"""Shared translated trait controls; values always remain language independent."""

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, pyqtSignal
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
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.layer_buttons: dict[str, QToolButton] = {}
        self.function_buttons: dict[str, QToolButton] = {}
        for row, (values, buttons) in enumerate(((PermacultureLayer, self.layer_buttons),
                                               (PlantFunction, self.function_buttons))):
            for index, value in enumerate(values):
                button = QToolButton(self)
                button.setText(trait_label(value.value))
                button.setCheckable(True)
                button.toggled.connect(self.changed)
                buttons[value.value] = button
                layout.addWidget(button, row * 3 + index // 4, index % 4)

    @property
    def layers(self) -> set[str]:
        return {key for key, button in self.layer_buttons.items() if button.isChecked()}

    @property
    def functions(self) -> set[str]:
        return {key for key, button in self.function_buttons.items() if button.isChecked()}
