# Ringelblume missing from the Flowers & Perennials gallery (#950)

- **Symptom** — The German gallery returned no result for Ringelblume.
- **Initially plausible** — A stale translation or a clipped search result hid the plant.
- **Evidence** — `[GALLERY950] search Ringelblume []` while `[GALLERY950] catalog Calendula officinalis` confirmed that the bundled lookup could resolve Pot Marigold.
- **Cause and fix** — The category has an explicit list of placeable plants. Add Pot Marigold under its own catalog name and reuse its existing translations and artwork resolver.
- **Pinned by** — `tests/integration/test_category_toolbar.py` opens the German category, searches and clicks each of the three flowers, and resolves the emitted species against the bundled catalog.
