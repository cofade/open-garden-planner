## 5. Before you design anything — checklist

Work through this in order; it takes five minutes and has repeatedly saved
multi-round review cycles.

1. **Read the ADR index** (`docs/09-architecture-decisions/README.md`). Is your
   problem already decided (possibly with your exact idea listed under
   *Alternatives considered — rejected*)? Respect the rejection or write a new
   ADR superseding it — don't relitigate silently.
2. **Does it touch an invariant above?** Serialization → row 9; anything that
   moves/resizes/rotates → row 2; any mutation → rows 3–5; beds/containers/
   plants-in-things → rows 7–8; tasks → row 6; agent surface → rows 12–13;
   file/network/user-JSON input → row 14. Name the rows in your plan.
3. **Pick the seam, don't add a call site.** New bed action → §8.14 playbook.
   New sizing rule → `plant_sizing.py`. New task surface →
   `make_calendar_task_id` + `species_key`. New dialog → `app/paths.py`
   defaults. New snap kind → a `SnapProvider` (ADR-020/023). New "thing plants
   live in" → an `ObjectType` + predicate membership, not a new item class.
4. **New persisted data?** Default to an additive key with old-app degrade
   semantics written down. A `FILE_VERSION` bump needs an ADR-grade
   justification (it locks out old installs) — see ADR-032 for the graceful
   alternative pattern.
5. **New ADR needed?** CLAUDE.md triggers: new dependency, choosing between
   approaches, changing a pattern, or a non-obvious constraint. If your design
   doc contains the word "instead", it probably needs an ADR.
6. **Can the logic be Qt-free?** If yes, it must be (invariant 10): pure module
   in `core/`/`services/`, thin Qt adapter, unit tests without `qtbot`.
7. **Plan the tests that enforce, not just cover:** parametrised-over-shapes for
   anything multi-shape, drift guards for duplicated constants, a pinning test
   for any invariant you extend (that's how every row above stays true).
8. **Then** switch to `ogp-change-control` for branch/PR/review process, and
   check `ogp-failure-archaeology` if you're touching a subsystem with a saga
   (rotation/resize, tasks, sidebar, snap/constraints, agent API).

