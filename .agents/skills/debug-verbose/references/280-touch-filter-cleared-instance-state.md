# Case study: A late viewport event reached the touch filter without its flag (#666 review)

**Symptom.** The Linux coverage run failed in a minimum-window-size test with
an AttributeError from the canvas touch filter.

**Wrong theory.** The test's minimum-size assertion or a real touch gesture
caused the failure.

**Key log.** [TOUCH-LATE] view instance flag missing. The captured stack
entered CanvasView.eventFilter from a live Qt viewport while the Python
instance no longer had its touch flag. A targeted test removed just that
attribute and reproduced the CI exception.

**Cause and fix.** The Qt callback could run after Python cleared instance
state (PF-CAN-61). Give the touch flag a disabled class-level default and
read it before consulting the viewport. The constructor and preferences
still set the active flag on the instance.

**Lesson.** An unrelated resize test can be the first event after a different
canvas has begun teardown. Guard the callback that raised and test that
callback with its instance state missing.
