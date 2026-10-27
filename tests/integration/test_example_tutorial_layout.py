"""Tutorial notes are real editable plan content and fit the plan in every locale."""

import pytest

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.example_library import bundled_examples
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.text_item import TextItem


@pytest.mark.parametrize("language", ["en", "de", "es"])
def test_every_tutorial_annotation_stays_inside_its_canvas(qtbot, language):
    for entry in bundled_examples(language):
        scene = CanvasScene()
        manager = ProjectManager()
        manager.load(scene, entry.path, as_template=True)
        notes = [item for item in scene.items() if isinstance(item, TextItem)]
        assert notes, entry.path
        for note in notes:
            assert scene.canvas_rect.contains(note.sceneBoundingRect()), (
                entry.path, note.sceneBoundingRect(), scene.canvas_rect)
        scene.clear()
