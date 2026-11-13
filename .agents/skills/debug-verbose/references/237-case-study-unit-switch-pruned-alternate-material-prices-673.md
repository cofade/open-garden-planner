## Case study: saving in imperial discarded metric material prices (#673, fixed 2026-11-12)

**Symptom**: native soil/mulch prices were correctly separated, but saving in the
other unit system deleted the previous system's prices.

**Wrong theory**: distinct item IDs alone were sufficient to protect the prices.
They prevented applying the wrong price but interacted with save-time pruning.

**Evidence**: a failing test followed the actual `prune_stale_prices` path. A tagged
print with caller stack showed the active display IDs being mistaken for existence:

```text
[UNIT-PRICES] current=['mulch:ft2', 'soil_fill:ft3']
    saved=['mulch:ft2', 'mulch:m2', 'soil_fill:ft3', 'soil_fill:m3']
    stale=['mulch:m2', 'soil_fill:m3']
```

**Root cause**: pruning used the current display's IDs as the complete material
universe. Alternate units hide a price record but do not remove its material.

**Fix**: when either identity for soil or mulch is present, retain both identities.
If the material disappears, prune both. Instrumentation was removed. Pinned by
`tests/unit/test_unit_reports.py::test_saving_in_either_system_keeps_both_native_price_records`.

**Lesson**: when identity varies by presentation, audit cleanup as well as lookup.
