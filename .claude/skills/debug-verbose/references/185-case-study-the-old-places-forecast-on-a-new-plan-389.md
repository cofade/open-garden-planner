# Case study: the old place's forecast on a new plan (#389, fixed 2026-11-02)

**Symptom.** With the 3D view's Today's Weather chosen, File › New left the old plan's
forecast in place:
- the 3D sky kept the old place's weather;
- the Planting Calendar showed its forecast strip with no location set;
- the new plan's frost alerts and badge were computed against the old place's weather.

An Open at another place fetched for the OLD place first. The senior review (L5, round 2)
reproduced this with an isolated probe. The seam test did not catch it: it patched
`WeatherWidget.refresh` out and emitted the signals by hand.

**Theories entertained (wrong).**
1. "The forecast is never cleared." It was: the slot forgot it, and then asked again.
2. "The worker for the old place is not cancelled." That was true but secondary. Cancelling
   alone would have left the ask itself fetching the wrong place.
3. After the fix, "a guard that drops a result for another place is needed too." It was
   written and documented, and the next review measured that its drop branch never fired
   (see Lesson).

**What instrumentation revealed** (the reviewer's probe, a faked `fetch_forecast` recording
each call, around `_new_project_document`):

```
right after File>New: location = None forecast = () fetches = [(52.52, 13.405), (52.52, 13.405)]
1 s after File>New:  location = None forecast = (('2026-11-02', 63),)     <- the old place's
frost_alerts_ready emissions after File>New (no location): 1
```

The second Berlin fetch was started by File › New itself, before the location was reset.

**Root cause.** `CanvasScene.document_replaced` fires inside `canvas_scene.clear()` /
`_apply_to_scene`, BEFORE `ProjectManager` resets or restores the location. The 3D view's
slot asked for a forecast there, and the calendar read the old place's location.
`WeatherWidget.set_location` did not cancel the worker when the place changed.

**Fix.**
- The document slot only forgets (`WorkspaceLivingCoordinator.document_changed`).
- `location_changed`, which always follows a new, opened or recovered document, asks.
- `WeatherWidget.set_location` cancels and disconnects the old place's worker.
- Pinned by `test_a_new_or_opened_plan_never_follows_the_old_places_forecast`. It holds a
  real fetch in flight with a `threading.Event`, and it failed on the old code with the
  reviewer's symptom.

**Lesson.**
- A "document replaced" signal is a goodbye, not a hello: read nothing place-dependent in
  it, including from the project manager. Ask on the signal that carries the new value
  (PF-LIF-12).
- Measure the mechanism before documenting it: the disconnect already protected, and the
  extra guard was dead code. The rule and its limit (undecorated slots only) are stated once,
  in PF-LIF-12.
- Round 4 found a second path: with the calendar's tab hidden and Today's Weather not chosen,
  nothing moved the widget on a place change, and the 3D side GUESSED that a forecast was the
  plan's. Have the producer say where it fetched; never infer provenance at the consumer.
- A seam test that patches out the thing doing the work (here `refresh`) cannot see a bug
  in it. Fake only the network (`weather_widget.get_weather_service`).
