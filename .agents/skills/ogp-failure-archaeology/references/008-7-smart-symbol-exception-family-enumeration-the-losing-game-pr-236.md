## 7. Smart-symbol exception-family enumeration — the losing game (PR #236)

Source: §11.4 (first entry), FR-31 / §8.18. Found over **three** senior-review rounds.

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
- The loader and its code were removed in #1009. The rule still applies to every new
  untrusted-input seam; if you see a broad catch at one and want to "tighten" it, this
  entry is why you must not.
- Status: closed, code retired. The original pin
  (`tests/unit/test_smart_symbol_library.py`) went with the loader in #1009; the rule's
  current pin is `tests/unit/test_ai_client_onboarding.py::test_corrupted_existing_file_is_replaced_not_fatal`.

---

