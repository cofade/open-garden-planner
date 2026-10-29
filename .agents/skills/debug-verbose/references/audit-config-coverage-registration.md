## Case study: extracted settings had no package coverage floor (#392)

- **Symptom:** all hosted test/render producers passed, but aggregate Coverage failed.
- **Wrong theories:** no test, tracer or rounding defect was inferred; the gate's
  diagnostic named the missing registration directly.
- **Key evidence:** `{"package": "config", "reason": "Missing package or floor entry"}`;
  the same report measured 449 covered statements out of 471 (95.3%). A new local
  source-package inventory test failed with the extra package `config` before the fix.
- **Root cause:** extracting settings and paths into a top-level package did not
  register that package in `quality/coverage-floors.json`.
- **Fix:** add the 95% floor, retaining every existing floor, and compare the source
  package inventory with the registered floor names in the regular test suite.
- **Lesson:** a new package changes coverage ownership even when code merely moves.
  Check registration locally; use actual unrounded hosted counts to enforce coverage.
