## 18. QSettings global-static poison — "passes alone, fails together, CI green"

Source: §11.4 ("`QSettings.setDefaultFormat()` / `setPath()` are process-global…").

- Symptom: 6 settings-persistence tests fail only in the full local run, pass in
  isolation, and CI stays green. Uniform tell: every failing getter returned exactly the
  coded *default* — the setter write never persisted.
- Root cause: a fixture in `tests/unit/test_ui_state.py` called
  `QSettings.setDefaultFormat(IniFormat)` + `setPath(...)` — **static, process-wide,
  never auto-reverted** — pointing at a `tmp_path` pytest later deleted; every
  `QSettings` constructed after it wrote to a dead path.
- Fix: monkeypatch the `QSettings` *symbol* in `ui_state` (auto-reverts) — never the
  globals. Backstops in `tests/conftest.py`: session fixture restores
  `defaultFormat()` at teardown; function-scoped autouse fixture clears the test store +
  nulls the settings singleton.
- Lesson: "passes alone, fails together, actual value = default" is almost always shared
  global/singleton state; green CI does not prove the local full suite is clean
  (different collection order dodges the poison).
- Status: closed (with tripwires; a `setPath`-only leak is NOT covered).

---

