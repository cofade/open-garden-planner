## 21. UNKNOWN-enum display corruption (#231/#232)

Source: §11.4 entry.

- Symptom: a tree's lifecycle read "Annual"; touching the form then **rewrote**
  `UNKNOWN` → that wrong concrete value (silent data corruption). Bundled DB masked it
  (full trait data); sparse online-search results exposed it.
- Root cause: combos skipped the `UNKNOWN` member and fell back to
  `setCurrentIndex(0)`; save reads `currentData()` back.
- Sibling defect, same issue: `setSpecialValueText("")` — Qt treats an **empty** special
  string as *disabling* the feature, so the `0` sentinel rendered as "0 cm" instead of
  blank. A **non-empty** `setSpecialValueText(self.tr("—"))` engages it.
- Fix: neutral `("—", UNKNOWN)` entry at index 0 in every enum combo; non-empty dash on
  all 8 spin-boxes; display-only (populate/save round-trip unchanged).
- Status: closed. Pinned by `tests/ui/test_plant_database_panel.py`
  (`TestMissingDimensionsShowDash`, `test_sparse_species_saves_back_as_none`).

---

