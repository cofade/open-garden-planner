## Case study: a sun-selection wait observed an earlier refresh (#930)

**Symptom:** Coverage partition 1 of version-sync PR #929 failed the new
unmeasured sun-selection regression: the canopy panel had zero rows instead of
one. The same test passed in prior complete runs and independent reviews.

**Wrong theories:** Version metadata did not change the coordinator. The UI was
not refusing the selection: its deferred refresh eventually populated the row.
An earlier nonempty evaluation cache did not prove that refresh had run.

**Key evidence:** Caller-stack and state prints wrapped the coordinator refresh.
Forcing the ordinary initial refresh before selection made both location variants
fail deterministically with the old wait, rather than relying on covered-worker
timing:

```text
[SUN-WAIT] before selection True 0
[SUN-WAIT] after old wait True 0 True
```

The values are nonempty evaluations, canopy rows and (on the second line) an
active refresh timer. A later tagged callback showed one canopy row. CI had
12,533 passing cases beside this one failure; suppressing it by retry would
have hidden the stale-condition race.

**Root cause:** The test waited for any evaluations after selecting a tree.
When initial evaluations already existed, that condition returned immediately
before the selection's 60 ms debounce updated the canopy panel.

**Fix and lesson:** Pre-populate evaluations deliberately, then wait for the
canopy row caused by selection and its removal after deselection. Keep all
zero-geometry-walk and unavailable-evaluation assertions. No application change,
timing threshold increase or expected-failure marker is required. A wait must
identify the result of the current gesture, not an older cache or an unrelated
ready flag. See §8.10 and
`tests/integration/test_sun_mismatch.py::test_unmeasured_selection_and_preview_do_not_collect_shadow_geometry`.
