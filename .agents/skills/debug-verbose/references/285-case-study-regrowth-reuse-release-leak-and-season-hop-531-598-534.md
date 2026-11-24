# Case study: a regrowth that destroyed Models, a release that leaked textures, and a season hop that paid for reads (#531, #598, #534)

## Symptom
A held date key (20 dated apple trees, a regrowth on every step) grew committed memory by 2.2-3.4 MB per step and GPU memory by 66-79 MB a minute (#531). The 300-plant seasonal scrub sat at 13.2-15.3 ms of a 16 ms budget and failed on a Windows CI runner (#598). The wind soak had been a non-strict xfail since L1.9 (#534).

## Wrong theories
- "Reusing a Model draws nothing" (ADR-069 withdrew #531 on it). True only for what was tried: a NEW geometry object assigned to the live Model. Loading new buffers into the geometry object the Model already has draws - the selection ring had done it since L1.8.
- "Model churn is the #531 cost." Reuse alone moved a step from 2.2 to 1.9 MB. The rest was the workspace counting every regrown item as "lost its Models" and calling `releaseResources()` - and each release lets Qt keep about half of the ground's tile textures (#532).
- "The season hop costs what it writes." With NO value changing it still cost 7.3 ms.
- "#534 is intermittent, so it is still there." Nine runs on Qt 6.12.0 were flat.

## Key measurements
```text
date playback, 60 s, interval_ms=0      master 121 steps, 2.23 MB/step, 6 releases
                                        branch 429 steps, 0.27 MB/step, 0 releases, 35,964 Models reused, 67 destroyed
QQmlExpression probe, 600 seasonal parts  same values again 7.3 ms = payload->JS 2.7 + property reads 4.6
                                        seasonTint writes 10.2 ms vs seasonDensity 1.2 ms
payload shapes (one QML call)           dict of 300 lists 2.15 ms, ids + flat list 1.54, ids + float64 QByteArray 0.11
```

## Root cause
1. `replace_geometry` destroyed and recreated every Model of a regrown item, and the workspace counted every geometry change as a retirement, so releases (and their #532 texture leak) followed every few date steps.
2. `setPlantSeasons` received a dict of lists (an expensive QVariant -> JS conversion), visited every part, and compared through `part[name]` reads, each a generic QObject lookup (a vector3d read allocates a wrapper).

## Fix and lesson
- `replace_geometry` reuses a Model of the same kind/surface/ground-detail/fill and calls `BufferGeometry.reload` on the object the Model already has; the sink counts `items_retired`, and the workspace releases by that count. Proven in pixels: a forged tree regrown in place equals fresh Models channel for channel.
- Seasons cross as ids + one float64 buffer; the scene indexes its seasonal parts and compares against the numbers it last wrote.
- Lessons: a withdrawn approach is only as dead as the variants that were actually measured - read the withdrawn diff, not its summary. Measure the cost of a QML call with no state change before optimising its writes. When a soak suspect goes quiet, run the gate every time in a row before turning an xfail back into an assertion.
