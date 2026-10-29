## 2. The QGraphicsItem geometry contract

Three different "where is it" answers, and this repo's specific convention:

- `pos()` — where the item's local origin sits in its parent's frame.
- `rect()` — the *geometric* shape rect (only on rect-bearing items:
  `CircleItem`, `RectangleItem`, `EllipseItem`).
- `boundingRect()` — the repaint region; geometry **plus decorations** (badge
  overflow, spacing-ring expansion). May be asymmetric.

**Repo convention: items keep `pos() == (0, 0)` and store geometry in local
coords.** `item.pos()` and `item.scenePos()` both return (0,0) for a plant;
the visual centre is `item.mapToScene(item.boundingRect().center())` (§11.4
"Plant items store center in boundingRect(), not in pos()"). Items *can* end
up with nonzero `pos()` after drags/resizes, which is why the serializer
always sums both:

```python
# core/project.py (~line 1428, EllipseItem branch — Circle/Rect analogous)
cx = item.pos().x() + rect.center().x()
cy = item.pos().y() + rect.center().y()
```

### The one invariant: `transformOriginPoint() == rect().center()`

The serializer saves `pos + rect.center()` as the centre and rotation as a
**separate angle pivoting on the centre**. So every geometry mutation —
rotate, programmatic resize, interactive drag-resize, and the undo/redo of any
of them — must end with `transformOriginPoint() == rect().center()`, or a
rotated item's saved centre diverges from its on-screen centre: it **drifts on
reload and jumps on the next rotation**. It looks correct on screen
immediately, so unrotated tests pass green. (§8.9.8; issues #213/#218/#219.)

Do not re-derive this per gesture. Route through the two blessed primitives:

1. **Resize** → `resize_rect_item_keeping_anchor(item, new_rect, scene_anchor,
   local_anchor)` in `src/open_garden_planner/ui/canvas/items/resize_handle.py`
   (~line 46). It calls `prepareGeometryChange()`, applies the rect, re-pins
   the origin to the new centre, and solves the position so a chosen scene
   point stays fixed. The math (Qt maps local `p` → scene as
   `pos + O + R(θ)·(p − O)` with `O = transformOriginPoint`):

   ```
   pos = scene_anchor − O − R(θ)·(local_anchor − O)
   ```

2. **Rotate** → `RotationHandleMixin._apply_rotation` (same file), which
   pivots on `rect().center()` when the item has `rect()`, else
   `boundingRect().center()` (Text/Callout/Polyline — no asymmetric
   decorations).

Lessons baked into those primitives (don't undo them):

- **#219**: the pivot must come from the geometric `rect()`, never the
  decoration-expanded `boundingRect()`. A runtime-only antagonist badge
  expands `boundingRect()` asymmetrically (+x/+y only); pivoting there made
  the save-time pivot (badge on) disagree with the load-time pivot (badge off)
  — a rotated badged plant drifted on save/reload *with no resize involved*.
- **#218**: the interactive `ResizeHandle._apply_resize` takes the fixed
  corner/edge **authoritatively from the handle position** (scene-space
  inference and rotated-local inference disagree under rotation); the item
  normalises the rect itself (`CircleItem._constrain_resize_size`, ~line 589,
  squares it so the dragged handle tracks the cursor — never `min(w, h)`,
  which collapses at 45°); then `_after_resize_geometry()` refreshes
  bookkeeping. Do not post-correct an incoherent geometry step — fix the step.
- **`prepareGeometryChange()` duty**: any code that can *shrink* a custom
  `boundingRect()` must call it first or Qt leaves a stale "ghost" of the old
  extent (the spacing ring made this visible in #218).
- Programmatic centred resize: `CircleItem.set_radius_centered()`
  (`circle_item.py` ~line 464) — resizes footprint, re-pins origin,
  repositions so `pos + center` stays put. Pinned by
  `test_apply_keeps_rotated_plant_centered`.
- **Any resize-under-rotation change needs an explicit rotated-item test** —
  see `tests/integration/test_rotation_aware_resize.py`
  ({Circle,Rect,Ellipse} × {0°, 45°, 215°} × {corner, edge}).

Plant sizing precedence (footprint radius vs `spacing_radius_cm` override vs
DB `max_spread_cm`) has one Qt-free home: `core/plant_sizing.py`. Never inline
it.

---

