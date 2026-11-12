## Case study: an edited unit test waited forever at cleanup (#673, fixed 2026-11-12)

**Symptom**: the new soil-depth test passed its assertions and then stalled.

**Wrong theories**: unit-switch notifications or a deferred Properties rebuild
might have left Qt waiting. These were possibilities, not fixes adopted.

**Evidence**: a temporary wrapper of `_confirm_discard_changes` printed the dirty
state and `traceback.format_stack()` while reproducing the real key/Return edit:

```text
[UNITS-CLOSE] dirty= True
[UNITS-CLOSE] caller= pytestqt.qtbot._close_widgets -> w.close()
    -> GardenPlannerApp.closeEvent -> _confirm_discard_changes
```

**Root cause**: pytest-qt closes registered windows after each test. Editing a real
plan correctly made it dirty, and cleanup entered the modal unsaved-changes prompt.

**Fix**: the whole-window unit fixture explicitly discards its own test document;
production close behavior is unchanged. Instrumentation was removed.

**Lesson**: when an edited-window test hangs after passing, instrument the close
path and its caller before changing widget logic. Pinned by
`tests/ui/test_units_surfaces.py::test_soil_depth_preserves_native_input`.
The save/reopen test separately compares geometry exactly; stacking ranks are
normalized at load and are not a length conversion.
