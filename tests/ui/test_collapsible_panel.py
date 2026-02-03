"""Tests for collapsible panel widget."""

from PyQt6.QtWidgets import QLabel

from open_garden_planner.ui.widgets import CollapsiblePanel


def test_collapsible_panel_creation(qtbot):  # noqa: ARG001
    """Test that a collapsible panel can be created."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)

    assert panel is not None
    assert panel.is_expanded()


def test_collapsible_panel_toggle(qtbot):
    """Test toggling the panel state."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)
    qtbot.addWidget(panel)
    panel.show()

    # Initially expanded
    assert panel.is_expanded()
    assert content.isVisible()

    # Toggle to collapse
    panel.toggle()
    assert not panel.is_expanded()
    assert not content.isVisible()

    # Toggle back to expand
    panel.toggle()
    assert panel.is_expanded()
    assert content.isVisible()


def test_collapsible_panel_expand_collapse(qtbot):
    """Test expand and collapse methods."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=False)
    qtbot.addWidget(panel)
    panel.show()

    # Initially collapsed
    assert not panel.is_expanded()
    assert not content.isVisible()

    # Expand
    panel.expand()
    assert panel.is_expanded()
    assert content.isVisible()

    # Collapse
    panel.collapse()
    assert not panel.is_expanded()
    assert not content.isVisible()


def test_collapsible_panel_set_content(qtbot):
    """Test setting content after creation."""
    panel = CollapsiblePanel("Test Panel", expanded=True)
    qtbot.addWidget(panel)
    panel.show()

    # No content initially
    assert panel._content_widget is None

    # Set content
    content = QLabel("New Content")
    panel.set_content(content)

    assert panel._content_widget is content
    assert content.isVisible()


def test_collapsible_panel_signal(qtbot):  # noqa: ARG001
    """Test that expanded_changed signal is emitted."""
    content = QLabel("Test Content")
    panel = CollapsiblePanel("Test Panel", content, expanded=True)

    # Track signal emissions
    expanded_states = []

    def on_expanded_changed(expanded: bool):
        expanded_states.append(expanded)

    panel.expanded_changed.connect(on_expanded_changed)

    # Toggle should emit signal
    panel.toggle()
    assert len(expanded_states) == 1
    assert expanded_states[0] is False

    # Another toggle
    panel.toggle()
    assert len(expanded_states) == 2
    assert expanded_states[1] is True
