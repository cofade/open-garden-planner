---
id: ADR-056
title: "Runtime sun diagnostics and document-owned exposure"
status: "Accepted; owner testing confirmed on 12 October 2026, shipped in [v1.30.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.1) via [PR #436](https://github.com/cofade/open-garden-planner/pull/436)."
refs: ["#314", "#428"]
legacy_anchor: adr-056-runtime-sun-diagnostics-and-document-owned-exposure-314-428
---

# ADR-056: Runtime sun diagnostics and document-owned exposure

**Status:** Accepted; owner testing confirmed on 12 October 2026, shipped in [v1.30.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.1) via [PR #436](https://github.com/cofade/open-garden-planner/pull/436).

Control layout, the 21 June shortcut and explicit-only refresh are superseded by ADR-062. The receiver-estimate model remains applicable.

**Context.** A raw ground heatmap sampled inside a solid receiving plant includes its own shadow: both reference tomatoes measured zero hours. The issue's literal centre lookup therefore cannot distinguish the shaded northern plant from the sunny southern plant. A second defect lets an old worker paint after New/Open because document replacement did not cancel the heatmap or invalidate queued success.

**Decision.** Use the shared `SimClock.plan_date`, with an opt-in **21 June** shortcut retaining the current simulation year. Only the explicit Hours of Sun action computes. One worker accumulates the unchanged ground grid plus sparse receiver exposure at the corresponding cell centres, excluding only each receiver's identified caster. The established integer-grid sweeps, solar positions, date-projected growth and 15-minute sampling remain authoritative. Per-owner unions combine overlapping footprints before coverage counting; bbox pruning and vectorized even-odd point sampling avoid one full aggregation per plant.

The Qt-free classification service derives nominal bands from the existing 2/4/6-hour boundaries. Warning limits are strictly `<5` for full sun, `<3` or `>7` for partial sun, `<1` or `>5` for partial shade, and `>3` for full shade. Exactly one hour outside a nominal boundary is tolerated. UNKNOWN never warns. Compare unrounded values; display one decimal. Every mismatch is warning severity.

Results belong to a document generation and a snapshot of date, location, canvas bounds, identified caster footprints/effective heights and receiver identities/positions. Validate the snapshot before publishing; scene/command/location/date changes compare it in a 60-ms, idempotent coordinator. Requirement-only edits can reclassify valid cached hours. Geometry changes clear measurements and warnings while retaining the ordinary heatmap as an explicitly stale visual snapshot. Date changes and document replacement clear the overlay. Time-only changes preserve daily exposure. `CanvasScene.document_replaced` is the sole document reset seam, before C++ item teardown and after load prevalidation; rejected loads preserve the active result. A cancelled worker remains owned until queued `finished` cleanup; no second launch is accepted meanwhile.

The shared Diagnostics coordinator publishes guild, sun and existing warnings together. Cached `sun_mismatch` records include hours, requirement, ISO date, direction, measurement method and receiver UUID. `sun_evaluation` information records expose unavailable known requirements. Group navigation addresses the enclosing object while retaining the physical receiver UUID. Reads remain unauthenticated, read-only and computation-free.

**Canopy grouping.** One selected TREE groups other footprint centres inside or on its recorded mature `max_spread_cm / 2`, independent of guild, drawing layer and bed. Enum order, translated name and UUID define ordering; missing traits are Unspecified. Missing mature spread produces an unavailable hint, without a spacing override. This geometric membership does not establish the cause of shade.

**Limits and alternatives.** These are estimates of direct sun at ground level excluding self-shadow, not leaf-height measurements or a translucent-canopy model. No automatic recomputation, new date owner, persistent setting, dependency or file-version change. Re-running the full day per receiver was rejected: the planning probe took 17.6 seconds for 20 receivers among 100 casters. The implemented 200-caster/receiver test measured **3.226 seconds** locally (10-second target, 30-second CI ceiling); final delivery reports retain actual repeated timings.

**Evidence.** The committed 24 m × 24 m Berlin plan, 21 June 2026, has a 10 m tree at (12 m, 12 m), 3 m canopy radius, tomatoes 1 m north and 8 m south: independently measured expected values are **0 h north and 16.5 h south**, excluding own casters. Unit tests pin sparse/reference parity, holes, multi-footprint ownership, raw-grid equivalence, strict tolerance boundaries and unavailable states. Integration tests pin explicit compute, badges, panel/MCP parity, canopy navigation, geometry, invalidation, worker responsiveness and document replacement during running/queued results; malformed loads retain the map. #328 shipped in PR #352 and is outside this PR.

**Addendum — merged into the Living Garden 3D tree (#385, story L1.3, 2026-10-12).** Two
changes to what this decision ships, both in the plain data the one walk hands the worker.

1. *Where a caster stands.* `IdentifiedCaster` gained `base_cm` (ADR-037's base-stacking
   addendum: a plant on a raised bed's soil is a solid `footprint × [base, base + height]`).
   `collect_identified_casters` is THE walk — one `ItemLookup`, `footprints.item_base_cm` per
   item — and `collect_shadow_casters` flattens it for the overlay; `compute_grouped_shadows`
   takes `GroupedCaster(footprints, height_cm, base_cm)`. The heat-map grid, the per-owner
   unions and the overlay therefore sweep the same solid (pinned: the grid of
   `compute_sun_exposure` equals `compute_heatmap` over the overlay's casters, bases included).
2. *A plant is not shaded by the soil it stands in.* **Measured on v1.30.1**: a tomato in a
   40 cm raised bed in the open, Berlin, 21 June — **0.0 hours**, a `too_little` mismatch and
   the warning badge; 16.5 hours for the same tomato on open ground. The estimate samples the
   ground point under the plant and left out only the plant's own caster; the bed is a caster
   too, and its footprint covers that point all day. So every plant in every raised bed
   warned. `SunReceiver` gained `stands_on`: the id of the soil parent the plant stands in —
   `footprints.standing_parent`, the membership half of the base rule (linked, visible, a
   soil-capable solid with a height, the plant's centre inside) — and that caster is spared
   for this receiver like its own. Merged tree, the same day: **16.5 h** on the bed; 10.5 h
   for a small plant on the ground 10 cm north of the bed; 11.5 h on the bed with a 3 m wall
   60 cm south of it, exactly what the same plant reads with the bed removed; 16.5 h in a bed
   2 cm high (a solid that lifts nothing: "is the plant in the parent's solid?" is asked, not
   "is it lifted?").

**Limits, stated.** Every OTHER caster shades a receiver as at ground level: a neighbour on
the same raised soil casts onto the ground plane from `base / tan α` on, so right behind it
the estimate is too sunny (pinned as a decision). A plant inside a bed's outline WITHOUT a
link to it stands on the ground inside the bed's solid and reads 0 hours — the bed-membership
follow-up, not this decision. `measurement_method` keeps its identifier
`ground_cell_centre_excluding_self`. The coordinator's clock subscription goes through
`connect_qobject` and nothing hangs on its own `destroyed` signal (ADR-053 addendum "L1.3":
in bare PyQt the closure v1.30.1 hung there runs 0 times when the wrappers are collected
before Qt's deferred delete, 5 of 5); its theme listener asks at the moment of use and takes
itself off the registry.

**Addendum — the estimate spares the soil solid a plant stands in, linked or not (#481,
2026-10-27).** The paragraph above ("reads 0 hours — the bed-membership follow-up") is
reversed for the ESTIMATE, because the follow-up (#443) is not a prerequisite for reading
the right sun. **Measured on master**: a full-sun tomato inside a 40 cm raised bed whose
outline contains it, Berlin, 21 June — **0.0 h** and a `too_little` mismatch when the link
was never made (a bed drawn around the plant, a mirror copy without its bed, a move by the
arrow keys or a typed coordinate), **16.5 h** linked. The link is bookkeeping and follows
only some edit paths; the geometry is the fact.

`IdentifiedCaster` gained `holds_plants` (the walk's `is_solid_soil_parent`: a bed, raised
bed, container or wall planter with a resolved, positive, finite height — the predicate
`object_height` already documents as "the per-plant sun estimate must not count that solid
as shade"). `_aggregate_day` spares such a caster for every receiver whose own point lies
inside its outline, on top of the existing `stands_on` link spare. It is a PER-RECEIVER
spare, not a hole in the bed's shadow: a plant 15 cm north or south of the same bed still
loses sun to it (pinned). The test is static for a run, so it costs one pass of
`points_in_polygons` per soil caster per run, not per sample. A `WALL`, a `TRELLIS` or an
in-ground bed with no height is NOT spared (pinned) — a solid that contains the point but
cannot hold soil is still between the plant and the sun. **Why not fix the link instead**:
making the link, or the base, follow the geometry is #443, whose nesting decisions (a
trellis in a bed, a pot on a bed) are open; this addendum changes only what the estimate
leaves out, and leaves where a plant STANDS (FR-SUN-11, `item_base_cm`) exactly as shipped.
The residue is stated: an unlinked plant inside a raised bed still casts its OWN shadow
from the ground (its base is 0), so its estimate is right and its own shadow is the known
link gap. Pins: `tests/integration/test_sun_exposure_raised_soil.py` (the
no-link estimate, the per-receiver spare with a neighbouring plant, the wall negative
control, the walk-vs-predicate drift guard). No `.ogp` change, no `FILE_VERSION` bump, no
user-visible string.
