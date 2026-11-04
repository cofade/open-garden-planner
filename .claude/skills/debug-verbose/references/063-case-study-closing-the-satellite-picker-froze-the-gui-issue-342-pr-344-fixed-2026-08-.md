## Case study: closing the satellite picker froze the GUI (Issue #342 / PR #344, fixed 2026-08-31)

**Symptom**: Closing the satellite picker during a slow Static Maps request could freeze the whole application until the HTTP timeout elapsed.

**Theories entertained (wrong)**:
- The worker's interruption request would make the network call stop immediately.
- A finite HTTP timeout made a synchronous join safe enough for dialog teardown.

**What targeted lifecycle review revealed** (the regression test holds the worker inside a simulated in-flight request): `MapPickerDialog.closeEvent()` called `requestInterruption()` and then `worker.wait()` on the GUI thread, but `google_maps_service._fetch_tile()` cannot observe cancellation while `requests.get(timeout=10)` is active.

**Root cause**: cooperative cancellation was paired with a blocking GUI-thread join, so the dialog's close path inherited the network timeout.

**Fix** (the dialog lifecycle): `closeEvent()` now ignores the close request, asks the worker to stop, and rejects asynchronously after the worker's terminal signals clear ownership and in-flight state. Unexpected failures log a traceback only after `_scrub_key()` redaction.

**Lesson**: a cancellation request is not a completion guarantee; Qt dialogs must own network workers asynchronously and must never wait on them from the GUI thread.

