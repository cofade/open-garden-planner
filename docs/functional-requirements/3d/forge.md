---
title: "Plant Forge"
prefixes: ["FR-3D-FORGE"]
---

# Plant Forge

Procedural species models, LODs and phenology (#387, ADR-064).

- **FR-3D-FORGE-01**: All 126 sprite recipes (111 species and 15 categories)
  have procedural 3D models in 13 archetypes, using shared art traits and no
  external models. Known heights remain within 3% and crown spread within 10%;
  winter structural wood retains ground contact and recorded height. A bulb
  (tulip, daffodil, crocus, iris, lily) reaches its height with its flower: out of
  bloom, inside its leaf window, it stands as its strap leaves, at about 40-60% of
  that height (#940); outside the window only its neck remains. Three spring bulbs -
  crocus and daffodil from February, tulip from March - keep
  leaves only to early summer and are gone after it, their leaf window fading in
  and out over 14 days (#963); the other `grass`/`allium` recipes stay evergreen.
- **FR-3D-FORGE-02**: Total triangle caps are 25,000/6,000/800 at distance LODs
  up to 18 m / up to 45 m / beyond 45 m. A 256-entry, 64 MiB LRU bounds mesh
  storage. The cache keys its meshes by 2% geometric size buckets and stretches a
  hit to the exact height and the exact scale (the post-fit pin keeps the spread
  within 1.04 of the diameter), so a tree that grows a little every day
  keeps one shape through a bucket instead of being re-forged and re-randomised
  every day (#973); a bucket builds the same mesh for every size inside it.
- **FR-3D-FORGE-03**: Initial silhouettes precede background synthesis. Once a
  plant is forged, a live regrowth pass never downgrades it back to a v0
  silhouette (`ForgeWorker.prepare_for_sync` stretches a warm 2% bucket hit in
  place, stretches the last forged mesh on a cold bucket miss while the background
  worker builds the new bucket, and forges a dated plant that first crosses its
  planting date into an already-forged scene directly; #995). Camera
  movement updates LOD without an edit; stale document/geometry completions are
  refused. Recovery restores progressive upgrades.
- **FR-3D-FORGE-04**: Climbers prefer their trellis parent, then a structure
  within 50 cm of the canopy edge, then a three-pole bamboo tripod.
- **FR-3D-FORGE-05**: Separate flower, fruit/pod and tuber geometry permits
  independent bloom and ripeness. Recorded harvest windows follow the shared
  day-level task calendar and the plan's local frost dates; a perennial's fruit
  shows only inside its fruit months (#940). Flowers are counted by the crown's
  surface and show from every side. Each fruit carries its own phase, so a crop
  ripens one fruit at a time across the window (ripeness 0.55 to 1) rather than
  every apple appearing on its first day (#973); pods carry a phase as well.
- **FR-3D-FORGE-06**: Existing Models respond to seasonal date changes through
  shader/material values. Deciduous leaves and their shadows disappear in
  winter, evergreens retain foliage; illustrative seasons shift in the southern
  hemisphere. Plant existence stays on the shared lifetime rule. Bloom opens over
  the first ten days of its window and fades over the last ten, flower by flower;
  a hardy plant flowers before the last frost, a tender one waits for it; magnolia,
  forsythia, peach, plum and cherry carry few leaves until their bloom ends (#940).
  Beyond 45 m a flowering or fruit-bearing plant (a flower or fruit other than a pod)
  keeps a sparse far representation of
  its crop - large patches of the blossom or fruit colour inside its LOD2 budget
  and its own height and reach - so a blossoming orchard or a ripening berry row
  does not lose its crop at distance (#948). The 64-triangle LOD2 reserve is paid
  only by a canopy that has a far crop; a leaf-only canopy keeps its full foliage.
  Pods and root crowns have no far cue (their green or underground colour does not
  read at 45 m) and keep their LOD2 behaviour.
- **FR-3D-FORGE-07**: The canopy's foliage tip weight is measured over the
  green-leaved canopy sprites only. A red- or purple-leaved canopy sprite is not
  part of that measurement and cannot move it (it uses the same canopy weight, so a
  new colour form cannot re-tint the green crowns) (#969). The 40 golden tree meshes
  pin the resulting colours.

Acceptance: `tests/integration/test_plant_forge.py`,
`tests/integration/test_plant_forge_workspace.py`,
`tests/integration/test_plant_forge_calendar.py`, `tests/unit/test_plant_forge_review.py`,
`tests/unit/test_plant_forge_l31.py` through `test_plant_forge_l34.py`,
`tests/unit/test_phenology.py`, `tests/unit/test_plant_art.py`,
`tests/unit/test_object_sprite_conformance.py` and the 40 golden tree references.
The production Beauty Board, actual engine seasonal checks and owner acceptance
complete the evidence.
