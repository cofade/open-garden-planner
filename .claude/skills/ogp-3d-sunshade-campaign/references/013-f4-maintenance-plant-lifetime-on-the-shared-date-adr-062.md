## F4 maintenance: plant lifetime on the shared date (ADR-062)

The plan timeline reads/writes the existing SimClock. Presence is inclusive planting,
exclusive removal. CanvasScene combines this with layers before the existing visible
shadow/heatmap/3D collectors run. The 2D sprite also reads scene.plan_date and invalidates
its cached paint on a date refresh. Fresh plants use the selected plan date; copies
and loads keep stored dates. No changes to solar/growth math; the production Qt Quick 3D workspace follows its existing clock subscriptions.
Visual exports use current presence; API reads retain absent plants. Season Manager
continues to copy complete yearly files. See tests/integration/test_plan_timeline.py.


F4's combined-controls follow-up retires the simulation visibility switch, decorative
shadow toggle and 21 June shortcut. SunSimToolbar is permanent; its monthly slider
preserves the chosen day. Hours of Sun is opt-in live intent: LiveSunMap coalesces
semantic input changes, keeps a correctly dated old preview, and publishes only current
receiver measurements. Time-only animation never launches a full-day map. All image/
PDF exports use SunExportGate readiness, animation leases and identity checks; API
waiting occurs outside Qt. Tests: test_plan_sun_controls.py and test_timeline_quick3d.py.
