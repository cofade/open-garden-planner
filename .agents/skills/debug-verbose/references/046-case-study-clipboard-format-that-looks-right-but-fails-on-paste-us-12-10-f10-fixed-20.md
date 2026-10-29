## Case study: clipboard format that LOOKS right but fails on paste (US-12.10/F10, fixed 2026-05-03)

**Symptom**: AmendmentPlanDialog → "Copy to clipboard" → paste into LibreOffice / Excel → everything dumped into a single column.

**Root cause**: `_build_clipboard_text` produced human-readable bullet lines (`- Dolomite lime: 10.4 kg (Bed A, Bed B)`). Visually fine on a notepad, but the spreadsheet has no separator to split on.

**Lesson**: "Copy to clipboard" buttons targeting *spreadsheets* must produce **tab-separated** rows with a header row. Always test the receiving application, not just the rendered string. Add a regression test that asserts exact column count via `line.count("\t") == n`.

---

