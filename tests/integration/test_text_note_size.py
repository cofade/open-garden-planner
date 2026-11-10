"""A text note's size is stated in the unit it has on the plan (#836, point 3).

``TextItem.font_size`` was documented and labelled as centimetres. It is not:
the number is the font's point size divided by 28.35, and one point of a
scene item's font is laid out at the screen's 96 pixels per inch, where one
pixel is one plan centimetre. A stored 1.0 is a 28 pt font: letters with an em
of 37 cm. The stored number keeps its meaning (plans look as they did); the
Properties panel states and takes the font's height on the plan.

Every test measures the rendered note or the font the item really has.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QDoubleSpinBox

from open_garden_planner.core.commands import CommandManager
from open_garden_planner.core.project import FILE_VERSION, ProjectManager
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.text_item import TextItem
from open_garden_planner.ui.panels import PropertiesPanel

NOTE_INK = QColor(255, 0, 255)
#: Stored sizes: the default, the three bundled examples' notes, and the ends.
STORED = [0.1, 0.24, 0.47, 0.65, 1.0, 1.5, 2.0, 3.3, 10.0]
#: What each stored size has always been drawn with: Arial of this many points.
STORED_POINTS = [(0.1, 3), (0.24, 7), (0.47, 13), (0.65, 18), (1.0, 28), (1.5, 43), (2.0, 57),
                 (3.3, 94), (10.0, 283), (100.0, 2835)]


def _scene(stored: float, text: str = "HHHH") -> tuple[CanvasScene, TextItem]:
    scene = CanvasScene(width_cm=3000, height_cm=2000)
    note = TextItem(200, 1500, text, font_size=stored, text_color=NOTE_INK)
    scene.addItem(note)
    return scene, note


def _picture(scene: CanvasScene, px_per_cm: float = 1.0) -> np.ndarray:
    """The plan as pixels, *px_per_cm* of them to a plan centimetre, Y up."""
    rect = scene.canvas_rect
    width, height = round(rect.width() * px_per_cm), round(rect.height() * px_per_cm)
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.translate(0, height)
    painter.scale(1.0, -1.0)
    scene.render(painter, QRectF(0, 0, width, height), rect)
    painter.end()
    buffer = image.bits()
    buffer.setsize(image.sizeInBytes())
    rows = np.frombuffer(buffer, dtype=np.uint8).reshape(height, image.bytesPerLine() // 4, 4)
    return rows[:, :width, :3].copy()


def _ink_height_cm(scene: CanvasScene, px_per_cm: float = 1.0) -> float:
    """How tall the note's letters are drawn, in plan centimetres."""
    pixels = _picture(scene, px_per_cm)
    magenta = (pixels[:, :, 2] > 150) & (pixels[:, :, 0] > 150) & (pixels[:, :, 1] < 120)
    lines = np.flatnonzero(magenta.any(axis=1))
    assert lines.size, "the note is not in the picture"
    return float(lines[-1] - lines[0] + 1) / px_per_cm


def _size_spin(panel: PropertiesPanel) -> QDoubleSpinBox:
    spins = [spin for spin in panel.findChildren(QDoubleSpinBox) if getattr(spin, "_ogp_text_size", False)]
    assert len(spins) == 1, "expected exactly one text size field"
    return spins[0]


def _panel(note: TextItem) -> tuple[PropertiesPanel, CommandManager]:
    manager = CommandManager()
    panel = PropertiesPanel()
    panel.set_command_manager(manager)
    panel.set_selected_items([note])
    return panel, manager


@pytest.mark.parametrize(("stored", "points"), STORED_POINTS)
def test_a_stored_size_is_drawn_with_the_font_it_always_had(qtbot, stored: float, points: int) -> None:
    """The invariant of this change: no stored value renders differently."""
    _scene_, note = _scene(stored)
    font = note.font()
    assert font.family() == "Arial"
    assert font.pointSize() == points
    assert font.pixelSize() == -1, "the font is sized in points, as it always was"
    assert FILE_VERSION == "1.4", "the file format did not change for this"


@pytest.mark.parametrize("stored", [0.47, 1.0, 2.0, 5.0])
def test_the_size_the_panel_states_is_the_size_of_the_letters_on_the_plan(qtbot, stored: float) -> None:
    scene, note = _scene(stored)
    panel, _manager = _panel(note)
    qtbot.addWidget(panel)
    spin = _size_spin(panel)
    assert spin.suffix().strip() == "cm"

    stated = spin.value()
    drawn = _ink_height_cm(scene)
    # A capital letter is 0.72 of Arial's em; the test platform's stand-in font
    # draws a box of one em. Either way the stated height is the letters' size.
    assert 0.6 * stated <= drawn <= 1.1 * stated, (
        f"the panel says {stated:g} cm, the letters are {drawn:g} cm tall"
    )
    assert stated == pytest.approx(note.em_height_cm, abs=0.5)


@pytest.mark.parametrize("typed", [10.0, 30.0, 50.0, 120.0, 400.0])
def test_a_size_typed_into_the_panel_is_the_size_drawn(qtbot, typed: float) -> None:
    scene, note = _scene(1.0)
    panel, _manager = _panel(note)
    qtbot.addWidget(panel)
    spin = _size_spin(panel)

    spin.setValue(typed)
    # Sizes step by one point of the font, 1.33 cm on the plan.
    assert note.em_height_cm == pytest.approx(typed, abs=1.0)
    drawn = _ink_height_cm(scene)
    assert 0.6 * typed <= drawn <= 1.1 * typed, f"typed {typed:g} cm, drawn {drawn:g} cm"
    # What the panel shows after the edit is what the note has, not what was typed.
    panel.set_selected_items([note])
    assert _size_spin(panel).value() == pytest.approx(note.em_height_cm, abs=0.5)


@pytest.mark.parametrize("stored", STORED + [round(0.1 * step, 1) for step in range(1, 101)])
def test_a_stored_size_survives_the_panel(qtbot, stored: float) -> None:
    """Showing a note changes nothing; retyping the shown size keeps its font."""
    scene, note = _scene(stored)
    points = note.font().pointSize()
    before = _picture(scene) if stored in STORED else None

    panel, manager = _panel(note)
    qtbot.addWidget(panel)
    assert note.font_size == stored, "selecting a note rewrote its size"
    assert not manager.can_undo

    spin = _size_spin(panel)
    shown = spin.value()
    spin.setValue(shown + 40.0)
    assert note.font().pointSize() != points
    spin.setValue(shown)
    assert note.font().pointSize() == points, (
        f"stored {stored}: shown as {shown:g} cm, retyped, and the font went from "
        f"{points} pt to {note.font().pointSize()} pt"
    )
    if before is not None:
        assert np.array_equal(_picture(scene), before), "the note is drawn differently"

    # Undo goes back to the stored number itself, not to a converted one.
    manager.undo()
    manager.undo()
    assert note.font_size == stored


def test_the_smallest_and_largest_sizes_the_panel_offers_are_real(qtbot) -> None:
    _scene_, note = _scene(1.0)
    panel, _manager = _panel(note)
    qtbot.addWidget(panel)
    spin = _size_spin(panel)
    spin.setValue(spin.minimum())
    assert note.em_height_cm == pytest.approx(spin.minimum(), abs=1.0)
    spin.setValue(spin.maximum())
    assert note.em_height_cm == pytest.approx(spin.maximum(), abs=1.0)
    for value in (spin.minimum(), spin.minimum() + spin.singleStep(), 37.0, 37.0 + spin.singleStep()):
        spin.setValue(value)
        before = note.em_height_cm
        spin.stepBy(1)
        assert note.em_height_cm > before, f"one step up from {value:g} cm changes nothing"


@pytest.mark.parametrize("example", ["balcony", "food-forest", "raised-bed"])
def test_a_bundled_examples_note_is_saved_as_it_was_loaded(qtbot, tmp_path, example: str) -> None:
    """Opening, showing and saving a plan leaves its stored text sizes alone."""
    scene = CanvasScene()
    manager = ProjectManager()
    manager.load(scene, BUNDLED_EXAMPLES / f"{example}.ogp", as_template=True)
    notes = [item for item in scene.items() if isinstance(item, TextItem)]
    assert notes, "the example has a note"
    stored = {str(note.item_id): note.font_size for note in notes}

    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    for note in notes:
        panel.set_selected_items([note])
    target = tmp_path / f"{example}.ogp"
    manager.save(scene, target)

    reloaded_scene = CanvasScene()
    ProjectManager().load(reloaded_scene, target)
    reloaded = {
        str(item.item_id): item.font_size
        for item in reloaded_scene.items() if isinstance(item, TextItem)
    }
    assert reloaded == stored
