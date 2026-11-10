"""Panels, rows and toolbars keep their content in view (#796).

One test per layout defect the issue names, each measuring the real widget:

* a stylesheet minimum width beats ``setFixedWidth`` (the root of four of them);
* the calendar's "Today's Tasks" showed one and a half rows of eighteen;
* the Tasks tab's date and arrow columns shifted with the number of buttons;
* Find Plants cut the descenders of its second line;
* the Properties panel and its Arrange row were cut at the right edge, and the
  Crop Rotation panel spread its lines over the panel's whole height;
* the Constraints header's "delete all" was a 6 px mark;
* the Plan / 3D / Split switch covered the plan's top-left corner;
* at 1280 px the toolbar lost three category buttons and the search field, and
  the sidebar kept 35 % of the window;
* the soil overlay had no key to its colours.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core import i18n
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.soil_service import HealthLevel
from open_garden_planner.services.task_generator import Task
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.constraints_panel import ConstraintsPanel
from open_garden_planner.ui.panels.plant_search_panel import PlantListItem
from open_garden_planner.ui.theme import (
    ThemeMode,
    apply_theme,
    list_row_size_hint,
    set_compact,
)
from open_garden_planner.ui.views import planting_calendar_view as calendar
from open_garden_planner.ui.views.tasks_view import TasksView
from open_garden_planner.ui.widgets.elided_label import ElidedLabel
from open_garden_planner.ui.widgets.toolbar_rows import rows_for_width
from tests.chrome_measure import clipped_labels, grab_image, ink_contrast

EXAMPLES = (Path(__file__).parents[2] / "src" / "open_garden_planner" / "resources" / "examples")

#: qtbot keeps a weak reference only: a host nobody holds takes its children with it
_HOSTS: list[QWidget] = []


@pytest.fixture(autouse=True)
def _themed(qapp: QApplication):
    """The app stylesheet is what these defects come from: every test has it."""
    apply_theme(qapp, ThemeMode.LIGHT)
    yield
    _HOSTS.clear()


def _host(qtbot, *children: QWidget, width: int = 900, height: int = 500) -> QWidget:
    host = QWidget()
    _HOSTS.append(host)
    layout = QVBoxLayout(host)
    for child in children:
        layout.addWidget(child)
    qtbot.addWidget(host)
    host.resize(width, height)
    host.show()
    qtbot.waitExposed(host)
    return host


def _window(qtbot, monkeypatch, width: int = 1280, height: int = 720):
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda _self: None)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    window.showNormal()
    window.resize(width, height)
    qtbot.waitExposed(window)
    qtbot.wait(120)   # the toolbar rows and the sidebar share settle after the events
    return window


def _right_edge(widget: QWidget, ancestor: QWidget) -> int:
    return widget.mapTo(ancestor, QPoint(widget.width(), 0)).x()


# ── The root: a stylesheet minimum beats a fixed size ────────────────────────

def test_a_compact_button_keeps_the_size_its_code_asks_for(qtbot) -> None:
    """``setFixedSize(26, 20)`` gave a 110 px button: the stylesheet's
    ``min-width: 80px`` (plus padding and border) wins over the code."""
    plain, compact, text = QPushButton(), QPushButton(), QPushButton("Done")
    plain.setFixedSize(26, 20)
    compact.setFixedSize(26, 20)
    set_compact(compact)
    set_compact(text)
    _host(qtbot, plain, compact, text)

    assert plain.width() >= 100          # the trap, as it stands for dialog buttons
    assert (compact.width(), compact.height()) == (26, 20)
    assert text.sizeHint().width() < 80  # a row button is as wide as its text


# ── Calendar: "Today's Tasks" ────────────────────────────────────────────────

def _dashboard_tasks(count: int, frost_every: int = 0) -> list[calendar._DashboardTask]:
    day = datetime.date(2026, 6, 21)
    return [
        calendar._DashboardTask(
            f"k{i}:harvest:2026",
            "frost_alert_red" if frost_every and i % frost_every == 0 else "harvest",
            f"Plant {i}", day, day, "today" if i < count // 2 else "this_week", f"k{i}")
        for i in range(count)
    ]


def test_todays_tasks_shows_whole_rows_not_one_and_a_half(qtbot, qapp) -> None:
    """Eighteen tasks got 65 px: ``QScrollArea`` remembers its first size hint,
    taken while the list was empty."""
    dashboard = calendar._DashboardPanel()
    filler = QScrollArea()          # the Gantt below it takes all spare height
    host = _host(qtbot, dashboard, filler, width=1200, height=700)
    host.layout().setStretch(1, 1)
    qapp.processEvents()
    empty_height = dashboard._content_scroll.height()

    dashboard.set_data(_dashboard_tasks(18))
    qtbot.waitUntil(
        lambda: dashboard._content_scroll.height() > calendar._DASHBOARD_MIN_H, timeout=3000)
    scroll = dashboard._content_scroll
    row_height = scroll.widget().findChildren(QPushButton)[0].parentWidget().height()
    assert scroll.height() == calendar._DASHBOARD_MAX_H + 2 * scroll.frameWidth()
    assert scroll.height() >= 4 * row_height > 0
    assert empty_height < row_height        # what the list used to keep

    # Two tasks: exactly their height, no empty band and no scroll bar.
    dashboard.set_data(_dashboard_tasks(2))
    qtbot.waitUntil(lambda: scroll.height() < calendar._DASHBOARD_MIN_H + 20, timeout=3000)
    assert scroll.height() == scroll.widget().sizeHint().height() + 2 * scroll.frameWidth()
    assert scroll.verticalScrollBar().maximum() == 0


def test_todays_tasks_rows_keep_one_date_and_arrow_column(qtbot, qapp) -> None:
    """A frost alert has no Done button; its date and arrow must not move right."""
    dashboard = calendar._DashboardPanel()
    _host(qtbot, dashboard, QScrollArea(), width=1200, height=700)
    dashboard.set_data(_dashboard_tasks(6, frost_every=2))
    qtbot.wait(80)
    rows = [button.parentWidget() for button in dashboard.findChildren(QPushButton)
            if button.objectName() == "taskDoneBtn"]
    assert len(rows) == 6
    arrows = {row.findChildren(QPushButton)[0].x() for row in rows}
    hidden = [row for row in rows if row.findChildren(QPushButton)[1].isHidden()]
    assert len(hidden) == 3                       # the frost alerts
    assert len(arrows) == 1, arrows
    # The arrow is the small button the code asks for (26 px at most), not a
    # 110 px one.
    widths = {row.findChildren(QPushButton)[0].width() for row in rows}
    assert len(widths) == 1 and 16 <= widths.pop() <= 26


def test_one_long_task_does_not_push_every_row_out_of_view(qtbot, qapp) -> None:
    """A frost alert that names twenty plants is wider than the window; a plain
    label is never narrower than its text, so the date, the arrow and Done of
    EVERY row were out of view at 1280 px."""
    dashboard = calendar._DashboardPanel()
    _host(qtbot, dashboard, QScrollArea(), width=900, height=600)
    tasks = _dashboard_tasks(4)
    day = tasks[0].task_date
    long_name = "Frost 2.0°C — " + ", ".join(["Runner Bean", "Sweet Pepper", "Tomato"] * 12)
    tasks[1] = calendar._DashboardTask("frost:1", "frost_alert_red", long_name, day, day,
                                       "today", "x")
    dashboard.set_data(tasks)
    qtbot.wait(80)

    buttons = [b for b in dashboard.findChildren(QPushButton) if b.objectName() == "taskDoneBtn"]
    assert len(buttons) == 4
    for button in buttons:
        assert _right_edge(button, dashboard) <= dashboard.width()
    long_label = next(label for label in dashboard.findChildren(ElidedLabel)
                      if label.text() == long_name)
    assert long_label.width() < long_label.fontMetrics().horizontalAdvance(long_name)
    assert long_label.toolTip() == long_name       # the cut text is still readable


# ── Tasks tab ────────────────────────────────────────────────────────────────

def test_a_long_task_title_keeps_the_tasks_tab_buttons_in_view(qtbot, qapp) -> None:
    view = TasksView(CanvasScene(), ProjectManager())
    _host(qtbot, view, width=700, height=400)
    day = datetime.date(2026, 6, 21)
    task = Task("m", "manual", "manual", "Order seeds", notes="tomato, pepper, bean, " * 30,
                start_date=day, end_date=day, species_key="x")
    view._clear_content()
    view._action_boxes = []
    row = view._build_row(task, "#43a047", snoozed=False, is_done=False)
    view._content_layout.insertWidget(view._content_layout.count() - 1, row)
    view._align_action_columns()
    qapp.processEvents()

    box = view._action_boxes[0]
    assert _right_edge(box, view) <= view.width()
    assert all(button.isVisible() for button in box.findChildren(QPushButton))


def test_the_tasks_tab_keeps_its_columns_with_two_three_and_four_buttons(qtbot, qapp) -> None:
    """Right-aligned, every extra button pushed its row's date and arrow left."""
    view = TasksView(CanvasScene(), ProjectManager())
    _host(qtbot, view, width=1200, height=500)
    day = datetime.date(2026, 6, 21)
    tasks = [
        Task("a", "calendar", "harvest", "Harvest tomato", start_date=day, end_date=day,
             species_key="tomato", dismissible=False),                     # Done, Snooze
        Task("b", "weather", "frost_alert_red", "Frost 0.3°C", start_date=day, end_date=day,
             species_key="x"),                                             # + Dismiss
        Task("c", "manual", "manual", "Buy compost", start_date=day, end_date=day,
             species_key="y"),                                             # + Edit, Delete
        Task("d", "manual", "manual", "No date, nowhere to go"),           # no date, no arrow
    ]
    view._clear_content()
    view._action_boxes = []
    rows = [view._build_row(task, "#43a047", snoozed=False, is_done=False) for task in tasks]
    for row in rows:
        view._content_layout.insertWidget(view._content_layout.count() - 1, row)
    view._align_action_columns()
    qapp.processEvents()

    button_counts = [len(box.findChildren(QPushButton)) for box in view._action_boxes]
    assert button_counts == [2, 3, 4, 4]
    assert len({box.width() for box in view._action_boxes}) == 1
    assert len({box.x() for box in view._action_boxes}) == 1
    dates = [row.findChildren(QLabel)[2] for row in rows]
    arrows = [row.findChildren(QPushButton)[0] for row in rows]
    assert len({label.x() for label in dates}) == 1, [label.x() for label in dates]
    assert len({button.x() for button in arrows}) == 1, [button.x() for button in arrows]
    assert {button.width() for button in arrows} == {28}
    # No button is cut: each is at least as wide as its text needs.
    for box in view._action_boxes:
        for button in box.findChildren(QPushButton):
            assert button.width() >= button.sizeHint().width()


# ── Find Plants ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("point_size", [10, 13, 15], ids=["100%", "125%", "150%"])
def test_find_plants_rows_keep_their_descenders(qtbot, qapp, point_size) -> None:
    """The row was sized to the widget's hint; the list's item padding then took
    10 px back and the second line ("novi-belgii") lost its descenders."""
    from uuid import uuid4

    from PyQt6.QtWidgets import QListWidget, QListWidgetItem

    font = qapp.font()
    qapp.setFont(QFont(font.family(), point_size))
    try:
        rows = QListWidget()
        widget = PlantListItem(uuid4(), "New York Aster", "Symphyotrichum novi-belgii",
                               ObjectType.PERENNIAL)
        item = QListWidgetItem()
        item.setSizeHint(list_row_size_hint(widget))      # as the panel does
        rows.addItem(item)
        rows.setItemWidget(item, widget)
        _host(qtbot, rows, width=420, height=260)
        qapp.processEvents()

        assert widget.height() >= widget.sizeHint().height()
        assert clipped_labels(rows) == []
    finally:
        qapp.setFont(font)


# ── Crop Rotation ────────────────────────────────────────────────────────────

def test_crop_rotation_lines_sit_under_each_other(qtbot, qapp) -> None:
    """The open accordion section's spare height was shared out between the
    wrapped labels: 90 px of nothing between two lines of text."""
    from open_garden_planner.services.crop_rotation_service import CropRotationService
    from open_garden_planner.ui.panels.crop_rotation_panel import CropRotationPanel

    panel = CropRotationPanel(CropRotationService())
    panel._status_label.setText("Raised bed 3: No History")
    panel._recommendation_label.setText("No planting history — any crop is suitable.")
    panel._suggest_label.setText("Next: Heavy Feeder")
    _host(qtbot, panel, width=450, height=800)     # far taller than the content
    qapp.processEvents()

    lines = (panel._status_label, panel._recommendation_label, panel._suggest_label)
    for upper, lower in zip(lines, lines[1:], strict=False):
        gap = lower.y() - (upper.y() + upper.height())
        assert gap <= 12, f"{gap} px between {upper.text()!r} and {lower.text()!r}"
    for label in lines:
        assert label.height() <= label.sizeHint().height() + 4, label.text()
    # The three row buttons are as wide as their text and stay inside the panel.
    for button in (panel._add_record_btn, panel._edit_record_btn, panel._delete_record_btn):
        assert button.width() >= button.sizeHint().width()
        assert _right_edge(button, panel) <= panel.width()


# ── Constraints header ───────────────────────────────────────────────────────

def test_the_constraints_delete_all_button_is_a_readable_icon(qtbot, qapp) -> None:
    """It was the character "×" in a 20 px button with 4 px padding: a 6 px mark."""
    panel = ConstraintsPanel()
    button = panel.delete_all_button
    _host(qtbot, panel, button, width=300, height=200)

    assert button.objectName() == "constraintsDeleteAllBtn"   # bound in the stylesheet
    assert button.text() == "" and not button.icon().isNull()
    assert button.iconSize().width() == 16
    assert not button.isEnabled()                 # nothing to delete yet

    panel._show_empty(False)
    qapp.processEvents()
    assert button.isEnabled()
    # The bin is drawn at least 10 px wide: count the columns that carry ink.
    image = grab_image(button)
    background = image.pixelColor(0, 0)
    inked = [x for x in range(image.width())
             if any(image.pixelColor(x, y) != background for y in range(image.height()))]
    assert inked and inked[-1] - inked[0] >= 10
    assert ink_contrast(image) >= 3.0


# ── The main window ──────────────────────────────────────────────────────────

def test_toolbars_wrap_instead_of_hiding_tools_at_1280(qtbot, monkeypatch) -> None:
    """Three category buttons and the search field went into the overflow popup."""
    window = _window(qtbot, monkeypatch, 1280, 720)
    main, constraints, categories = (
        window.main_toolbar, window.constraint_toolbar, window.category_toolbar)
    widths = [bar.sizeHint().width() for bar in (main, constraints, categories)]
    assert sum(widths) > 1280                       # the premise: one row cannot hold them
    assert rows_for_width(widths, 1280) == [False, False, True]

    assert window.toolBarBreak(categories) and not window.toolBarBreak(constraints)
    assert categories.y() > main.y() == constraints.y()
    for bar in (main, constraints, categories):
        overflow = [b for b in bar.findChildren(QToolButton)
                    if b.objectName() == "qt_toolbar_ext_button" and b.isVisible()]
        assert overflow == [], bar.objectName()
        for button in bar.findChildren(QToolButton):
            if button.objectName() != "qt_toolbar_ext_button" and button.parentWidget() is bar:
                assert button.isVisible(), button.toolTip()
    search = categories._search_field
    assert search.isVisible() and _right_edge(search, window) <= window.width()

    # Wide enough again: one row, as before.
    window.resize(1920, 1000)
    qtbot.wait(120)
    assert not window.toolBarBreak(categories)
    assert categories.y() == main.y()


def test_the_sidebar_keeps_the_width_its_widest_form_needs(qtbot, monkeypatch) -> None:
    """A recorded decision, not a fix: #796 found the sidebar at 35 % of a
    1280 px window. A share of the window (30 % = 384 px) was built and
    measured: the Properties form has no horizontal scroll bar and its German
    rows ("Beschriftung auf der Leinwand anzeigen", "Muster-Versatz") need 388
    to 406 px, so it was cut again. The default stays 450 px until the form can
    be narrower; ``test_the_selection_panels_fit_the_sidebar`` is what fails
    when it is lowered."""
    window = _window(qtbot, monkeypatch, 1280, 720)
    assert window.sidebar.width() == pytest.approx(450, abs=3)


def test_the_mode_switch_sits_on_the_tab_row_and_covers_nothing_of_the_plan(
        qtbot, monkeypatch) -> None:
    """It floated over the canvas at (28, 28), on top of the plan's corner."""
    window = _window(qtbot, monkeypatch, 1280, 720)
    switch = window._workspace._floating
    assert switch.isVisible()
    assert [button.text() for button in switch.buttons] == ["Plan", "3D", "Split"]

    canvas = window.canvas_view
    canvas_rect = QRect(canvas.mapTo(window, QPoint(0, 0)), canvas.size())
    switch_rect = QRect(switch.mapTo(window, QPoint(0, 0)), switch.size())
    assert not canvas_rect.intersects(switch_rect)
    assert switch_rect.bottom() <= canvas_rect.top()
    assert _right_edge(switch, window) <= window.width()

    # It belongs to the plan: gone on the other tabs, back on the plan's.
    window._tab_widget.setCurrentWidget(window.tasks_view)
    qtbot.wait(30)
    assert not switch.isVisible()
    window._tab_widget.setCurrentIndex(0)
    qtbot.wait(30)
    assert switch.isVisible()


def test_the_soil_overlay_has_a_key_to_its_colours(qtbot, monkeypatch) -> None:
    window = _window(qtbot, monkeypatch, 1280, 720)
    legend = window._soil_overlay_legend
    assert not legend.isVisible()

    window._on_toggle_soil_overlay(True)
    qtbot.wait(150)
    assert legend.isVisible()
    assert [legend.labels[level].text() for level in HealthLevel] == [
        "Good", "Fair", "Poor", "No soil test"]
    # In view, not in the toolbar's overflow popup — at 1280 and at 1920.
    for width in (1280, 1920):
        window.resize(width, 800)
        qtbot.wait(150)
        last = legend.labels[HealthLevel.UNKNOWN]
        assert last.isVisible() and _right_edge(last, window) <= window.width(), width
        search = window.category_toolbar._search_field
        assert search.width() >= search.minimumSizeHint().width()

    window._on_toggle_soil_overlay(False)
    qtbot.wait(150)
    assert not legend.isVisible()


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_selection_panels_fit_the_sidebar(qtbot, monkeypatch, language) -> None:
    """Properties' Arrange row was four 110 px buttons in a 440 px panel with no
    horizontal scroll bar: the row and every field above it were cut. Crop
    Rotation spread three lines over the panel's whole height."""
    i18n.load_translator(QApplication.instance(), language)
    try:
        window = _window(qtbot, monkeypatch, 1280, 720)
        scene = window.canvas_scene
        bed = RectangleItem(100, 100, 300, 120, object_type=ObjectType.RAISED_BED,
                            layer_id=scene.active_layer.id)
        scene.addItem(bed)
        bed.setSelected(True)
        qtbot.wait(500)

        window._sidebar_controller._on_title_click("properties")
        qtbot.wait(450)
        panel = window.properties_panel
        buttons = [panel.findChild(QPushButton, name) for name in (
            "arrange_front_button", "arrange_forward_button",
            "arrange_backward_button", "arrange_back_button")]
        assert all(button is not None for button in buttons)
        for button in buttons:
            assert button.minimumSizeHint().width() < 80       # not a dialog button
            assert _right_edge(button, panel) <= panel.width(), button.objectName()
        widths = [button.width() for button in buttons]
        assert max(widths) - min(widths) <= 1                  # they share the row evenly
        assert clipped_labels(panel) == []

        rotation = window.crop_rotation_panel
        window._sidebar_controller._on_title_click("crop_rotation")
        qtbot.wait(450)
        if rotation.isVisible():
            # The lines sit under each other: no label is taller than its text.
            for label in (rotation._status_label, rotation._recommendation_label,
                          rotation._suggest_label):
                assert label.height() <= label.sizeHint().height() + 6, label.text()
            row = rotation._add_record_btn.parentWidget()
            for button in (rotation._add_record_btn, rotation._edit_record_btn,
                           rotation._delete_record_btn):
                assert _right_edge(button, row) <= row.width()
                assert button.width() >= button.sizeHint().width()
    finally:
        i18n.load_translator(QApplication.instance(), "en")


def test_find_plants_in_the_window_shows_whole_rows(qtbot, monkeypatch) -> None:
    window = _window(qtbot, monkeypatch, 1280, 720)
    window._load_project_file(str(EXAMPLES / "family-garden.ogp"))
    qtbot.wait(300)
    window._sidebar_controller._on_title_click("plant_search")
    panel = window.plant_search_panel
    qtbot.waitUntil(lambda: panel.results_list.count() > 5 and panel.height() > 150, timeout=8000)
    qtbot.wait(350)
    assert clipped_labels(panel.results_list) == []
