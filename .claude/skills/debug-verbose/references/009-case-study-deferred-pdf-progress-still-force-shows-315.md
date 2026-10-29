## Case study: deferred PDF progress still force-shows (#315)

**Symptom.** A second progress dialog covers the operable readiness Cancel button.
**Wrong theory.** Setting minimumDuration to INT_MAX was assumed to delay creation.
**Evidence.** Independent Qt 6.11 instrumentation recorded constructor value -1,
minimum 0, and both dialogs visible at 4.6 seconds in the real export handler.
**Root cause.** The constructor's four-second force-show timer is not restarted by
setMinimumDuration while value differs from minimum.
**Fix.** Construct generation progress only inside the admitted render callback;
close/delete it in finally. A real held-worker regression waits 4.3 seconds and
asserts only readiness progress is visible before allowing the current-map export.
**Lesson.** Match object lifetime to readiness, rather than trying to silence its timer.
Pinned by test_pdf_generation_progress_is_created_only_after_map_readiness.

