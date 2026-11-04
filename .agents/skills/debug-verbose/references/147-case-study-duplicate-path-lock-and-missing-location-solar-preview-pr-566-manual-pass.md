## Case study: duplicate path lock and missing-location solar preview (PR #566 manual pass)

**Symptom.** A locked path had an upright end badge and an inverted small lock at
its center. A separate plan had no 2D shadows, an unavailable map and static 3D
shadows while the clock animated.
**Wrong theories.** One badge might be painting twice; the clock-to-light animation
might have regressed. Instrumentation tested both before changing solar behavior.
**Evidence.** A sys.setprofile probe logged `[566-MARKER] groups=1 legacy_parts=2
shared_badge=True`; traceback.format_stack at _build_fixed_marker showed
CanvasScene.update_dimension_lines -> DimensionLineManager.update_all. The solar
probe logged `[566-SUN] clock=10:00 -> 13:00 2d_state=no_location
shadow_changed=False 3d_sun_changed=False`. With Berlin coordinates, 2D became
active and both shadows changed. The owner confirmed setting the location solved
all solar symptoms. Probes were temporary and did not alter the user's plan.
**Root cause/fix.** The dimension layer still painted its former FIXED marker on
paths alongside the new shared badge. Suppress that renderer for PositionLockMixin
objects; retain construction-item markers. Solar behavior was correct, but its
location prerequisite was only explained away from the controls. Add a persistent
translated link beside Hours of Sun that opens the existing location dialog.
**Lesson.** Audit all old renderers when centralizing an indicator. Explain a
missing prerequisite where its dependent controls live. Pin the path regression
before fixing it, and test cancel, zero coordinates, enabled-map recovery and
new-document reset. Native locale/theme/width cases cover hint layout as well as
normal map status. No solar math or animation policy changed.

