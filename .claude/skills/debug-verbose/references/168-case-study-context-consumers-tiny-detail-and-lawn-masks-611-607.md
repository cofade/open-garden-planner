## Case study: context consumers, tiny detail and lawn masks (#611/#607)

**Symptom.** A house retyped as a greenhouse carried its former door context
inside a hold. A 0.1 cm rain barrel failed the normal/winding gate.
**Wrong assumption.** Lawn-blade presence classified every context transition;
nominal detail joints would remain valid at every positive size.
**Evidence.** The fake-clock regression found `door_wall` in the GREENHOUSE
params; the tiny barrel's MeshError reported a winding dot of -1.0 against 0.99.
`[607-MASK]` measured 36,000 roots against 5,990 edges at 569.11 to 19.25 ms and
16,000 edges at 1,835.06 to 59.07 ms, with identical masks (three-run medians on
a concurrently loaded machine). `[611-STOP]` counted two builds with the bracket
cap, seven with it removed.
**Root cause and fix.** Context eligibility belongs to consumers: intersect old
and new door targets and heightless-lawn eligibility. Fixed joints must yield to
an exact prism below 3 cm. Batch exact even-odd masks by vertical range with at
most 65,536 temporary point/edge pairs; retain the small-ring fast path. Admit
blades only for High/Ultra; centralize roof clamps.
**Lesson.** Pin work avoided as well as final dimensions, and classify parameters
from the consumers that actually take them.

**Senior-review follow-up (#600).** The first visibility export marked a hidden
shadow-casting seasonal part as ground detail, violating MeshPart's invariant
that ground detail casts no shadow. Fail-first flowers/fruit regressions reproduced
the ValueError. The oracle-only excluded copy now clears casts_shadow as well;
part indices and the sink's original part remain intact. Standing arc42 preset
and meadow descriptions were corrected alongside the new addendum.

**Qt picker follow-up (#600).** After the held-mesh fix, one stable birch ray
still disagreed. `[600-FACE]` printed two negative determinants (-903.39 and
-923.48). Qt 6.11.0's qssgrenderray.cpp accepts only positive determinants; its
back-face branch is commented out. The raw mesh export remains two-sided, but
the engine-specific selection witness filters camera-facing triangles. Tests
pin both windings, keep the general collision/analysis cast unchanged and require
recharacterization on Qt upgrade. Eighty seeded candidates retain the original
minimum45 robust comparisons; no failing ray is individually excluded.

**Minimized-window follow-up (#603).** Several G7 soaks refused a hidden host
or timed out waiting for forge admission. The decisive state was
`window_visible=True minimized=True pane_visible=True pane=False`; no host.hide
call had occurred. Windows started the native app minimized, so the product
correctly paused its controller and forge. The test's user-entry helper now
restores a minimized window before entering 3D. It keeps every rest condition,
uses a real QWidget regression, and removes temporary hide-stack instrumentation.

