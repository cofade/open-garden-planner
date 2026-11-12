## Case study: a correct formatter left two open 3D labels metric (#673, fixed 2026-11-12)

**Symptom**: after a unit switch, an open tour list and Photo Mode focus label
still showed metric values. The card and eye-height menu changed correctly.

**Wrong theory**: changing each format call would suffice because the next redraw
would refresh it. These widgets retain their text until their own controls change.

**Evidence**: the independent creator's real-widget probe recorded unchanged focus
and keyframe text, with unchanged camera, keys and PhotoSettings. Tagged entry prints
with caller stacks then showed `_say_focus` on the metric control changes and no
refresh call after the preference transition:

```text
[UNIT-REFRESH] _say_focus metric ... set_photo_mode
[UNIT-REFRESH] _say_focus metric ... _on_controls_changed
[UNIT-REFRESH] changing to imperial
```

**Root cause**: both retained text surfaces lacked a unit-notifier subscription.
The planned tour hook had matched `QListWidget()` but the constructor used
`QListWidget(keys)`; the focus label was incorrectly treated as transient.

**Fix**: connect the actual tour list to `_show_keys` and the initialized capture
coordinator to `_say_focus`. Instrumentation was removed. The regression
`tests/integration/test_unit_system.py::test_switching_units_refreshes_photo_focus_and_tour_rows`
switches units on the open widgets and also asserts that the camera, keys and photo
settings remain unchanged.

**Lesson**: formatting on creation and refreshing an already shown surface are
separate contracts. Assert both through the widget.
