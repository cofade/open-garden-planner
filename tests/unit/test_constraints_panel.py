"""Tests for the constraints manager panel (US-7.6)."""

from uuid import UUID, uuid4

from open_garden_planner.core.constraints import AnchorRef, ConstraintGraph
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin
from open_garden_planner.ui.panels.constraints_panel import (
    ConstraintListItem,
    ConstraintsPanel,
)


class _FakeDLM:
    """Fake DimensionLineManager — always returns None for anchor positions."""

    def _resolve_anchor_position(self, _item_id, _anchor_type, _anchor_index):
        return None


class _FakeScene:
    """Minimal fake CanvasScene for testing the panel without Qt graphics."""

    def __init__(self) -> None:
        self.constraint_graph = ConstraintGraph()
        self._items: list = []

    def items(self):
        return self._items

    @property
    def dimension_line_manager(self):
        return _FakeDLM()


class _FakeItem(GardenItemMixin):
    """Fake GardenItem that subclasses GardenItemMixin for isinstance checks.

    GardenItemMixin.__init__ expects 'self' to also be a QGraphicsItem,
    so we bypass it and manually set the required attributes.
    """

    def __init__(self, item_id: UUID, name: str = "", object_type=None) -> None:
        # Skip GardenItemMixin.__init__ — set attributes directly
        self._item_id = item_id
        self._object_type = object_type
        self._name = name
        self._label_visible = True
        self._global_labels_visible = True
        self._label_item = None
        self._edit_label_item = None
        self._shadows_enabled = False
        self._metadata: dict = {}
        self._stroke_style = None
        self._fill_color = None

    @property
    def item_id(self) -> UUID:
        return self._item_id

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def object_type(self):
        return self._object_type

    def setSelected(self, _selected: bool) -> None:
        pass  # No-op for tests


class TestConstraintsPanel:
    """Tests for the ConstraintsPanel widget."""

    def test_empty_state(self, qtbot) -> None:
        """Panel shows empty label when no constraints exist."""
        panel = ConstraintsPanel()
        scene = _FakeScene()
        panel.set_scene(scene)
        panel.refresh()

        # Use isHidden() to check explicit visibility state (widgets not in
        # a visible window always report isVisible()==False)
        assert not panel._empty_label.isHidden()
        assert panel._list.isHidden()

    def test_shows_constraints(self, qtbot) -> None:
        """Panel lists constraints from the graph."""
        panel = ConstraintsPanel()
        scene = _FakeScene()

        id_a = uuid4()
        id_b = uuid4()
        ref_a = AnchorRef(id_a, AnchorType.CENTER)
        ref_b = AnchorRef(id_b, AnchorType.CENTER)
        scene.constraint_graph.add_constraint(ref_a, ref_b, 200.0)

        scene._items = [
            _FakeItem(id_a, name="Tree A"),
            _FakeItem(id_b, name="Fence B"),
        ]

        panel.set_scene(scene)
        panel.refresh()

        assert panel._empty_label.isHidden()
        assert not panel._list.isHidden()
        assert panel._list.count() == 1

    def test_multiple_constraints(self, qtbot) -> None:
        """Panel lists multiple constraints."""
        panel = ConstraintsPanel()
        scene = _FakeScene()

        ids = [uuid4() for _ in range(3)]
        scene.constraint_graph.add_constraint(
            AnchorRef(ids[0], AnchorType.CENTER),
            AnchorRef(ids[1], AnchorType.CENTER),
            150.0,
        )
        scene.constraint_graph.add_constraint(
            AnchorRef(ids[1], AnchorType.CENTER),
            AnchorRef(ids[2], AnchorType.CENTER),
            300.0,
        )

        scene._items = [_FakeItem(uid) for uid in ids]

        panel.set_scene(scene)
        panel.refresh()

        assert panel._list.count() == 2

    def test_constraint_selected_signal(self, qtbot) -> None:
        """Clicking a row emits constraint_selected with the UUID."""
        panel = ConstraintsPanel()
        scene = _FakeScene()

        id_a = uuid4()
        id_b = uuid4()
        c = scene.constraint_graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        scene._items = [_FakeItem(id_a), _FakeItem(id_b)]

        panel.set_scene(scene)
        panel.refresh()

        received = []
        panel.constraint_selected.connect(lambda cid: received.append(cid))

        panel._list.setCurrentRow(0)

        assert len(received) == 1
        assert received[0] == c.constraint_id

    def test_constraint_edit_signal_on_double_click(self, qtbot) -> None:
        """Double-clicking a row emits constraint_edit_requested."""
        panel = ConstraintsPanel()
        scene = _FakeScene()

        id_a = uuid4()
        id_b = uuid4()
        c = scene.constraint_graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            250.0,
        )

        scene._items = [_FakeItem(id_a), _FakeItem(id_b)]

        panel.set_scene(scene)
        panel.refresh()

        received = []
        panel.constraint_edit_requested.connect(lambda cid: received.append(cid))

        # Simulate double-click on first item
        item = panel._list.item(0)
        panel._on_double_click(item)

        assert len(received) == 1
        assert received[0] == c.constraint_id

    def test_constraint_delete_signal(self, qtbot) -> None:
        """Delete button emits constraint_delete_requested."""
        panel = ConstraintsPanel()
        scene = _FakeScene()

        id_a = uuid4()
        id_b = uuid4()
        c = scene.constraint_graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        scene._items = [_FakeItem(id_a), _FakeItem(id_b)]

        panel.set_scene(scene)
        panel.refresh()

        received = []
        panel.constraint_delete_requested.connect(lambda cid: received.append(cid))

        # Find the ConstraintListItem widget and trigger its delete
        row_widget = panel._list.itemWidget(panel._list.item(0))
        assert isinstance(row_widget, ConstraintListItem)
        row_widget.delete_requested.emit(c.constraint_id)

        assert len(received) == 1
        assert received[0] == c.constraint_id

    def test_refresh_after_removal(self, qtbot) -> None:
        """Panel updates after a constraint is removed from the graph."""
        panel = ConstraintsPanel()
        scene = _FakeScene()

        id_a = uuid4()
        id_b = uuid4()
        c = scene.constraint_graph.add_constraint(
            AnchorRef(id_a, AnchorType.CENTER),
            AnchorRef(id_b, AnchorType.CENTER),
            100.0,
        )

        scene._items = [_FakeItem(id_a), _FakeItem(id_b)]

        panel.set_scene(scene)
        panel.refresh()
        assert panel._list.count() == 1

        # Remove the constraint and refresh
        scene.constraint_graph.remove_constraint(c.constraint_id)
        panel.refresh()

        assert panel._list.count() == 0
        assert not panel._empty_label.isHidden()

    def test_delete_all(self, qtbot) -> None:
        """Delete All button emits delete for every constraint."""
        panel = ConstraintsPanel()
        scene = _FakeScene()

        ids = [uuid4() for _ in range(3)]
        c1 = scene.constraint_graph.add_constraint(
            AnchorRef(ids[0], AnchorType.CENTER),
            AnchorRef(ids[1], AnchorType.CENTER),
            100.0,
        )
        c2 = scene.constraint_graph.add_constraint(
            AnchorRef(ids[1], AnchorType.CENTER),
            AnchorRef(ids[2], AnchorType.CENTER),
            200.0,
        )

        scene._items = [_FakeItem(uid) for uid in ids]

        panel.set_scene(scene)
        panel.refresh()

        received = []
        panel.constraint_delete_requested.connect(lambda cid: received.append(cid))

        panel.delete_all()

        assert len(received) == 2
        assert {c1.constraint_id, c2.constraint_id} == set(received)

    def test_no_scene_shows_empty(self, qtbot) -> None:
        """Panel with no scene shows empty state."""
        panel = ConstraintsPanel()
        panel.refresh()
        assert not panel._empty_label.isHidden()


class TestConstraintListItem:
    """Tests for the ConstraintListItem widget."""

    def test_creation(self, qtbot) -> None:
        """Widget creates without errors."""
        cid = uuid4()
        widget = ConstraintListItem(cid, "Tree", "Fence", 150.0, True)
        assert widget.constraint_id == cid

    def test_delete_signal(self, qtbot) -> None:
        """Delete button emits delete_requested signal."""
        cid = uuid4()
        widget = ConstraintListItem(cid, "A", "B", 100.0, False)

        received = []
        widget.delete_requested.connect(lambda uid: received.append(uid))
        widget.delete_requested.emit(cid)

        assert received == [cid]
