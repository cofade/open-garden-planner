## 8. Phase 6 — Validation & promotion (per slice)

Run for EVERY US in the campaign; route everything through
`ogp-change-control` (it owns the canonical sequence; this is the
campaign-specific overlay).

| Step | Command (Windows; Linux swap `venv/bin/python`) | Expected |
|---|---|---|
| Tests | `venv/Scripts/python.exe -m pytest tests/ -v` | green, incl. the new pinned-number tests |
| Lint | `venv/Scripts/python.exe -m ruff check src/` | clean |
| Security | `venv/Scripts/python.exe -m bandit -r src/ --severity-level high` | clean |
| i18n | `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py && PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py && venv/Scripts/python.exe -m pytest "tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished" -v` | pass — remember: f-strings bypass `tr()` (the AGENTS.md trap); sun/shade has LOTS of user-visible strings (menu, hints, band labels, command descriptions) |
| Exe | build, then **both** checks per `ogp-change-control` §2.8 — `--selftest` is **the check that caught #277**, this campaign's own Qt3D micro-mismatch, which startup and the 8-second smoke both survived because Qt3D imports lazily | exit code 124, then 0 |
| Integration test | mandatory per §8.10 — each phase's gate table above names the file | in `tests/integration/` |
| Review | `senior-reviewer` agent on the branch diff, fresh worktree; fix P0/P1; re-run for a clean pass | clean pass BEFORE the PR |
| PR | draft PR (`gh pr create --draft`), stays draft until the owner's manual test | per `ogp-change-control` — never merge on your own say-so |

**The exe gate is two commands, and both are mandatory** — the 8-second smoke *and*
`--selftest`, which is what sees a subsystem that died silently (#291 hid from the smoke
for six releases; #277 shipped a crash behind a lazy import). The command literals live in
**`ogp-change-control` §2.8** — the single place they are written down — with the
invocation traps in `ogp-build-and-run`. Do not copy them here.

**Manual-test checklist (owner-facing, per slice — the owner's judgment is
sovereign, but hand them numbers, not vibes):** e.g. for Phase 3: "Set
location Berlin (52.52, 13.405). Set sim time 21 Jun 12:00 UTC (14:00 CEST).
Place a 1 m-tall post. EXPECTED: shadow ~59 cm long pointing north-northeast
(up-right on screen). Set 21 Dec 12:00 UTC. EXPECTED: ~4.3 m shadow, nearly
due north." — the numbers come from the Appendix, so a failed manual test
localizes instantly to render-vs-math.

**Documentation duties (per `ogp-change-control` / AGENTS.md matrix):**
- **ADR-037**: solar engine + shadow architecture (Qt-free core, canvas-frame
  math, overlay non-serialization, aggregation strategy). **ADR-038**: 3D
  engine GO/NO-GO. (ADRs live in `docs/09-architecture-decisions/README.md`;
  036 is the last used as of 2026-07-19 / v1.24.3.)
- **FR entries** in `docs/functional-requirements.md` (suggest FR-SUN-01…):
  height property, shadow overlay, time control, heatmap, empty states, and
  the explicit exclusions (flat-ground assumption; refraction ignored;
  terrain slopes out of scope v2.0).
- **§8 concept section** in `docs/08-crosscutting-concepts/README.md`
  (next free §8.x — check; §8.19 was Agent API): the three-frame coordinate
  discipline for solar math, with the worked example.
- **Glossary** (`docs/12-glossary/` — a directory): azimuth, declination,
  elevation angle, equation of time, hour angle, solar noon, full sun /
  partial shade / full shade bands.
- **Roadmap + wiki**: mark the USes, sync `../open-garden-planner.wiki/Roadmap.md`.
- **§11.1**: close/update the Qt3D open-question row with the ADR-038 outcome.

---

