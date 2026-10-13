"""Independent presentation contracts for every constraint type (#457)."""

from uuid import uuid4

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator
from PyQt6.QtWidgets import QLabel

from open_garden_planner.core.constraints import ConstraintType
from open_garden_planner.ui.constraint_presentation import CONSTRAINT_DESCRIPTORS
from open_garden_planner.ui.panels.constraints_panel import ConstraintListItem

EXPECTED = {
    "DISTANCE": ("A – B   1.20 m", "A to B: 1.20 m", "constraint_distance"),
    "EDGE_LENGTH": ("A   Edge 1.20 m", "A edge length: 1.20 m", "constraint_edge_length"),
    "HORIZONTAL": ("A – B   Horizontal", "A horizontal align B", "constraint_horizontal"),
    "VERTICAL": ("A – B   Vertical", "A vertical align B", "constraint_vertical"),
    "ANGLE": ("A – B – …   120.0°", "Angle A–B–…: 120.0°", "constraint_angle"),
    "SYMMETRY_HORIZONTAL": ("A – B   Symmetric", "A symmetric to B about the horizontal axis", "constraint_symmetric"),
    "SYMMETRY_VERTICAL": ("A – B   Symmetric", "A symmetric to B about the vertical axis", "constraint_symmetric"),
    "COINCIDENT": ("A – B   Coincident", "A coincident with B", "constraint_coincident"),
    "PARALLEL": ("A – B   Parallel", "A parallel to B", "constraint_parallel"),
    "PERPENDICULAR": ("A – B   Perpendicular", "A perpendicular to B", "constraint_perpendicular"),
    "EQUAL": ("A – B   Equal", "A equal size to B", "constraint_equal"),
    "FIXED": ("A   Fixed", "A is fixed in place", "constraint_fixed"),
    "HORIZONTAL_DISTANCE": ("A – B   1.20 m", "A to B: horizontal distance 1.20 m", "constraint_h_distance"),
    "VERTICAL_DISTANCE": ("A – B   1.20 m", "A to B: vertical distance 1.20 m", "constraint_v_distance"),
    "POINT_ON_EDGE": ("A – B   On edge", "A lies on the edge of B", "snap_nearest"),
    "POINT_ON_CIRCLE": ("A – B   On circle", "A lies on the circle of B", "snap_tangent"),
    "TANGENT": ("A – B   Tangent", "A tangent to B (r=1.20 m)", "snap_tangent"),
}


def test_descriptor_enum_coverage_and_immutability():
    assert set(CONSTRAINT_DESCRIPTORS) == set(ConstraintType)
    assert set(EXPECTED) == set(ConstraintType.__members__)
    with pytest.raises(TypeError):
        CONSTRAINT_DESCRIPTORS[ConstraintType.DISTANCE] = None
    with pytest.raises(AttributeError):
        CONSTRAINT_DESCRIPTORS[ConstraintType.DISTANCE].icon_name = "wrong"


@pytest.mark.parametrize("name", list(EXPECTED))
def test_each_row_preserves_text_tooltip_and_icon(qtbot, name):
    row = ConstraintListItem(uuid4(), "A", "B", 120.0, True, name)
    qtbot.addWidget(row)
    labels = [label for label in row.findChildren(QLabel) if label.text()]
    assert len(labels) == 1
    text, tooltip, icon = EXPECTED[name]
    assert labels[0].text() == text
    assert labels[0].toolTip() == tooltip
    assert row._type_icon_name == icon


@pytest.mark.parametrize("name", list(EXPECTED))
def test_violated_dot_and_fixed_exception(qtbot, name):
    row = ConstraintListItem(uuid4(), "A", "B", 120.0, False, name)
    qtbot.addWidget(row)
    status = row.findChildren(QLabel)[0]
    color = status.pixmap().toImage().pixelColor(7, 7)
    assert (color.red(), color.green(), color.blue()) == (
        (180, 130, 0) if name == "FIXED" else (220, 40, 40)
    )
    assert status.toolTip() == "Violated"


def test_unknown_type_retains_distance_fallback(qtbot):
    row = ConstraintListItem(uuid4(), "A", "B", 120.0, True, "FUTURE_TYPE")
    qtbot.addWidget(row)
    label = next(label for label in row.findChildren(QLabel) if label.text())
    assert label.text() == "A – B   1.20 m"


def test_tangent_displays_absolute_radius(qtbot):
    row = ConstraintListItem(uuid4(), "A", "B", -120.0, True, "TANGENT")
    qtbot.addWidget(row)
    label = next(label for label in row.findChildren(QLabel) if label.text())
    assert label.toolTip() == "A tangent to B (r=1.20 m)"


@pytest.mark.parametrize("target,expected", [(17.5, "0.17 m"), (20.5, "0.20 m")])
@pytest.mark.parametrize("kind", ["DISTANCE", "EDGE_LENGTH", "TANGENT"])
def test_centimetre_rounding_boundaries_preserve_existing_division(qtbot, target, expected, kind):
    row = ConstraintListItem(uuid4(), "A", "B", target, True, kind)
    qtbot.addWidget(row)
    label = next(label for label in row.findChildren(QLabel) if label.text())
    assert expected in label.toolTip()
    if kind != "TANGENT":
        assert label.text().endswith(expected)


def test_german_descriptor_strings_reach_compiled_translator(qtbot):
    from pathlib import Path

    import open_garden_planner

    translator = QTranslator()
    resource = Path(open_garden_planner.__file__).parent / "resources/translations/open_garden_planner_de.qm"
    assert translator.load(str(resource))
    QCoreApplication.installTranslator(translator)
    try:
        for kind, descriptor in CONSTRAINT_DESCRIPTORS.items():
            row = ConstraintListItem(uuid4(), "A", "B", 120.0, True, kind.name)
            qtbot.addWidget(row)
            label = next(label for label in row.findChildren(QLabel) if label.text())
            assert label.toolTip() != EXPECTED[kind.name][1], kind.name
            assert "{a}" not in label.toolTip()
            assert "{d}" not in label.toolTip()
            assert QCoreApplication.translate("ConstraintListItem", descriptor.tooltip_template) != descriptor.tooltip_template
        edge = ConstraintListItem(uuid4(), "A", "B", 120.0, True, "EDGE_LENGTH")
        qtbot.addWidget(edge)
        assert next(label.text() for label in edge.findChildren(QLabel) if label.text()) == "A   Kante 1.20 m"
    finally:
        QCoreApplication.removeTranslator(translator)
