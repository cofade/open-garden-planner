## Case study: untransformable label child poisoned Qt's BSP tree (#919) (2026-11-17)

**Symptom:** Every `scene.itemAt()`, hover move, press, double-click, and context menu on an 853-object plan walked every labelled object in Python (5–6 ms per event) instead of querying only the local BSP leaf.

**Theories entertained (wrong):**
- Attributing the cost only to `LabelPass` foreground painting or `CanvasView` snap-index rebuilds (`#847` already moved those off `scene.changed`, yet `itemAt` / hover stayed linear in the number of objects).
- Assuming `PlanLabelItem.shape()` returning `QPainterPath()` and `ItemHasNoContents` kept the label invisible to Qt's spatial index.

**Key evidence:** `PlanLabelItem` was a child `QGraphicsItem` on every garden object with Qt's C++ `QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations` enabled (`garden_item.py`). Qt's `QGraphicsSceneBspTreeIndex` cannot spatially index untransformable subtrees, so setting `ItemIgnoresTransformations` on a child pushes its **top-level parent** (`CircleItem`, `RectangleItem`, etc.) into `untransformableItems`. Every BSP query then linearly walks all 853 owners in Python and calls `boundingRect()` on each (with `CircleItem.boundingRect()` also recomputing `_grown_radius_overflow()`, `_effective_spacing_radius()`, and `_shadow_margin()` uncached).

**Root cause:** `QGraphicsSceneBspTreeIndex` classifies the entire parent hierarchy as untransformable when any child carries C++ `ItemIgnoresTransformations`, bypassing the BSP tree for all scene queries and repaints; additionally `CircleItem.boundingRect()` was uncached.

**Fix:**
- `src/open_garden_planner/ui/canvas/items/halo_text.py` (`PlanLabelItem.setFlag` / `setFlags` / `screen_device_transform` / `deviceTransform` / `paint` / `contains`): intercept `ItemIgnoresTransformations` in Python (`self._ignores_transformations`) without setting the C++ flag, and supply the screen-space transform explicitly to `LabelPass` (`plan_labels.py`) and standalone `paint()`.
- `src/open_garden_planner/ui/canvas/items/circle_item.py`: cache `_cached_bounding_rect` and invalidate it in `prepareGeometryChange()` (`PF-CAN-43`).

**Lesson:** Never put Qt's C++ `ItemIgnoresTransformations` flag on a child attached to every scene object. If the scene paints the child in screen space (or maps its anchor explicitly), track the transform policy in Python so Qt's BSP index continues to index every parent. Pinned by `tests/integration/test_plan_label_hits.py::test_scene_query_on_large_plan_uses_bsp_index_not_full_walk` and `tests/integration/test_canvas_repaint_package.py::test_circle_spacing_ring_and_bounding_rect_caches`.
