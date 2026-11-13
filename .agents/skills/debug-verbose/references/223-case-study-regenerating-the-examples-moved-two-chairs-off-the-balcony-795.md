## Case study: regenerating the examples moved two chairs off the balcony — the generator nobody ran (#795, fixed 2026-11-10)

**Symptom**: the task was to change two path widths in one example and regenerate "by the documented procedure". After `scripts/generate_examples.py`, `git status` showed all four examples modified, not one: plans, sidecars and every thumbnail.

**Theories entertained (wrong)**:
- *"Line endings."* The generator writes LF into a CRLF checkout, so every file is "modified". `git diff --ignore-cr-at-eol --stat` removed nine plan files from the list and left real content differences in the rest.
- *"My change did it."* The data change was not written yet. The run was the unchanged generator on the unchanged tree.
- *"Float noise or thumbnail fonts."* True for the PNGs (another slice had changed the rendering). Not for the plans: the differences were whole coordinates and whole words.

**What the evidence showed** (no print needed here; the instrument was the diff of a regeneration that should have been a no-op):

```
balcony.ogp            "x": 120.0, "y": 215.0   →   "x": -257.0, "y": 120.0      ← CHAIR, no rotation_angle before or after
balcony.ogp            "x": 292.0, "y": 215.0   →   "x": 215.0, "y": -334.0
es/family-garden.ogp   "name": "Compostador"    →   "name": "Compost"
*.meta.json            - "attribution_ru": …                                      ← three sidecars lose a key
```

**Root cause**: three independent drifts between the generator and the files it once wrote, none visible to any test, because no test ran the generator.

1. The generator turned the chairs with `chair.setRotation(±90)`. A bare `setRotation` turns about the item's origin and is not the `rotation_angle` the serializer saves, so the chairs had always shipped unrotated. Since #661 the serializer writes a shape where its centre lies in the parent frame; for an item turned about (0, 0) that is somewhere else entirely.
2. `text(en, de, es)` filled one table per English string. The showcase registered "Compost" → "Compostador" at import, the raised bed registered "Compost" → "Compost" when it was authored, and the later one won. The shipped showcase had been generated alone (`generate_examples.py family-garden`); generating all four changed it.
3. `attribution_ru` had been added to three sidecars by hand and never to the generator.

**Fix**: the chairs are turned with `geometry_apply.apply_rotation` (they stand where they were drawn and now face the table); `text()` asserts that a second registration of a string is the same translation; the attribution table carries Russian. `example_content(slug)` became the one function the shipped plans and sidecars come from, `--check` compares the files with it, and `tests/integration/test_example_generation.py` does the same in the suite.

**Lesson**: before changing generated data, run the generator on the unchanged tree and read the diff. A no-op that is not a no-op is the bug list, and it is far cheaper to read before your own change is mixed into it. And a generator whose output is committed needs a test that runs it; a file that "is generated" but is only ever compared with itself drifts silently.
