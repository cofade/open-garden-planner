---
id: ADR-082
title: "A tool's multi-press draft is painted by the view through one `BaseTool` hook"
status: "Shipped in [v1.42.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.42.0) after owner acceptance (2026-11-23; issue #1002; [PR #1000](https://github.com/cofade/open-garden-planner/pull/1000), contributed by tanclin)."
refs: ["#1002"]
legacy_anchor: adr-082-a-tools-multi-press-draft-is-painted-by-the-view-through-one-basetool-hook-1002
---

# ADR-082: A tool's multi-press draft is painted by the view through one `BaseTool` hook

**Status**: Shipped in [v1.42.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.42.0)
after owner acceptance (2026-11-23; issue #1002;
[PR #1000](https://github.com/cofade/open-garden-planner/pull/1000), contributed by tanclin).

**Context**: Drawing tools preview their gesture with scene items at the `preview_z`
levels (§5, `core/tools/preview_z.py`). Those previews last one press-drag-release and
picture items that are about to exist. Plant Grid keeps a draft across many presses. The
draft is a rotated rectangle with up to 400 species sprites, eight resize handles, a
rotation handle, a size handle and a control strip (`QFrame`) inside the viewport. As
scene items, the draft would appear in `scene.items()` and therefore in rubber-band
selection, bed-membership queries, hit tests and every filter that must skip previews.
The contributed version painted the draft from `CanvasView.drawForeground` through a branch
that named this one tool, and it moved the control strip from inside that paint.

**Decision**:
1. **One hook.** `BaseTool.paint_foreground(painter)` is a no-op by default.
   `CanvasView.drawForeground` calls it for the active tool only. The call comes after the
   scene's own foreground (the object labels) and before the snap guides, with the painter
   in scene coordinates. The view wraps the call in `painter.save()`/`restore()`, so a tool
   cannot leak a transform or pen into what is painted after it. The view never names a
   tool.
2. **A paint only reads.** The hook does not move widgets and does not change scene or tool
   state. A widget that follows the draft (Plant Grid's control strip) is placed from the
   input paths and from the view changes: `CanvasView.zoom_changed`, both scroll bars'
   `valueChanged`, and a viewport resize. The resize is watched by an event filter and
   handled one event-loop turn later, because the viewport's Resize event arrives before
   `QGraphicsView` re-centres the scene (an `AnchorViewCenter` re-centre without a scroll
   range moves no scroll bar). Moving a child widget inside the parent's paint schedules
   another paint each time the position changes.
3. **Which mechanism.** A one-gesture preview of items about to exist uses scene items at
   `preview_z`. A multi-press draft that is not part of the document uses
   `paint_foreground`.
4. **Pinch.** `BaseTool.cancel_pointer_press()` is the hook that
   `CanvasView._cancel_touch_press` calls when a second finger starts a pinch (§8.9.12).
   Its default is `cancel()`. A multi-press tool overrides it to undo only that press and
   keep its draft.

**Consequences**: The draft is view-only. Exports and the minimap draw through
`scene.render()`, which never calls the view's foreground, so the draft never appears in a
picture of the plan (§8.9.16). It is never hit-tested, selected or serialized. A second
multi-press tool reuses the hook and needs no change to the view. Tests:
`tests/integration/test_plant_grid_tool.py` (the preview paints, the control strip does
not move during a paint but follows zoom, scrolling and a resize, and a pinch keeps the
draft in both phases).
Cross-refs: §8.9.12, §8.9.21, FR-PLANT-25, FR-CANVAS-04.

**Addendum (2026-11-24, #1003/#1005)**: the draft's local arithmetic moved to
Qt-free `core/plant_grid.py` (cell centres, resize edges, whole-centimetre span
snapping, local handle positions) so it is unit-tested without a QApplication.
Decision 2's placement now has one owner: `ui/canvas/viewport_overlay.ViewportOverlay`
subscribes to `zoom_changed`, both scroll bars and the deferred viewport-resize
event, and places the control strip from a tool-supplied anchor rect. The tool
no longer connects those signals or repeats the clamp arithmetic. The strip's
size, spacing, width and height are `LengthSpinBox` fields, so they follow the
units profile (ADR-078/081) while the model stays in centimetres; the field
labelled **Column spacing** shows the column pitch, typing it sets both axes,
and the row pitch is `Height ÷ rows`. Typing an extent updates the column
spacing. Snapping is
part of the drag contract: move snaps the centre, resize snaps the edge and
rounds the per-cell spacing to whole centimetres, rotation sticks within 3° of
a 15° step when snap is on (Shift always snaps), and the size handle rounds to
whole centimetres. Tests: `tests/unit/test_plant_grid.py` and
`tests/integration/test_plant_grid_tool.py`.

The toolbar placement is unchanged: the button stays in the main toolbar. The
owner call recorded in #1003 (main toolbar vs the Plants category toolbar) is
still open; this addendum records the current state, not a decision.

**Status:** Shipped in
[v1.43.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.43.0)
(PR #1021). Owner manual testing passed on 2026-11-25.
