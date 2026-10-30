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

**Touch gestures: use Qt's recognizer, and test the real event filter.** A
hand-written `QTouchEvent` state machine looks testable but is wrong at the only
seam that matters: Qt sends `TouchBegin` for the *first* finger and adds the
second in a `TouchUpdate`, so a handler that waits for two points in the begin
never starts (measured on #321). `viewport().grabGesture(Qt.GestureType.PinchGesture)`
lets Qt arbitrate: it starts only on the second finger, reports the centre and a
cumulative `totalScaleFactor`, and leaves a single-finger tap/drag on the
synthesised mouse path. PyQt6 *does* expose `QPinchGesture`, its setters and
`QGestureEvent`, and a `QPinchGesture` subclass can override the read-only
`state()`, so the real `eventFilter` can be driven with synthetic
started/updated/finished gestures; only a real touchscreen's delivery stays
manual. Pan first, then zoom about the new centre. A native trackpad pinch is a
`QNativeGestureEvent`, not a touch event; that path is `_native_gesture`. The
canvas's wheel and pinch share `_zoom_at`, and the middle-mouse pan and
two-finger pan share `_pan_by` - never duplicate either formula in a test helper
or a second handler.

---

