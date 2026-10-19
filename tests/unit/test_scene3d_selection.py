"""The selection ring and its one seam through the pipeline (Phase 17 L1.8, gate G3).

``core/scene3d/selection.py`` turns "these item ids are selected" into ONE mesh: a
band along every outline of the selected records, on the outside of what is solid,
at each record's standing base. ``SceneSync`` hands it to the engine through one
additive ``EngineSink`` method — ``set_selection`` — and through nothing else: a
selection change never adds, removes, rebuilds, re-poses or re-tints a model, and a
selected item that moves takes its ring along in the same transaction.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    Material,
    Params,
    Record,
    RecordingSink,
    SceneSync,
    SinkProtocolError,
    SunState,
    SyncStateError,
    Transform,
    point_in_ring,
    pose_ring,
)
from open_garden_planner.core.scene3d.selection import (
    EMPTY_SELECTION,
    MITRE_LIMIT,
    RING_LIFT_CM,
    RING_WIDTH_PX,
    SELECTION_RGB,
    Selection,
    selection_of,
)

BEGIN, COMMIT = ("begin", None), ("commit", None)
SELECT = ("set_selection", None)
MODEL_CALLS = {"add", "remove", "replace_geometry", "update_transform", "update_material"}


def rect(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    half_w, half_d = width / 2.0, depth / 2.0
    return ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))


def circle(radius: float, corners: int = 24) -> tuple[tuple[float, float], ...]:
    return tuple((radius * math.cos(2 * math.pi * k / corners),
                  radius * math.sin(2 * math.pi * k / corners)) for k in range(corners))


def item(item_id: str, east: float = 0.0, north: float = 0.0, *, ring=None, holes: tuple = (),
         rotation: float = 0.0, base: float = 0.0, height: float | None = 100.0,
         kind: str = "SHED") -> Record:
    return Record(item_id=item_id, kind=kind, shape="polygon",
                  footprints=(ring if ring is not None else rect(200.0, 100.0),), holes=holes,
                  transform=Transform(east, north, rotation, base), material=Material(kind),
                  height_cm=height, params=Params({"seed": item_id}))


def displaced(selection: Selection, width_cm: float) -> np.ndarray:
    """Where the ring shader puts each vertex for a band ``width_cm`` wide: the vertex,
    moved along its stored direction by uv.x widths and up by uv.y widths."""
    mesh = selection.ring
    out = mesh.positions.astype(np.float64).copy()
    out[:, :2] += mesh.normals[:, :2].astype(np.float64) * mesh.uvs[:, :1].astype(np.float64) * width_cm
    out[:, 2] += mesh.uvs[:, 1].astype(np.float64) * width_cm
    return out


def distance_to_ring(point, ring) -> float:
    best = math.inf
    for index, (ax, ay) in enumerate(ring):
        bx, by = ring[(index + 1) % len(ring)]
        dx, dy = bx - ax, by - ay
        t = min(1.0, max(0.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(point[0] - ax - t * dx, point[1] - ay - t * dy))
    return best


# ── the ring's geometry ──────────────────────────────────────────────────────


def test_the_stated_numbers() -> None:
    assert SELECTION_RGB == (0, 120, 215), "the canvas's selection blue"
    assert RING_WIDTH_PX == 3.0 and RING_LIFT_CM == 1.0 and MITRE_LIMIT == 2.5


def test_nothing_selected_is_the_empty_selection() -> None:
    records = {"a": item("a")}
    assert selection_of(records, ()) == EMPTY_SELECTION
    assert selection_of(records, ["gone", "also gone"]) == EMPTY_SELECTION, "ids without a record"
    assert selection_of({}, ["a"]) == EMPTY_SELECTION
    assert EMPTY_SELECTION.ids == () and EMPTY_SELECTION.ring.vertex_count == 0
    assert not EMPTY_SELECTION and selection_of(records, ["a"])


@pytest.mark.parametrize("rotation", [0.0, 30.0, 90.0, 213.5])
def test_the_ring_lies_on_the_posed_outline_at_the_standing_base(rotation: float) -> None:
    """The mesh is in the SCENE frame: the record's transform is applied — position,
    turn and base — and every vertex starts ON the footprint outline."""
    record = item("a", 500.0, -300.0, rotation=rotation, base=38.0)
    selection = selection_of({"a": record}, ["a"])
    outline = pose_ring(record.transform, record.footprints[0])
    mesh = selection.ring
    assert selection.ids == ("a",)
    assert mesh.vertex_count == 3 * 4 and mesh.triangle_count == 4 * 4
    assert np.allclose(mesh.positions[:, 2], 38.0 + RING_LIFT_CM), "slightly above its base"
    for vertex in mesh.positions:
        assert min(math.hypot(vertex[0] - x, vertex[1] - y) for x, y in outline) < 1e-3
    assert np.allclose(np.linalg.norm(mesh.normals, axis=1), 1.0, atol=1e-6)
    assert np.allclose(mesh.normals[:, 2], 0.0), "the band's direction is level"


@pytest.mark.parametrize("width", [0.5, 4.0, 25.0])
def test_the_band_lies_outside_the_footprint_and_is_as_wide_as_asked(width: float) -> None:
    """Displaced as the shader displaces it, the band covers exactly the strip from the
    outline to ``width`` outside it — never the item's own ground (the solid stands
    there and would hide it)."""
    record = item("a", 100.0, 50.0, rotation=20.0)
    selection = selection_of({"a": record}, ["a"])
    outline = pose_ring(record.transform, record.footprints[0])
    moved = displaced(selection, width)
    uvs = selection.ring.uvs
    for vertex, (out, up) in zip(moved, uvs, strict=True):
        distance = distance_to_ring(vertex, outline)
        if out == 0.0:
            assert distance < 1e-3 and up == 0.0, "the inner edge is the outline itself"
        else:
            assert not point_in_ring(float(vertex[0]), float(vertex[1]), outline)
            assert distance == pytest.approx(width * math.sqrt(2.0), rel=1e-4), "a mitred square corner"
        assert vertex[2] == pytest.approx(record.transform.base_cm + RING_LIFT_CM + up * width)
    # two heights: a flat band on the ground and a ribbon standing on its outer edge —
    # seen from above the first shows, seen from the side the second
    assert sorted({round(float(up), 6) for up in uvs[:, 1]}) == [0.0, 1.0]
    flat = [t for t in selection.ring.indices if np.all(uvs[t, 1] == 0.0)]
    standing = [t for t in selection.ring.indices if np.any(uvs[t, 1] == 1.0)]
    assert len(flat) == len(standing) == 8
    assert all(np.all(uvs[t, 0] > 0.0) for t in standing), "the ribbon stands on the OUTER edge"


def test_a_hole_gets_its_own_ring_on_the_holes_side() -> None:
    """A closed fence is an outer ring with the garden as its hole: the band runs
    outside the outer ring and INSIDE the hole — both away from the solid."""
    hole = tuple(reversed(rect(100.0, 60.0)))                 # clockwise, as a record holds it
    record = item("f", 0.0, 0.0, ring=rect(160.0, 120.0), holes=((hole,),))
    selection = selection_of({"f": record}, ["f"])
    assert selection.ring.vertex_count == 3 * (4 + 4)
    moved = displaced(selection, 5.0)[selection.ring.uvs[:, 0] > 0.0]
    outer_side = [p for p in moved if abs(p[0]) > 80.0 or abs(p[1]) > 60.0]
    hole_side = [p for p in moved if abs(p[0]) < 50.0 and abs(p[1]) < 30.0]
    assert len(outer_side) == len(hole_side) == 8, "four corners, two heights each, per ring"
    assert all(abs(abs(p[0]) - 45.0) < 1e-3 and abs(abs(p[1]) - 25.0) < 1e-3 for p in hole_side)
    assert all(abs(abs(p[0]) - 85.0) < 1e-3 and abs(abs(p[1]) - 65.0) < 1e-3 for p in outer_side)


def test_a_circle_gets_a_round_ring_of_even_width() -> None:
    record = item("tree", 300.0, 400.0, ring=circle(150.0), kind="TREE", base=40.0)
    selection = selection_of({"tree": record}, ["tree"])
    assert selection.ring.vertex_count == 3 * 24
    outer = displaced(selection, 6.0)[selection.ring.uvs[:, 0] > 0.0]
    radii = np.hypot(outer[:, 0] - 300.0, outer[:, 1] - 400.0)
    # the 24-gon's corners are mitred: the band is 6 cm wide ACROSS, 6 / cos(7.5 deg) at a corner
    assert np.allclose(radii, 150.0 + 6.0 / math.cos(math.radians(7.5)), atol=1e-3)


def test_a_needle_sharp_corner_is_cut_short_not_shot_into_the_garden() -> None:
    """A mitre grows without bound as a corner closes; it is capped at ``MITRE_LIMIT``
    band widths, so a 2-degree spike of a polygon does not throw the ring metres away."""
    spike = ((0.0, 0.0), (400.0, -7.0), (400.0, 7.0))          # the corner at the origin: 2 degrees
    record = item("s", 0.0, 0.0, ring=spike)
    selection = selection_of({"s": record}, ["s"])
    reach = float(np.abs(selection.ring.uvs[:, 0]).max())
    assert reach == pytest.approx(MITRE_LIMIT)
    assert float(displaced(selection, 4.0)[:, 0].min()) >= -4.0 * MITRE_LIMIT - 1e-6, (
        "the tip's band ends within the cap, west of the corner")


def test_repeated_points_and_a_closing_point_do_not_break_the_ring() -> None:
    ring = ((-50.0, -50.0), (50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0), (-50.0, -50.0))
    record = item("r", 0.0, 0.0, ring=ring)
    mesh = selection_of({"r": record}, ["r"]).ring
    assert mesh.vertex_count == 3 * 4, "four distinct corners"
    assert np.isfinite(mesh.positions).all() and np.isfinite(mesh.normals).all()


def test_the_selection_is_one_merged_mesh_in_a_canonical_order() -> None:
    """Several items are ONE mesh — one Model, one draw call — and the same set gives
    the same selection whatever order it was asked or painted in."""
    a, b, c = item("a", 0.0, 0.0), item("b", 500.0, 0.0, ring=circle(40.0)), item("c", 0.0, 500.0)
    records = {"a": a, "b": b, "c": c}
    both = selection_of(records, ["b", "a"])
    assert both.ids == ("a", "b") and both.ring.vertex_count == 3 * 4 + 3 * 24
    assert selection_of(records, {"a", "b"}) == both
    assert selection_of({"c": c, "b": b, "a": a}, ("a", "b", "b", "zzz")) == both
    assert both != selection_of(records, ["a"]) and both != selection_of(records, ["a", "c"])
    assert int(both.ring.indices.max()) == both.ring.vertex_count - 1


def test_a_selection_compares_by_what_would_be_drawn() -> None:
    a = item("a", 0.0, 0.0)
    here = selection_of({"a": a}, ["a"])
    moved = selection_of({"a": replace(a, transform=Transform(1.0, 0.0))}, ["a"])
    recoloured = selection_of({"a": replace(a, material=Material("SHED", (1, 2, 3, 255)))}, ["a"])
    assert here != moved and here == recoloured and here == selection_of({"a": a}, ["a"])
    assert here != EMPTY_SELECTION and here != object()


# ── the seam: one sink method ────────────────────────────────────────────────


def scene() -> dict[str, Record]:
    return {"a": item("a", 0.0, 0.0), "b": item("b", 500.0, 0.0, ring=circle(40.0), kind="TREE"),
            "c": item("c", 0.0, 500.0)}


def synced() -> tuple[RecordingSink, SceneSync, dict[str, Record]]:
    sink = RecordingSink()
    sync = SceneSync(sink)
    records = scene()
    sync.apply(records, sun=SunState(40.0, 180.0))
    sink.clear_calls()
    return sink, sync, records


def test_a_selection_change_is_one_call_and_touches_no_model() -> None:
    """Gate G3: select, add, remove, clear — each is ``[begin, set_selection, commit]``."""
    sink, sync, records = synced()
    builds = sync.build_count
    for ids in (["a"], ["a", "b"], ["b"], []):
        assert sync.set_selection(ids) is True
        assert sink.ops() == [BEGIN, SELECT, COMMIT]
        assert sink.selection == selection_of(records, ids) == sync.selection
        assert sink.selection.ids == tuple(sorted(ids)) and sync.selected_ids == frozenset(ids)
        assert not {op for op, _id in sink.ops()} & MODEL_CALLS
        sink.clear_calls()
    assert sync.build_count == builds, "no builder ran"
    assert sink.state() == sync.expected_state()


def test_asking_for_what_is_shown_already_sends_nothing() -> None:
    sink, sync, _records = synced()
    assert sync.set_selection([]) is False and sink.ops() == []
    sync.set_selection(["a"])
    sink.clear_calls()
    assert sync.set_selection(["a"]) is False and sync.set_selection(("a", "a")) is False
    assert sync.set_selection(["a", "not in the scene"]) is False, "an id without a record draws nothing"
    assert sink.ops() == [] and sync.selected_ids == {"a", "not in the scene"}


def test_selecting_only_remembers_and_the_next_apply_carries_it() -> None:
    """``select`` makes no engine call (a hidden view costs nothing); ``apply`` sends
    the ring in ITS transaction, with whatever else changed."""
    sink, sync, records = synced()
    sync.select(["a"])
    assert sink.ops() == [] and sink.selection == EMPTY_SELECTION
    assert sync.selection == EMPTY_SELECTION and sync.selected_ids == {"a"}
    moved = {**records, "c": replace(records["c"], transform=Transform(10.0, 500.0))}
    sync.apply(moved)
    assert sink.ops() == [BEGIN, ("update_transform", "c"), SELECT, COMMIT]
    assert sink.selection == selection_of(moved, ["a"])
    sink.clear_calls()
    sync.apply(moved)
    assert sink.ops() == [], "nothing changed: nothing is sent"
    assert sync.send_selection() is False


def test_a_selection_alone_makes_apply_open_a_transaction() -> None:
    sink, sync, records = synced()
    sync.select(["b"])
    sync.apply(records)
    assert sink.ops() == [BEGIN, SELECT, COMMIT]


@pytest.mark.parametrize(("edit", "calls"), [
    (lambda r: replace(r, transform=Transform(77.0, 5.0, 30.0)), [("update_transform", "a"), SELECT]),
    (lambda r: replace(r, footprints=(rect(300.0, 100.0),)), [("replace_geometry", "a"), SELECT]),
    (lambda r: replace(r, transform=Transform(0.0, 0.0, 0.0, 38.0)), [("update_transform", "a"), SELECT]),
    (lambda r: replace(r, material=Material("SHED", (9, 9, 9, 255))), [("update_material", "a")]),
    (lambda r: replace(r, height_cm=250.0), [("replace_geometry", "a")]),
    (lambda r: replace(r, name="renamed"), []),
])
def test_the_ring_follows_its_item_in_the_same_transaction(edit, calls) -> None:
    """A move, a turn, a new outline, a new base: the ring is re-sent WITH the edit.
    A recolour, a new height (same outline, same base) and a rename leave it alone."""
    sink, sync, records = synced()
    sync.set_selection(["a"])
    sink.clear_calls()
    edited = {**records, "a": edit(records["a"])}
    sync.apply(edited)
    assert sink.ops() == ([BEGIN, *calls, COMMIT] if calls else [])
    assert sink.selection == selection_of(edited, ["a"]) == sync.selection
    assert sink.state() == sync.expected_state()


def test_an_edit_of_something_else_does_not_resend_the_ring() -> None:
    sink, sync, records = synced()
    sync.set_selection(["a"])
    sink.clear_calls()
    sync.apply({**records, "b": replace(records["b"], transform=Transform(900.0, 0.0))})
    assert sink.ops() == [BEGIN, ("update_transform", "b"), COMMIT]


def test_a_selected_item_that_is_deleted_loses_its_ring_and_gets_it_back_with_undo() -> None:
    sink, sync, records = synced()
    sync.set_selection(["a", "c"])
    sink.clear_calls()
    without = {key: value for key, value in records.items() if key != "a"}
    sync.apply(without)
    assert sink.ops() == [BEGIN, ("remove", "a"), SELECT, COMMIT]
    assert sink.selection.ids == ("c",) and sync.selected_ids == {"a", "c"}, "the WISH is kept"
    sink.clear_calls()
    sync.apply(records)                                   # undo: the item is back
    assert sink.ops() == [BEGIN, ("add", "a"), SELECT, COMMIT]
    assert sink.selection == selection_of(records, ["a", "c"])


def test_a_new_plan_drops_the_ring_of_an_item_that_is_gone() -> None:
    sink, sync, _records = synced()
    sync.set_selection(["a"])
    other = {"x": item("x", 50.0, 50.0)}
    sink.clear_calls()
    sync.apply(other)
    assert SELECT in sink.ops() and sink.selection == EMPTY_SELECTION
    assert sink.state() == sync.expected_state()


def test_a_pure_reorder_does_not_touch_the_ring() -> None:
    sink, sync, records = synced()
    sync.set_selection(["a", "c"])
    sink.clear_calls()
    sync.apply({key: records[key] for key in ("c", "b", "a")})
    assert sink.ops() == []


def test_a_reset_forgets_what_was_sent_and_the_next_apply_sends_the_ring_again() -> None:
    """Recovery (``SceneSync.reset``): the engine holds nothing — no ring either — and
    the selection the canvas still has comes back with the next apply."""
    sink, sync, records = synced()
    sync.set_selection(["a"])
    sync.reset()
    assert sink.selection == EMPTY_SELECTION and sync.selection == EMPTY_SELECTION
    assert sync.selected_ids == {"a"}
    sink.clear_calls()
    sync.apply(records, sun=SunState(40.0, 180.0))
    assert sink.ops()[-2:] == [SELECT, COMMIT] and sink.selection == selection_of(records, ["a"])
    assert sink.state() == sync.expected_state()


def test_the_incremental_ring_is_the_ring_of_a_fresh_apply() -> None:
    """The invariant of the sync, now with a selection in the state: after any sequence
    the sink holds what ONE apply of the latest snapshot and selection would give."""
    sink, sync, records = synced()
    rng = np.random.default_rng(8)
    ids = list(records)
    for step in range(60):
        choice = int(rng.integers(0, 4))
        if choice == 0:
            sync.set_selection([i for i in ids if rng.random() < 0.5])
        elif choice == 1:
            target = ids[int(rng.integers(0, len(ids)))]
            if target in records:
                records = {**records, target: replace(records[target], transform=Transform(
                    float(rng.uniform(-500, 500)), float(rng.uniform(-500, 500)),
                    float(rng.uniform(0, 360)), float(rng.choice([0.0, 38.0]))))}
        elif choice == 2 and len(records) > 1:
            records = dict(list(records.items())[1:])
        else:
            records = {**scene(), **records}
        sync.apply(records)
        assert sink.state() == sync.expected_state(), step
        assert sink.selection == selection_of(records, sync.selected_ids), step


def test_the_recording_sink_holds_the_protocol_for_the_new_call() -> None:
    sink = RecordingSink()
    with pytest.raises(SinkProtocolError, match="outside"):
        sink.set_selection(EMPTY_SELECTION)
    sink.begin()
    with pytest.raises(SinkProtocolError, match="Selection"):
        sink.set_selection(["a"])  # type: ignore[arg-type]
    ring = selection_of(scene(), ["a"])
    sink.set_selection(ring)
    sink.commit()
    assert sink.selection is ring and sink.state().selection is ring
    assert sink.calls[1].op == "set_selection" and sink.calls[1].args == (ring,)
    sink.clear()
    assert sink.selection == EMPTY_SELECTION and sink.state().selection == EMPTY_SELECTION


def test_a_sink_that_fails_on_the_ring_poisons_the_sync_like_any_other_call() -> None:
    class Failing(RecordingSink):
        def set_selection(self, selection: Selection) -> None:
            raise RuntimeError("the engine refused the ring")

    sink = Failing()
    sync = SceneSync(sink)
    sync.apply(scene())
    with pytest.raises(RuntimeError, match="refused the ring"):
        sync.set_selection(["a"])
    assert sync.poisoned
    with pytest.raises(SyncStateError):
        sync.set_selection(["b"])
    sync.select(["b"])            # remembering is always allowed: it touches nothing
    assert sync.selected_ids == {"b"}


def test_an_outline_that_cannot_be_ringed_is_left_out_and_the_rest_is_drawn(
        caplog: pytest.LogCaptureFixture) -> None:
    """One bad item must not take the selection of the others with it."""
    from open_garden_planner.core.scene3d import selection as module

    records = scene()
    real = module._posed_outline

    def failing(record: Record, ring):
        if record.item_id == "b":
            raise ValueError("a ring nobody can walk round")
        return real(record, ring)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, "_posed_outline", failing)
        selection = selection_of(records, ["a", "b", "c"])
    assert selection.ids == ("a", "c") and selection == selection_of(records, ["a", "c"])
    assert any("'b'" in record.getMessage() for record in caplog.records)
