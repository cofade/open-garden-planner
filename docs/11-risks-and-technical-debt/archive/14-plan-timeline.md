# Plan timeline and live sun integration (#315)

### Timeline growth must change the rendered sprite, not only its collectors (#315)

The existing 3D/shadow collectors read SimClock.plan_date, but CircleItem's sprite
resolver read date.today. Tagged evidence recorded `[F4-GROWTH] sprite_day=2026-10-19
plan_day=2025-06-01` and the same sprite day after scrubbing to 2030, with a stack
through scene rendering. The resolver now reads the scene's shared date and a date
refresh invalidates DeviceCoordinateCache. The mature footprint remains unchanged.
The regression compares rendered canopy pixels at two dates. Its first sampler was
itself wrong: the spacing ring's translucent fill covered the sampled region at both
dates (40000/40000 pixels), so the final sampler explicitly disables that overlay.
PDF text extraction may break lines between glyphs despite correct rendered layout;
whitespace is normalized for content checks and rendered pages are inspected.


### A live sun-map preview is not a current measurement or an export (#315)

The former on-demand map intentionally disappeared on date changes. Retaining its
pixels for the combined timeline requires three separate identities: desired inputs,
in-flight snapshot, and the snapshot whose image is actually displayed. The launched
worker's computed_day changes before its result arrives, so it cannot label the old
image. displayed_snapshot is updated only on accepted success; stale measurements
are cleared immediately and cannot feed badges. The preview remains visibly dated.

Export readiness must also guard the no-map case: a document can be replaced between
two API GUI hops even when its exposure Future is already ready. SunExportGate checks
generation (zero before the first replacement), plan revision and wall time immediately
before writing. Its waits happen outside the API bridge call; cancellation and timeouts
write nothing. The pending-Future test, map date/late-result tests and guarded GUI/API
export tests pin these distinctions. Shutdown is idempotent, including a second call
after QObject teardown; the test fixture releases its controlled workers on cancel.


### Derived lifetime visibility must not announce a plan edit (#315)

The first native Quick3D review found ten regrowth snapshots in 156–172 ms when
ten date steps crossed a planting/removal boundary; the same-presence control
produced none. Tagged stacks traced Qt's ItemVisibleHasChanged through the plan
revision signal to the controller's immediate edit path, bypassing its 500 ms
date throttle. refresh_timeline now scopes only those visibility announcements
as derived runtime state (restored in finally). Manual visibility, layer commands
and lifetime undo/redo still announce edits. Separate-event-loop boundary tests
pin both halves. The identical probe reads zero extra snapshots/revisions after
the fix and the existing clock's trailing update produces the final state.

Translated layout also needs its own evidence: German's first three control
groups missed the available 800-pixel content width by two pixels despite English
passing. The actual group hints, not a guessed Qt cache bug, explained the third
row. Narrow sliders now leave translated text headroom; native-widget captures
and two-locale regressions supplement the English geometry tests.


### Debounce collection and own abandoned export calls (#315)

Worker-count tests missed 154 synchronous whole-scene captures during one 150-item
layer command. Live-map notifications now dirty cheap state; collection occurs once
after debounce, and requirement-only changes restore cached measurements. The bulk
command regression asserts both synchronous and eventual capture counts.

A completed map Future also masked a real-dialog Cancel in the same event turn.
Cancellation now wins independently. Generic bridge timeouts leave queued calls in
Qt, so an abandoned begin could acquire a permanent animation lease and an abandoned
render could write later. Locked operation state refuses late admission and releases
leases through queued Qt cleanup. Fail-first tests withhold actual bridge delivery
until after timeout, then assert resumed animation and absent output files.
