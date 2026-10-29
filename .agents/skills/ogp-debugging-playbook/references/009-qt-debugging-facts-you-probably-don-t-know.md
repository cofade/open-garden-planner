## Qt debugging facts you probably don't know

These are load-bearing for interpreting evidence in this repo (all verified against the chronicle / test suite as of 2026-07-03):

1. **pytest-qt turns any exception raised inside a Qt slot into a failure of the currently running test** — even when the slot belongs to a widget created by an *earlier* test. This is the engine behind every "passes alone, fails together" row (14–16). When a test failure's traceback names code the test never touched, suspect a leaked slot, not the test.
2. **A hand-built `QMouseEvent` passed to `view.mousePressEvent` is not delivered to `ItemIgnoresTransformations` child items** (even when `itemAt` finds them). Use `QTest.mousePress/Move/Release` on `view.viewport()` — real event dispatch — after `view.centerOn(target)` so the target is inside the viewport. This is the only faithful way to test handle drags. (#193 case study.)
3. **`QT_QPA_PLATFORM=offscreen`** makes Qt run headless (no display server). Already set in `tests/conftest.py` and CI; export it yourself for ad-hoc scripts on Linux.
4. **PyQt6 tests require the `qtbot` fixture even when unused** (Qt initialisation); ruff has a per-file ARG002 ignore for test files (AGENTS.md).
5. **`QGraphicsScene.changed` is both too chatty and too quiet**: it fires on *every repaint* (a firehose — never wire it to a destructive rebuild without debounce + a diff guard, row 21) yet *never* fires on Python attribute writes (row 22). Both directions have bitten this project.
6. **`QGraphicsItem.shape()` is hit-testing geometry, not drawing geometry** — for `QGraphicsPolygonItem` it returns the pen-width stroke *envelope*. Outline items with their primitive (`drawPolygon(self.polygon())`), never `drawPath(self.shape())`. (Case study "stroke envelope".)
7. **Python's `max(iterable, key=...)` is left-biased on ties** — with date-resolution keys, the *first* record with the max date wins, not the newest. Design tie-breaks explicitly. (Case study "max() ties".)
8. **An overridden/monkey-patched Qt event handler must return `None`** — forwarding a `bool` (e.g. `lambda e: QDesktopServices.openUrl(...)`) raises `TypeError: invalid argument to sipBadCatcherResult()`. (Chronicle: `sipBadCatcherResult`.)
9. **`item.pos()` is (0,0) for OGP shape items** — geometry lives in the local rect; the visual centre is `item.mapToScene(item.boundingRect().center())` (or `rect().center()` for the geometric centre, row 1). Coordinates asserted in tests are in cm, scene frame.

---

