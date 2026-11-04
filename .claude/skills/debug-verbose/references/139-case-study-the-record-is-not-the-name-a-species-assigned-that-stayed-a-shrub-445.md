## Case study: the record is not the name - a species assigned that stayed a shrub (#445)

**Symptom.** Assigning "Oak" from the plant database gave the plant the oak's
calendar data and the oak's size, and left it drawn as a generic tree - in the
plan and in the 3D view alike.

**Evidence.** The assignment wrote `metadata["plant_species"]` (the RECORD). The
sprite resolver reads the item's own species STRING (`item.plant_species`), and
the 3D plant builder resolves from the same string. The item's string was
untouched, so the plant kept the sprite it was drawn with.

**Wrong theory.** "The resolver should look at the record" - and "the resolver
should look at the DATA's common name". The second is a trap: a gallery
"Pumpkin" carries the DATA of "Winter Squash" while its own name is "pumpkin",
so resolving from the data's name draws a different plant than the plan shows.

**Cause/fix.** The assignment writes the item's string as well - the name of the
species ASSIGNED (the record's common name, or its scientific name when the
common name names no sprite) - inside the same `ApplySpeciesCommand`, so the
record, the spacing override, the footprint radius and the string revert
together in one undo step. The string is the plant's own name; the record's data
is the species' data, and the two may still differ.

**Lesson.** When a model has two places for a fact, find out which one the
READER reads before you write to either. The record was written and the data was
right, and the plant still looked wrong - because the name the pixels come from
was a third thing, and nobody asked who reads it.

