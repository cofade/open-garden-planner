## 20. The ghost-field family (US-12.10d, fixed 2026-05-03)

Source: two debug-verbose case studies.

- Incident A: soil-mismatch warnings never fired despite 14 passing integration tests.
  Evidence: a diff of `dataclasses.fields(PlantSpeciesData)` vs `to_dict()` keys — three
  new fields (`n_demand`/`p_demand`/`k_demand`) missing from **both** serialization
  sites, silently dropped on the canvas→metadata→canvas path. The integration tests
  constructed instances directly and never round-tripped. **Construct-and-test is not
  serialize-and-test.**
- Incident B: even after fixing serialization, plants still had `None` everywhere — the
  panel had **no UI rows** for the new fields, so nothing could ever set them. A "ghost
  field" with no UI is worse than no field: the data layer looks complete while the
  feature is unusable.
- Fixes pinned by `tests/unit/test_plant_data_serialization.py` (iterates
  `dataclasses.fields()`, asserts presence + full round-trip equality).
- Status: closed; the *pattern* recurs — when adding a dataclass field, update
  `to_dict`/`from_dict` AND audit the forms that read/write the model.

---

