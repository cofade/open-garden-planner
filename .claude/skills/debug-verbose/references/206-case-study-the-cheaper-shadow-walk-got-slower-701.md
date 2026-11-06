# Case study: the cheaper shadow walk got slower (#701)

## Symptom

The sun-overlay test with 150 identical sheds took ~4.9 s after an "optimisation" that
removed 150 pyclipper unions, against ~2.6 s before it. A per-owner union whose only
output (`owned_shadows`) had **no production reader** was supposed to be free to remove.

## Wrong theories

1. *The machine drifted.* The dev box does drift 37–63 % (AGENTS.md), so the first
   explanation was noise. A profile showed the regression in the union itself.
2. *The roof cache would hide it.* The cache removed the 750 roof-mesh builds, but the
   union cost grew by more than that saving.
3. *`include_owned=False` skipped unused work safely.* It skipped **load-bearing**
   pre-merging, not just output formatting.

## Key evidence

- Before: 153 `_union_int` calls, 1.48 s total (150 per-owner + the global union).
- After: 3 `_union_int` calls, 3.25 s total — the single global union of all 3,750
  unmerged roof-triangle paths dominated.
- The per-owner union pre-merged each building's roof triangles, so the final union saw
  150 small polygons instead of thousands of overlapping triangles.

## Root cause

An output field with no reader can still be the by-product of work that makes the rest of
the pipeline cheap. `owned_shadows` was unused, but building it kept the global union
small.

## Fix

Keep the per-owner union; keep the **roof-triangle cache** (one build per distinct
building geometry). Recorded in ADR-059 so the next attempt starts from the measurement.

## Lesson

Measure the whole pipeline, not the call you removed. "No reader" is not "no work": check
what the unused result was pre-computing for everyone else.
