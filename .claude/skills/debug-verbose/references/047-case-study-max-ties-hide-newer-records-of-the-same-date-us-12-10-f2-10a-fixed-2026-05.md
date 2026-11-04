## Case study: max() ties hide newer records of the same date (US-12.10/F2.10a, fixed 2026-05-04)

**Symptom**: User saves a Lab-mode soil test on a bed that already has a Kit-mode record dated the same day. Reopens the dialog → defaults to Kit. The History tab seems to show only one record. The .ogp file does contain a record with `mode: "lab"`, but the dialog can't see it.

**Wrong theories**:
- `AddSoilTestCommand` silently dropped the record (verified — it appended).
- `to_dict` wasn't emitting the `mode` field (verified — it did when != "kit").
- `_records_equivalent` dedup'd it out (mode differs → guard passed).
- Q-signal ordering issue inside the dialog rebuild after save.

**Key signal**: side-by-side comparison of the .ogp file (which had the lab record) and the dialog state on reopen (`existing_latest.mode == "kit"`). The lab record was on disk but `latest` returned the kit record.

**Root cause**: `models/soil_test.py:116` `latest` — `SoilTestHistory.latest` was implemented as `max(self.records, key=lambda r: r.date)`. Python's `max()` returns the **first** maximal element when keys tie ("If multiple items are maximal, the function returns the first one encountered"). The Kit record was appended first, so it won every same-day tie. Compounded by `_format_history_row` showing only categorical fields — the user couldn't tell two records existed for that date.

**Fix**: Walk `reversed(self.records)` and return the first match for the max date. Plus add a ` [Lab]` / ` [Labor]` suffix to History-tab rows whose `mode == "lab"` so they're visually distinguishable from Kit rows on the same date.

**Lesson**: `max(iterable, key=...)` is **left-biased** on ties. For a "most recently saved record" that uses date as the key, the *first* save with the max date wins — not the last. Whenever the semantic is "newest among items with equal sort keys", either (a) walk the iterable backwards, (b) use a tuple key including a stable secondary sort (insertion index, uuid, monotonic counter), or (c) use `sorted(...)[-1]`. Bonus heuristic: if a sort/aggregation key has limited resolution (a date, not a datetime), assume ties are common and design the tie-break explicitly.

---

