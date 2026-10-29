## 10. i18n incidents — hardcoded strings and mojibake

Source: §11.4 (two entries) + CLAUDE.md Translation section.

- **Hardcoded-English class** (the gate's mechanics/blind-spot are owned by
  `ogp-diagnostics-and-tooling` §1.2/1.3 — in one line: the gate only checks
  strings *already extracted into the .ts file*, so plain-string call sites are
  invisible). Concrete historical failures: module-level
  `_SEGMENT_LABELS = {"early_spring": "Early Spring",…}` looked up raw in three
  places despite being registered in `fill_translations.py`; f-strings like
  `f"{a} overlaps {b}"` look like sentences but never reach Qt Linguist.
  Fix pattern: `QT_TR_NOOP` dicts + translate at lookup, or
  `self.tr("…").format(...)`; grow `TestNoHardcodedEnglish`'s suspicious-phrase
  list whenever a string slips through manual testing. Related:
  `ChangePropertyCommand` `{property}` fragments must be manually registered under the
  `"Commands"` context (an unregistered fragment silently degrades to English).
- **PowerShell mojibake**: PowerShell 5.1 `Get-Content -Raw` mis-guesses UTF-8-no-BOM as
  Latin-1; `Set-Content -Encoding UTF8` then double-encodes every umlaut (`ö` → `Ã¶`).
  Trigger was an in-place `Anbauerfolge` → `Anbaufolge` replace in
  `fill_translations.py` + the `.ts` file. Recovery: `git checkout` the files, redo with
  Python. Fast detection: `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — non-zero = regressed.
- **Excel BOM**: bare `utf-8` CSVs mojibake German umlauts in Excel — use `utf-8-sig`.
- Status: closed individually; the hardcoded-string class recurs — treat every new
  user-visible string as suspect.

---

