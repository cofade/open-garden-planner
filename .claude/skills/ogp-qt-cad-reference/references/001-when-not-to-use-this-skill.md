## When NOT to use this skill

- Triaging a live bug → `ogp-debugging-playbook` (and the `/debug-verbose` skill).
- The narrative history of how a fix was found → `ogp-failure-archaeology`.
- Gardening/plant domain rules → `ogp-garden-domain-reference`.
- Which module owns what / layering rules → `ogp-architecture-contract`.
- Build, run, test invocation mechanics → `ogp-build-and-run`, `ogp-validation-and-qa`.
- You are editing pure business logic that never touches `QGraphicsItem`,
  coordinates, rendering, or signals (e.g. `services/task_generator.py`).

