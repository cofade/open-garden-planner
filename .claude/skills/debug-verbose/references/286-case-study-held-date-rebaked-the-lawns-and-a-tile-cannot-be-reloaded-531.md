# Case study: a held date key re-baked the lawns twice a second, and a re-baked tile cannot be reloaded (#531, owner's manual test)

## Symptom
The owner's manual test of the #531 package: the arrow key held in the date field from today to 1 July 2031 on the food-forest example. The process grew from about 950 MB to over 1.4 GB in a few minutes, "no end in sight". The package's own gate (20 dated trees, 60 s) had measured 0.25 MB a step and a flat GPU.

## Wrong theories
- "It is the residue of the regrown trees (#1013)." 13 kB a tree is 2 MB for 150 trees, not 450.
- "The JavaScript heap of the QML engine collects late." A `collectGarbage()` after every `set_plant_seasons` and `set_ground` call changed nothing (four 150 s arms, slopes of 58-76 MB/min with and without).
- "The 60 s gate was representative." Its 20 trees had no lawn: a lawn's fill follows the date, and the gate's plan never re-coloured one.
- "An in-place reload fixes it, as it did for the geometry." It does not draw (below).

## Key measurements
```text
host calls stubbed (food forest, 90-240 s)   all engine calls stubbed          -52 MB, slope 3.7 MB/min (flat)
                                             set_ground stubbed                +25 MB, second-half slope 0.0
                                             seasons / reloads / sun / look    each inside the +-50 MB noise
step tally (Scene3DController.applied)       geometry: TREE 220, material: LAWN 78 in 30 s
                                             ground tile replacements 432 in 40 s (1 MB pixels each)
in-place tile reload (probe, 2 tiles)        64 px, 128 px  new colour shown
                                             256 px, 512 px  OLD colour, also after clearing the data first
                                             and after changing the size and back
final A/B, 300 s, food forest                ground tile uploads  1223 -> 619 and 7779 -> 648
                                             growth 122 -> 104 MB and 218 -> 98 MB (about 100 MB of each is the warm-up of the first minute)
```

## Root cause
`seasonal_ground_tint` moves a lawn's fill every fourth day, so a held key (about 30 days a second, a pass every 500 ms) re-coloured every lawn about twice a second. The ground baker re-baked every tile under a lawn, `GroundTiles._replace` made a new Model and a new 512 x 512 texture for each, and each one the engine destroyed kept memory (#532). Nothing in the package's gate re-coloured a lawn.

## Fix and lesson
- `Scene3DController._season_date_for`: the lawns' colour is read at the date they last showed while the date keeps changing (`SEASON_REST_MS` 800 ms, `SEASON_MAX_HOLD_MS` 10 s; a single pick applies at once); the meadow's uniform follows the same date (`controller.season_date`).
- The twin of `BufferGeometry.reload` for a tile's `QQuick3DTextureData` is not available: a texture of 256 x 256 pixels or more shows its old picture after `setTextureData` + `update()`. The `ground_tiles` docstring has the numbers.
- Lessons: (1) a gate that holds one kind of change fixed (no lawn, no date-dependent ground) proves nothing about the others - run the owner's gesture on a bundled example before calling a memory issue closed. (2) Bisect by stubbing the host calls one at a time AND all together: the all-stubbed arm separated the engine from Python in one run, and stubbing one call at a time hid a cause that was spread over two. (3) A temporary instrument must not allocate what it measures: a debug dict that kept `repr()`s of the pixel arrays grew the process by 13 GB and produced a spectacular, wrong A/B. (4) Private bytes swing by +-100 MB and every arm has a 100 MB warm-up: compare second-half slopes and event counts (tile uploads), not one growth figure.
