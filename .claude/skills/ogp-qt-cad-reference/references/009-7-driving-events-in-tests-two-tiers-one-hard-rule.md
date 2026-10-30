## 7. Driving events in tests — two tiers, one hard rule

**Tier 1 — tool logic (default)**: bypass the event pipeline via the tools'
direct API (§8.10):

```python
event = MagicMock(spec=QMouseEvent)
event.button.return_value = Qt.MouseButton.LeftButton
tool.mouse_press(event, QPointF(x, y))   # scene coordinates, cm
```

Always `view.set_snap_enabled(False)` in tests; always take the `qtbot`
fixture even if unused (Qt init).

**Tier 2 — anything involving drag handles**: a hand-built `QMouseEvent` is
**NOT delivered to an `ItemIgnoresTransformations` child item** (§11.4 mouse-
grab entry). You must go through the real event pipeline with `QTest` on the
**viewport**, after bringing the handle on-screen:

```python
# pattern from tests/integration/test_curve_vertex_edit.py (~lines 234–283)
canvas.show(); QTest.qWaitForWindowExposed(canvas)
canvas.centerOn(handle.scenePos())        # handle must be inside the viewport
vp_pos = canvas.mapFromScene(handle.scenePos())
QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=vp_pos)
QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(target_scene))
QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=...)
```

`QT_QPA_PLATFORM=offscreen` makes this work headless in CI. Remember
`mapFromScene` already includes the Y-flip — feed it scene coords and trust it.

**Touch gestures cannot be built as `QTouchEvent`s.** PyQt6 exposes
`QTouchEvent` but not `QTouchEvent.TouchPoint`, so a synthetic multi-touch
event cannot be constructed (verified 2026-10-30 for #321). Drive the state
machine's plain-position methods instead — `CanvasView._touch_started`,
`_touch_moved`, `_touch_finished` — and keep them free of Qt event types for
that reason. Event *delivery* (viewport attribute + event filter) is what stays
manual. A native trackpad pinch is a `QNativeGestureEvent`, not a touch event;
that path is `_native_gesture`. The canvas's wheel and pinch share `_zoom_at`,
and the middle-mouse pan and two-finger pan share `_pan_by` — never duplicate
either formula in a test helper or a second handler.

---

