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

---

