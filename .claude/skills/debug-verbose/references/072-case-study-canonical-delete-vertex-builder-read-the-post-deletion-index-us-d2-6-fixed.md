## Case study: canonical delete-vertex builder read the post-deletion index (US-D2.6, fixed 2026-09-25)

**Symptom**: The interactive polyline "delete last vertex" gesture built an undo command whose stored position was read after the vertex had already been removed. Undo either restored the wrong point or, for the final index, tripped the builder's index guard.

**Wrong theories**: The initial shared builder looked correct because the Agent API path computes the position before executing the command. The assumption "the vertex still exists when the builder runs" was true for one caller and false for the other.

**Key evidence**: `PolylineVertexEditMixin._delete_vertex` removes the point and then calls `_on_vertex_delete(index, deleted_pos)`; the builder ignored `deleted_pos` and re-read the live index. The new regression test deleting index 4 of a 5-point fence failed at the builder's `0..3` guard, naming the off-by-state exactly.

**Root cause**: A shared command builder replaced two call-site orderings with one ordering. The interactive path is post-mutation; the agent path is pre-mutation. Reading shared state at build time made the seam order-dependent.

**Fix**: `build_delete_vertex_command` takes an optional already-captured local position. The interactive path passes its `deleted_pos` and permits the undo insertion index to equal the current count; the Agent API omits it and the builder reads the still-present vertex. Pinned by `tests/integration/test_polyline_vertex_edit.py::TestVertexAddDeleteShiftsConstraintIndices::test_delete_last_vertex_undo_restores_its_exact_position`.

**Lesson**: When consolidating two call paths into one helper, enumerate each path's mutation order relative to the helper call. "One canonical path" must preserve caller-supplied state where the caller has already mutated the thing the helper is tempted to re-read.

---

