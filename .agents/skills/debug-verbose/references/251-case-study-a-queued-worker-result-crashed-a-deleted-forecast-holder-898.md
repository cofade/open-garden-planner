## Case study: a queued worker result crashed a deleted forecast holder (#898, fixed 2026-11-15)

**Symptom:** master's CI run 43649444367 lost four xdist workers (`Test` lost three, Coverage
partition (0) lost one), while running `test_polygon_paint_bound.py`,
`test_agent_task_soil_tools.py` (twice) and `test_save_location.py` — files that never mention
weather. Every crash was the same:

```text
Fatal Python error: Segmentation fault
Current thread (most recent call first):
  File ".../services/forecast_holder.py", line ??? in <lambda>
  File ".../pytestqt/plugin.py", line 220 in _process_events
  File ".../pytestqt/plugin.py", line 179 in pytest_runtest_setup
```

The same tree had passed the same partitions in run 43646470225 (PR #920).

**Wrong theories:** a soil-tool bug; the MCP transport; a QThread destroyed while running (#480
class, which aborts differently); `pytest-qt` itself. The crash site named the holder, but the
test that triggered it only created the normal app fixture, which sets a location and starts a
real forecast fetch.

**Key trace:** `forecast_holder.py` connected `worker.success` to
`lambda f: self._safe_worker_success(f, gen, lat, lon)`. A lambda is not a `QObject` receiver, so
nothing disconnects it when the holder dies; pytest-qt's next `_process_events` delivered the
queued result into a wrapper whose C++ object was gone. The trace's top frame is the lambda; the
inferred first C++ touch on the deleted wrapper is the `forecast_ready.emit(...)` inside the
success path. Two probe results sharpened the diagnosis: `QObject.receivers(signal)` still reports
1 after `sip.delete(receiver)` (a count cannot pin the fix), and PyQt still resolves a Python
class method on the deleted wrapper (so a patched method can record the delivery that must not
happen).

**Root cause:** the connection outlived its owner by design. PF-LIF-12 already required
UNDECORATED slots; the lambda satisfied "not decorated" and violated the other half — a receiver
Qt can drop.

**Fix:** connect undecorated bound methods (`_on_worker_signal_success`,
`_on_worker_signal_failed`), carry generation/lat/lon on the worker, read them from
`self.sender()`, and retain the worker until `finished` at start so a holder that dies without
`shutdown()` cannot let Python collect a running `QThread`.

**Lesson:** a Lambda slot has no receiver, so its lifetime is the sender's, not the owner's.
If a queued result must not reach a dead object, the connection must belong to an object Qt can
delete. Do not use `receivers()` as the proof; record the call at a class-level method on the
deleted wrapper instead. Pins:
`tests/unit/test_forecast_holder.py::test_a_queued_worker_result_never_reaches_a_deleted_holder`
(fails on the old lambda code) and
`tests/unit/test_forecast_holder.py::test_a_worker_result_carries_the_request_values_not_the_holders`.
Pitfall: PF-LIF-13.
