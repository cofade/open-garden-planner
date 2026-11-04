## When NOT to use this skill

- **Triaging a live bug right now** → `ogp-debugging-playbook` (and the project skill
  `debug-verbose` for instrumentation method). Come back here only to check whether the
  bug rhymes with a settled saga.
- **Looking up an invariant as a forward-looking contract** (what you must preserve when
  writing new code) → `ogp-architecture-contract`. This skill records how those
  invariants were *learned*; the contract skill states them normatively.
- **Release/merge mechanics** → `ogp-change-control` / `finalize-us`. Saga #8 here only
  explains *why* those procedures look paranoid.
- **Qt/CAD API reference** (Y-flip math, snap pipeline, item patterns) →
  `ogp-qt-cad-reference` and `docs/08-crosscutting-concepts/` §8.9.
- Adding a brand-new subsystem with no history — nothing here binds you, though sagas
  6, 7, 11, and 16 describe traps that generalise to any new Qt code.

---

