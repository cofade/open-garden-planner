"""UI tests for the CompanionCheckDialog (US-10.4)."""

import pytest

from open_garden_planner.services.companion_planting_service import (
    ANTAGONISTIC,
    BENEFICIAL,
    CompanionPlantingService,
    CompanionRelationship,
)
from open_garden_planner.ui.dialogs.companion_check_dialog import (
    CompanionCheckDialog,
    PlantPairResult,
    analyse_plan,
)


@pytest.fixture()
def service() -> CompanionPlantingService:
    return CompanionPlantingService()


def _make_pair(
    name_a: str, name_b: str, rel_type: str, distance: float = 100.0
) -> PlantPairResult:
    return PlantPairResult(
        plant_a_name=name_a,
        plant_b_name=name_b,
        relationship=CompanionRelationship(
            plant_a=name_a.lower(),
            plant_b=name_b.lower(),
            type=rel_type,
            reason="test reason",
        ),
        distance_cm=distance,
    )


class TestCompanionCheckDialogCreation:
    def test_creates_empty_report(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        dialog = CompanionCheckDialog([], [], service)
        qtbot.addWidget(dialog)
        assert dialog is not None
        assert dialog.windowTitle()

    def test_creates_with_conflicts(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        bad = [_make_pair("Tomato", "Fennel", ANTAGONISTIC, 150.0)]
        dialog = CompanionCheckDialog([], bad, service)
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_creates_with_beneficial(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        good = [_make_pair("Tomato", "Basil", BENEFICIAL, 50.0)]
        dialog = CompanionCheckDialog(good, [], service)
        qtbot.addWidget(dialog)
        assert dialog is not None


class TestCompatibilityScore:
    def test_all_good_returns_100(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        good = [_make_pair("Tomato", "Basil", BENEFICIAL)]
        dialog = CompanionCheckDialog(good, [], service)
        qtbot.addWidget(dialog)
        assert dialog._compute_score() == 100

    def test_all_bad_returns_0(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        bad = [_make_pair("Tomato", "Fennel", ANTAGONISTIC)]
        dialog = CompanionCheckDialog([], bad, service)
        qtbot.addWidget(dialog)
        assert dialog._compute_score() == 0

    def test_mixed_returns_ratio(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        good = [
            _make_pair("Tomato", "Basil", BENEFICIAL),
            _make_pair("Carrot", "Onion", BENEFICIAL),
            _make_pair("Lettuce", "Radish", BENEFICIAL),
        ]
        bad = [_make_pair("Tomato", "Fennel", ANTAGONISTIC)]
        dialog = CompanionCheckDialog(good, bad, service)
        qtbot.addWidget(dialog)
        assert dialog._compute_score() == 75

    def test_empty_returns_100(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        dialog = CompanionCheckDialog([], [], service)
        qtbot.addWidget(dialog)
        assert dialog._compute_score() == 100


class TestRowClickSelection:
    def test_row_click_selects_items_on_scene(
        self, qtbot, service: CompanionPlantingService  # noqa: ARG002
    ) -> None:
        from PyQt6.QtWidgets import QGraphicsScene

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        scene = QGraphicsScene()
        tomato = CircleItem(100.0, 100.0, 25.0, object_type=ObjectType.TREE)
        tomato.plant_species = "tomato"
        scene.addItem(tomato)

        fennel = CircleItem(150.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
        fennel.plant_species = "fennel"
        scene.addItem(fennel)

        bad = [PlantPairResult(
            plant_a_name="Tomato",
            plant_b_name="Fennel",
            relationship=CompanionRelationship(
                plant_a="tomato", plant_b="fennel",
                type=ANTAGONISTIC, reason="test",
            ),
            distance_cm=50.0,
            items=[tomato, fennel],
        )]

        dialog = CompanionCheckDialog([], bad, service, scene=scene)
        qtbot.addWidget(dialog)

        # Find the table and select the first row
        from PyQt6.QtWidgets import QTableWidget
        tables = dialog.findChildren(QTableWidget)
        assert len(tables) == 1
        tables[0].selectRow(0)

        # Both plants should now be selected
        assert tomato.isSelected()
        assert fennel.isSelected()


class TestAnalysePlan:
    def test_finds_antagonistic_pair(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        from PyQt6.QtWidgets import QGraphicsScene

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        scene = QGraphicsScene()

        tomato = CircleItem(100.0, 100.0, 25.0, object_type=ObjectType.TREE)
        tomato.plant_species = "tomato"
        scene.addItem(tomato)

        fennel = CircleItem(150.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
        fennel.plant_species = "fennel"
        scene.addItem(fennel)

        def species_fn(item: object) -> str:
            return getattr(item, "plant_species", "") or ""

        def is_plant(item: object) -> bool:
            return hasattr(item, "plant_species") and is_plant_type(
                getattr(item, "object_type", None)
            )

        beneficial, antagonistic = analyse_plan(
            scene=scene,
            service=service,
            radius_cm=200.0,
            species_name_fn=species_fn,
            is_plant_fn=is_plant,
        )
        assert len(antagonistic) == 1
        assert antagonistic[0].relationship.type == ANTAGONISTIC
        assert len(antagonistic[0].items) == 2

    def test_finds_beneficial_pair(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        from PyQt6.QtWidgets import QGraphicsScene

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        scene = QGraphicsScene()

        tomato = CircleItem(100.0, 100.0, 25.0, object_type=ObjectType.TREE)
        tomato.plant_species = "tomato"
        scene.addItem(tomato)

        basil = CircleItem(150.0, 100.0, 15.0, object_type=ObjectType.SHRUB)
        basil.plant_species = "basil"
        scene.addItem(basil)

        def species_fn(item: object) -> str:
            return getattr(item, "plant_species", "") or ""

        def is_plant(item: object) -> bool:
            return hasattr(item, "plant_species") and is_plant_type(
                getattr(item, "object_type", None)
            )

        beneficial, antagonistic = analyse_plan(
            scene=scene,
            service=service,
            radius_cm=200.0,
            species_name_fn=species_fn,
            is_plant_fn=is_plant,
        )
        assert len(beneficial) == 1
        assert beneficial[0].relationship.type == BENEFICIAL
        assert len(antagonistic) == 0

    def test_out_of_range_ignored(self, qtbot, service: CompanionPlantingService) -> None:  # noqa: ARG002
        from PyQt6.QtWidgets import QGraphicsScene

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        scene = QGraphicsScene()

        tomato = CircleItem(0.0, 0.0, 25.0, object_type=ObjectType.TREE)
        tomato.plant_species = "tomato"
        scene.addItem(tomato)

        fennel = CircleItem(500.0, 500.0, 15.0, object_type=ObjectType.SHRUB)
        fennel.plant_species = "fennel"
        scene.addItem(fennel)

        def species_fn(item: object) -> str:
            return getattr(item, "plant_species", "") or ""

        def is_plant(item: object) -> bool:
            return hasattr(item, "plant_species") and is_plant_type(
                getattr(item, "object_type", None)
            )

        beneficial, antagonistic = analyse_plan(
            scene=scene,
            service=service,
            radius_cm=200.0,
            species_name_fn=species_fn,
            is_plant_fn=is_plant,
        )
        assert len(beneficial) == 0
        assert len(antagonistic) == 0
