## Case study: a broken shader failed the render, and the run's own summary counted 0 Qt errors (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: the positive control "a broken shader fails the render" did what it should: the
render raised `RenderError` and the driver exited with its error code. The same run's summary
(`result.json`, `qt_messages.counts.error`) said 0. The frame's own report listed the shader
errors; the run's report had never heard of them.

**Theories entertained**: none worth the name, and no instrumentation was added — say so
rather than dress it up. The cause was found by reading the two places that install a Qt
message handler. The entry is here because the SYMPTOM is the kind this skill exists for (a
count that contradicts an exception raised a line earlier), and because the tempting first
theory — "the summary is written before the error arrives" — would have sent the search into
the order of events, where nothing was wrong.

**Key evidence**: the two recorders themselves. `render_records` creates a `QtMessages`
recorder for ONE frame and installs it with `qInstallMessageHandler`; the render driver had
installed one for the WHOLE run with the same call. The inner one held the errors, the outer
one held none.

**Root cause**: `qInstallMessageHandler` keeps a single handler per process. Installing the
inner recorder REPLACED the outer one for the duration of the frame — and a shader's compile
messages arrive during exactly that frame.

**Fix**: `qt_messages.install()` forwards every message to the handler it replaced and returns
it; `uninstall(previous)` puts that one back. Recorders nest. Inside the running app the same
chaining keeps the app's own handler hearing everything during an offscreen render. Pinned by
`tests/unit/test_quick3d_pure.py::test_nested_recorders_both_hear_an_error` and
`::test_a_recorder_listens_in_and_then_steps_aside`.

**Lesson**: **a "one per process" API turns a second listener into a replacement** — when a
count is 0 where an error was just raised, compare the listeners before suspecting the order of
events. The same shape came back twice in the same story: `faulthandler` has ONE
`dump_traceback_later` timer (a watchdog inside a watchdog cancels the outer one), and
`QLoggingCategory.setFilterRules` holds ONE rule set (a nested block must not switch the outer
block's rule off).

