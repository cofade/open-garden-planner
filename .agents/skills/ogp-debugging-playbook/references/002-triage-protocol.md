## Triage protocol

1. **Reproduce first.** Get exact steps, exact object types (rectangle bed vs polygon bed vs circle plant — they are four independent classes, see row 18), rotation state, and whether a save/reload or undo/redo is involved. Half the rows below only fire under rotation or across a save/load boundary.
2. **Classify against the tables below.** Match on the symptom column (phrased the way a tester says it). If a row matches, read the cited §11.4 chronicle entry / case study before touching code — it names the contract you must preserve and the regression test that pins it.
3. **If no row matches, or two rows compete: stop theorising and invoke `/debug-verbose`.** That skill's method — `print`-based instrumentation with `[TAG]` prefixes, `traceback.format_stack()` at every "who called me?" site, reproduce manually, read stdout — is the project standard. Do not duplicate its templates here; load the skill.
4. **Fix from evidence.** Prefer the fix pattern the chronicle already established (e.g. route through the existing command/helper) over a new local patch — most §11.4 entries end with a contract ("any new X must also do Y"); violating it is how these bugs recur.
5. **Document.** After the fix: remove all instrumentation prints; add a **Case study** entry to `.agents/skills/debug-verbose/SKILL.md` (symptom, wrong theories, key log line, root cause, lesson) and a §11.4 entry if a new contract emerged. This duty is mandatory per `AGENTS.md`; format guidance in `ogp-docs-and-writing`.

Run commands note (2026-07-03): `AGENTS.md` commands use `venv/Scripts/python.exe` — the dev machine is Windows. On Linux/CI the interpreter is `venv/bin/python` and headless Qt needs `QT_QPA_PLATFORM=offscreen` (already set in `tests/conftest.py` and `.github/workflows/ci.yml`).

---

