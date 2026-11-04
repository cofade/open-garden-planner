## Case study: timeline changes 3D growth but the 2D sprite stays at today (#315)

**Symptom:** two timeline dates produced the same 2D sprite while the collectors grew
the tree. **Wrong theories:** no new growth formula was needed; a first pixel sampler
was also masked by the translucent spacing-ring fill (40000/40000 sampled pixels).
**Evidence:** `[F4-GROWTH] sprite_day=2026-10-19 plan_day=2025-06-01`, then the same
sprite day for 2030, with traceback through scene.render and CircleItem.paint.
**Root cause:** `_visual_plant_diameter_cm` passed date.today; cached canvas paint
also needs invalidation when the shared date moves. **Fix:** read scene.plan_date,
invalidate the plant cache on refresh, and compare actual rendered pixels with the
spacing overlay disabled. **Lesson:** assert the user's image, and isolate the overlay
that can swamp a measurement. Instrumentation removed; the regression remains in
tests/integration/test_plan_timeline.py.

