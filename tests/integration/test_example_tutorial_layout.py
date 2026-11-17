"""Tutorial notes are real editable plan content and fit the plan in every locale."""

import pytest

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.example_library import bundled_examples
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.text_item import TextItem


@pytest.mark.parametrize("language", ["en", "de", "es"])
def test_balcony_note_does_not_run_under_furniture(qtbot, language):
    from open_garden_planner.core.furniture_renderer import is_furniture_type
    from open_garden_planner.core.item_geometry import object_outline
    from open_garden_planner.core.object_types import ObjectType

    entry = next(entry for entry in bundled_examples(language) if entry.path.stem == "balcony")
    scene = CanvasScene()
    ProjectManager().load(scene, entry.path, as_template=True)
    note = next(item for item in scene.items() if isinstance(item, TextItem))
    for item in scene.items():
        kind = getattr(item, "object_type", None)
        if is_furniture_type(kind) or kind is ObjectType.PARASOL:
            outline = item.sceneTransform().map(object_outline(item))
            assert not outline.intersects(note.sceneBoundingRect()), (item.name, language)


@pytest.mark.parametrize("language", ["en", "de", "es"])
def test_every_tutorial_annotation_stays_inside_its_canvas(qtbot, language):
    for entry in bundled_examples(language):
        scene = CanvasScene()
        manager = ProjectManager()
        manager.load(scene, entry.path, as_template=True)
        notes = [item for item in scene.items() if isinstance(item, TextItem)]
        if entry.path.stem == "family-garden":
            assert not notes, "the 3D showcase teaches nothing: it has no tutorial note"
            scene.clear()
            continue
        assert notes, entry.path
        for note in notes:
            assert scene.canvas_rect.contains(note.sceneBoundingRect()), (
                entry.path, note.sceneBoundingRect(), scene.canvas_rect)
        scene.clear()
