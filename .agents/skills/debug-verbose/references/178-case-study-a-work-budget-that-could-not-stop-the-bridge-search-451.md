# Case study: a work budget that could not stop the bridge search (#451)

**Symptom.** One polygon whose holes *touch* its outer ring held the GUI thread for
0.6–1.5 s before the 3D snapshot refused it (`outline_too_large`, no solid, the 2D
plan untouched). `scripts/measure_region_work.py` named it as the only family above
its price: 3.6 to 8.1 time-per-charged-unit against a reference of 1, and every other
row of the 61 stayed at 2.1 or below. The code comment said so and said "known, not
re-priced" (review of fix round 4), which is why it survived four rounds.

**Wrong theories.**

- *"The budget is not checked inside the bridge search."* It is: per hole and per
  block of candidates (`polygon._bridge_position`).
- *"`_inside_corner` walks the loop."* It reads three vertices and does three cross
  products — O(1).
- *"The refusal is from the size check, so no cut runs."* Only for a ring large
  enough to fail `region_work`; the 110-hole ring passed it and cut for 500 ms.
- *"The sort of the boundary dominates."* It is charged (`_HOLE_VERTEX_UNITS`) and
  showed no anomaly in the script's per-step table.

**Evidence.** The block charge was `_BRIDGE_UNITS = 60` * len(first)` — 60 units per
edge. A block of six candidates then tests those six against every edge at once
(six `_touch` passes over the whole boundary). For a hole that *bridges*, the first
block usually succeeds, so the price looked right. For a hole that *touches* the
wall, the nearest boundary vertices are hidden and every candidate is blocked: the
search takes block after block, and every failing block cost 8 times its charge.
Measured with a temporary experiment (dev box, reference unit 0.95–1.00 ns):

| `_BRIDGE_UNITS` | 89 touching holes | 110 holes | 200 holes | worst cost-to-price |
|---|---|---|---|---|
| 60 (shipped) | built, 148.2 M, 0.37–0.65 s | refused, 505 ms | refused, 1000 ms | 8.06 (script) |
| 600 | refused, 82 ms | refused, 73 ms | refused from size, 14 ms, **0 bridge calls** | 1.3-1.5 (runs) |

**Root cause.** A price fitted to the success path of a call. `_triangulation_floor`
uses the same constant, so the underprice also let a 200-hole ring reach the cut
instead of being refused before it.

**What it costs.** The same constant feeds the pre-cut floor (\_triangulation_floor\), so the
re-price also raises the least a region with many holes can cost: a crafted 25 x 25 line grid
(625 crossings) is now refused from its size where it used to resolve; a 22 x 22 grid still
resolves (286 regions, 25.6 M units), and a closed fence's one hole costs about 1 M. That is
stated in section 8.29.1 and ADR-059 rather than hidden, and pinned by
`test_a_625_crossing_grid_is_refused_from_its_size_after_the_reprice`.

**Fix.** `_BRIDGE_UNITS = 600`, plus the measured capacities in the comments, §8.29.1,
ADR-059 and the script's docstring. The regression pin counts `_bridge_position`
calls: ≤ 40 for 110 touching holes (30 measured) and exactly 0 for 200 (refused from
its size). No clock is read in the test; the script remains the timing gate.

**Lesson.** Price the *failure* form of a call, not only the form that usually
succeeds. A family that is "known and not re-priced" in a comment is an open bug
with a note attached — the fourth review read it and moved on. Also: when the same
constant feeds the pre-cut size floor, re-pricing it fixes two symptoms at once
(the refusal *and* its cost), which is the sign it was the right knob.
