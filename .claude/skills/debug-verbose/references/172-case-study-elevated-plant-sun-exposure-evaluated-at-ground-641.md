## Case study: elevated plant sun exposure evaluated at ground level (#641)

**Symptom.** Plants elevated in raised beds or planters received unexpected shade
warnings from low garden structures such as 50 cm fences.
**Wrong assumption.** Plant base height was tracked for 3D standing models and shadow
casting, so receiver shade evaluations were assumed to be height-aware.
**Evidence.** Inspection of `core/shade_aggregation.py` showed receiver coordinates
`(x, y)` evaluated against unified ground-plane caster projections (`z = 0`) regardless
of plant soil elevation. A 50 cm fence cast a 100 cm shadow covering an 80 cm raised
bed, falsely giving 0 hours to a plant standing above the fence height.
**Fix.** Pass `elevation_cm=item_base_cm(...)` to `SunReceiver`. In `_aggregate_day`,
group receivers by elevation. Slice obstacle casters relative to receiver elevation
`e` (`z_top = b + h`, skip if `z_top <= e`, else effective base `b' = max(0.0, b - e)`
and effective height `h' = z_top - max(b, e)`), projecting elevated plane shadow polygons
with bed sparing preserved. Pinned by `tests/unit/test_sun_exposure_base.py` and
`tests/integration/test_sun_exposure_raised_soil.py`.
**Lesson.** A receiver in 3D space cannot sample a 2D ground projection when surrounding
occluders have heights below the receiver plane.

**Review regression (PR #645).** Tagged boundary probes reported
`[ELEVATION] actual=38.0 band=40 obstacle_top=39.0 discarded=True`.
Six vertical-translation cases failed before removing the 5 cm rounding.
A 1 cm wall slice at the true plane yielded 780 minutes; rounding it away
yielded 990. Share sweeps at identical exact elevations only; precompute
receiver indices and exclusions outside the daylight loop.
