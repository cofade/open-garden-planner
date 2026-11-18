# Category popup overflow (#951)

- **Symptom** — Searching the Vegetables & Herbs category put exact matches below the screen. Reopening the category retained hidden trait selections.
- **Initially plausible** — The plant search or the species data discarded matches.
- **Evidence** — `[GALLERY951] show` logged frame `(193, 309, 581, 1215)` in an 800 × 800 work area. Matches remained visible in their original sparse grid cells.
- **Cause and fix** — An unbounded fixed-width popup laid out every original grid row and kept its previous size. Bound it to the anchor screen, put results in a scroll area, re-pack matches and reset the browse state on open.
- **Pinned by** — `tests/integration/test_category_toolbar.py` covers open, scroll, filter, empty, reopen and activate.
