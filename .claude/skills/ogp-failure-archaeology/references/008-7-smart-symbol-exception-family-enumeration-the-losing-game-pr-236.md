## 7. Smart-symbol exception-family enumeration — the losing game (PR #236)

Source: §11.4 (first entry), CLAUDE.md C4 row. Found over **three** senior-review rounds.

- Contract: a bad user-dropped JSON in `<app-data>/smart_symbols/` must never crash the app.
- The losing game: first enforced with `except (OSError, JSONDecodeError, ValueError)`.
  Broke three times, each a different family escaping the enumeration:
  (1) dry-run `generate()` raised `ArithmeticError`/`TypeError` (divide-by-zero,
  `9**9**9`, `round(x, float)`) — none subclass `ValueError`;
  (2) `"+".join(["1"]*5000)` raised `RecursionError` **during `ast.parse`**;
  (3) a non-dict `parameters` entry raised `AttributeError` in `from_dict`'s
  *structural* phase — before the dry-run, bypassing `generate()`'s wrapper entirely.
  Each "fix" added the family that bit it, then re-declared victory.
- Final rule (structural, not enumerative): the **user-file load loop catches
  `Exception`** (log-and-skip) so any `from_dict` failure on untrusted input is non-fatal
  *by construction*; the **bundled** load loop stays narrow so first-party packaging bugs
  crash loud. `BaseException` still propagates. Defense in depth: `generate()` wraps its
  body → `SmartSymbolError`; the evaluator caps AST node count (`_MAX_NODES`).
- If you see the broad catch in `smart_symbol_library.py` and want to "tighten" it: this
  entry is why you must not.
- Status: closed. Pinned by `tests/unit/test_smart_symbol_library.py`
  (arithmetic/recursion/structural/non-object poison skipped; malformed *bundled* file
  still crashes loud).

---

