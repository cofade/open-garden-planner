## 11. CI-only teardown crashes (#230, PR #235)

Source: §11.4 (two adjacent entries).

- **#230**: `scene.changed` slots that `start()` a debounce timer (soil-mismatch /
  companion / spacing) fired **during teardown** — the scene emits `changed` while being
  cleared, after the child `QTimer`'s C++ object is deleted. `RuntimeError` inside a Qt
  slot escalates to `Fatal Python error: Aborted` — the *next* test errors and the run
  aborts mid-suite. Timing-dependent: passed locally, reliably crashed CI Linux. Fix:
  wrap the `.start()` in `contextlib.suppress(RuntimeError)`; **never** connect
  `scene.changed` to a bare `lambda: self._timer.start()` (a lambda can't be made
  teardown-safe). Command/status-signal timers (`stack_changed` etc.) don't need it.
- **PR #235**: `GlobalSearchField` connects to the process-global
  `QApplication.focusChanged`. Two faults: Qt already auto-disconnects destroyed
  receivers, so the explicit `destroyed`-lambda disconnect raced to `TypeError`; and a
  stray `focusChanged` could still invoke the slot on a dead widget. pytest-qt fails the
  *current* test for any exception in a slot — so one test's torn-down window failed an
  unrelated later full-app test ("passes alone, fails in the full run",
  `test_harvest.py::TestHarvestNavigation`). Fix: `suppress(TypeError, RuntimeError)` on
  the disconnect + `try/except RuntimeError: return` in the slot body.
- Rule: any handler bound to `scene.changed` or an app-global signal must assume it can
  fire after its owner is destroyed.
- Status: closed (contract-style; enforced by convention, no dedicated test).

---

