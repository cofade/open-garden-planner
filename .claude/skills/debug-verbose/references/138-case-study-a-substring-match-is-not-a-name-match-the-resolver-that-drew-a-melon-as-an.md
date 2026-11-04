## Case study: a substring match is not a name match - the resolver that drew a melon as an eggplant (#446)

**Symptom.** A plant assigned "Melon" was drawn with the eggplant's sprite; a
scientific name ("Petroselinum crispum") was drawn as a rose; a plant whose name
merely CONTAINED another plant's name ("peach_tree") was drawn as a pea; a
string of blanks was drawn as a rose.

**Evidence.** The rule asked whether a key was CONTAINED in the name, or the name
in the key. "melon" is inside "solanum melongena"; "rose" is inside
"petroselinum crispum"; the empty string is inside every key. The golden of
1,562 answers made it visible: the melon, the rose and the pea were all in it.

**Wrong theory.** "The lookup needs a better alias table" - and "match the whole
name only". Both were MEASURED before anything was written. Whole-name-only
changes 266 of the 1,562 answers over 110 distinct names, and most of those
changes are REGRESSIONS: "Quercus robur", "Broad Bean", "Sweet Corn" and "Winter
Squash" have no exact key and fall back to a generic category sprite. An alias
table fixes three cases exactly and adds a hand-maintained table that can rot.

**Cause/fix.** A name is matched as a whole name or alias, in three steps: the
whole name; else a key whose every word is a word of the name ("Broad Bean" ->
bean); else a key that holds every word of the name ("Solanum" -> tomato). A name
no sprite knows takes the plant's category sprite. Measured after: 74 answers
change over 37 names, and of the bundled species' 118 names exactly ONE changes -
the melon. The rule is ONE rule, shared by the 2D renderer and the 3D plant
builder, so both views change together.

**Lesson.** Before changing a rule that decides what a user SEES, measure the
rule you are about to replace against the whole corpus, and count the regressions
as carefully as the fixes. The issue's own expected behaviour was measured and
rejected - and the three cases that survive the shipped fix ("Lemon Balm", "Bean
(Bush)", "Sweet Potato") are pinned in the test, so nobody discovers them later as
a surprise.

