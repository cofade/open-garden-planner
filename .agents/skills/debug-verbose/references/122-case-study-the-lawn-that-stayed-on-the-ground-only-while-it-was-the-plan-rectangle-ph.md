## Case study: the lawn that stayed on the ground — only while it was the plan rectangle (Phase 17 L1.5, fixed 2026-10-12)

**Symptom**: a full ground tile (more than 256 records) had dropped the lawn under its pavers:
138,240 px of a 5.12 m square were bare meadow. The fix of the first review round — "an opaque
cover ends the walk; below the cut a tile keeps what covers it WHOLE" — passed its pins: zero
bare pixels under 255, 256 and 2,000 pavers. The re-check moved the lawn 10 cm inside the plan's
edge: 149,604 px bare again (158,721 at half a centimetre), mean 24.4 of 255 against the canvas,
and more pavers did not help.

**Wrong theories**:

1. *"Zero bare pixels at 2,000 pavers shows the lawn is safe."* The test lawn was
   `surface("lawn", (550, 350), (550, 350))` on a 1100 x 700 plan — the plan rectangle, the one
   lawn that covers EVERY tile whole.
2. *"The rule was implemented as ruled, so the outcome follows."* It was implemented to the
   letter. The letter named a mechanism ("covers the whole tile"), not what it was for.

**Key evidence**: one number changed in the fixture — the lawn's half size, 550 -> 540.

**Root cause**: a rule worded as a mechanism, pinned by a fixture that sits exactly on the
mechanism's best case. A lawn whose edge runs through a tile covers 99 % of it and counted as
nothing.

**Fix**: the rule by its OUTCOME — when a bound bites, a tile loses its smallest records, never
a large one (ranked by how much of the tile each record's paint box overlaps; ties to the
topmost; an opaque cover still ends the walk). Pinned for four lawns (the plan rectangle, 10 cm
inside, half a centimetre inside, 30 % of the tile), three counts of pavers and a real scene
against the canvas.

**Lesson**: **when a fix is specified as a mechanism, restate it as the outcome it is for and
test THAT — with a fixture the mechanism was not written for** (off its boundary by a little,
and by a lot). A fixture that coincides with a special case of the code — the plan rectangle, a
tile-aligned item, a centred upright one — proves the special case.

