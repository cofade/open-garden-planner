---
id: ADR-041
title: "One QSettings Chokepoint — `app/settings.create_qsettings()`"
status: "Accepted (2026-07-30) | **Context**: issue #285 (tech debt), follow-up to #283"
legacy_anchor: adr-041-one-qsettings-chokepoint--appsettingscreate_qsettings
---

# ADR-041: One QSettings Chokepoint — `app/settings.create_qsettings()`

**Status**: Accepted (2026-07-30) | **Context**: issue #285 (tech debt), follow-up to #283

**Problem.** Two modules persisted user state and each built its own backend: `AppSettings` (preferences) and `UiStateStore` (window geometry, splitter, toolbar layout), both calling `QSettings("cofade", "Open Garden Planner")` directly. The test suite isolated only the first, by replacing `AppSettings.__init__` — so `UiStateStore` walked straight past it. Every full-app test therefore **read** whatever geometry and toolbar layout the developer's own app had last saved, and **wrote it back at teardown** (pytest-qt closes registered widgets → `closeEvent` → `_save_ui_state`). Measured during #283: **120 writes** into the real `cofade / Open Garden Planner` registry key from one test file, and a toolbar-visibility assertion that failed *with the fix applied* because a stale real-world layout was the actual variable — an hour lost to "the fix doesn't work". #283 shipped a second autouse fixture patching `ui_state.QSettings`; that left **two** isolation mechanisms guarding **one** store, and a third hand-rolled store tomorrow would get the same free pass.

**Decision — one factory, and the redirection lives inside its body.**

- `app/settings.py` owns `ORGANIZATION_NAME`, `APPLICATION_NAME` and `create_qsettings()`. It is the only place that names `QSettings`; `AppSettings` and `UiStateStore` both take their backend from it. Same shape as the `app/paths.py` file-dialog chokepoint (ADR-027): one funnel beats N disciplined call sites. **Accepted consequence:** because the gate matches the *name*, no module outside the chokepoint can type a store it receives either — a bare `def _apply(store: QSettings)` is unwritable anywhere else, including under `if TYPE_CHECKING`. That is deliberate (an annotation is one keystroke from a construction, and nothing needs one today), but it will look like a broken gate to whoever first wants it; pass the *wrapper* instead, or move the code into `settings.py`. The gate reads the AST, so a *string* annotation (`s: "QSettings"`) or a `getattr(QtCore, "QSettings")` slips through — neither is worth chasing, since both are deliberate evasions rather than the accident this guards.
- **The non-obvious part, and the whole reason this is an ADR:** `create_qsettings()` reads the two module-level names *on every call* rather than capturing them at import (no default argument, no module-level tuple, no `functools.partial`). Redirection therefore happens **inside the function body**, which is what makes it inescapable *for stores built after the rebinding* — rebinding the two names covers every consumer regardless of how it imported the factory (bullet 3 says *where* that rebinding lives; it is not a fixture). Had the seam been the *binding* instead (patch `settings.create_qsettings`), a future consumer writing `from ...settings import create_qsettings` at module level would silently escape it — a re-run of the exact #283 bug, one import statement away. `tests/unit/test_settings_chokepoint.py::test_rebinding_the_names_redirects_new_stores` pins this property so it cannot be optimised away.
- **The seam's precise limit, and where the redirection therefore has to happen.** A `QSettings` binds its `(organization, application)` when it is constructed; rebinding a module global cannot retarget an object that already exists (pinned by `test_rebinding_does_not_retarget_an_existing_store`, after a senior review caught an earlier draft of this ADR claiming otherwise — do not restore that claim, and do not reason from it). Everything therefore turns on *when* the rebinding runs relative to construction, so it runs at **`tests/conftest.py` import time**, at module scope, not inside a fixture. pytest imports the root conftest before it collects any test module, hence before any `open_garden_planner` module a test imports — so even a store built while a module is being imported is constructed after the redirection and lands in the test key (measured: a module-level `AppSettings()` in a test module reports `organizationName() == "cofade_test"`). No fixture, however early-scoped, can offer that: fixtures run after collection. A third review round proposed this after breaking the fixture-based alternative's compensating gate, and it is strictly stronger — the invariant now holds by construction rather than by everyone remembering a rule. `isolate_qsettings` keeps only what needs a fixture: nulling the lazy singleton, clearing the key at session end, the `defaultFormat()` tripwire, and an assertion that the import-time rebinding actually took.
- **The rule is enforced, not documented.** `tests/unit/test_settings_chokepoint.py` walks the **AST** of every module under `src/` *and* `tests/` and fails if anything but the chokepoint so much as *names* `QSettings` — import (in any alias or parenthesised spelling), annotation, or construction, including the import-free `from PyQt6 import QtCore` … `QtCore.QSettings(…)` route. `tests/` is in scope because the #283 damage was *observed* from the test side and a stray store in a test leaks just as hard; exactly three test modules are exempt (the conftest tripwire, the temp-INI factory, the method spy), and a test fails if any exemption stops being *needed* — the other direction, "nobody quietly adds a fourth", is a review duty, since a length assertion against a literal in the same file would be tautological and the file's whole value is being honest about what it enforces. The same file forbids the process-global `QSettings.setDefaultFormat()` / `setPath()` statics everywhere but the one sanctioned restore in `conftest` — whose continued existence is itself asserted, so that exemption cannot outlive its reason (§11.4: a leaked `setPath` to a deleted `tmp_path` once broke six tests two-thirds of the way through a session). `scripts/` is scanned too — the §11.4 corollary that cost a developer their own Welcome-dialog setting was a throwaway *probe script* writing to the production store outside pytest, where no fixture isolates anything. A third rule forbids building a store at **import time** (`TestNoStoreIsBuiltAtImportTime`): belt-and-braces since the conftest redirection above, but still a smell — such a store cannot be redirected by anything at all. That detector reads *names*, so it resolves import aliases and subclasses transitively but is defeated by one level of indirection (`def _b(): return AppSettings()` then `_P = _b()`); its docstring says so, and that is affordable exactly because it is no longer load-bearing. Every detector carries a **positive control** — fed the exact escape it exists to catch — because a detector that stops matching anything reads as a green gate forever. Both of those disciplines were bought one review at a time, and the sequence is the lesson: a construction-only regex missed an aliased import; adding an import regex still missed `from PyQt6.QtCore import (\n    QSettings as _Q,\n)`, which names the class on a line carrying no `import` keyword (found by review round 1 in one experiment); the first cut of the import-time rule matched only the literal name `create_qsettings`, so a module-level `AppSettings()` — what a developer would actually write, since nobody caches the low-level factory — sailed straight through the gate named after that very invariant (round 2, one experiment); and widening it to the wrapper names still missed `AppSettings as _Prefs` … `_Prefs()`, because `_callee()` sees only the call-site spelling (round 3, one experiment). Falsify a gate against the API people use, not the primitive it is written in terms of — and note that the third round's real contribution was not a better detector but a mechanism that made the detector optional.
- `UiStateStore` calls it **module-qualified** (`app_settings.create_qsettings()`), so `settings.create_qsettings` is additionally patchable as a single name — used by `tests/unit/test_ui_state.py` to point one unit test at a temp INI file, where the *medium* is the thing under test. This second seam inherits the very weakness bullet 2 rejects for the primary one (a `from … import create_qsettings` in `ui_state.py` would escape it, and nothing gates that import form). It is accepted only because the blast radius is one unit-test file and that file's own `test_store_is_built_by_create_qsettings` fails loudly if the patch stops landing.

**Rejected alternatives.**

| Option | Why not |
|--------|---------|
| Constructor injection (`UiStateStore(settings: AppSettings)` or a raw store) | The honest trade, not a knock-out: injection would make the dependency **visible at the call site** instead of implicit in module state, which is the better property. It loses on reach and cost — `UiStateStore` is constructed inside `GardenPlannerApp.__init__`, so isolating it by injection means threading a store through app construction (and through every future consumer's), while the chosen seam reaches code whose construction the test does not control. Injection also still needs a seam somewhere to decide *what* gets injected. Chosen: the cheapest seam that reaches instances built by code the test doesn't call directly — at the price of two module-level names in `src/` being a test-isolation contract documented only in comments. |
| A production `set_qsettings_factory()` test hook | Ships test-only API in `src/` and invites runtime rewiring of the store. The name constants give the same reach with no extra surface. |
| Keep both fixtures, add a lint rule only | The measured failure was *reads*, not just writes; a lint rule cannot make the existing bypass safe, and two mechanisms for one store is the debt #285 was filed against. |
| Isolate by pointing `QSettings.setPath()` at a temp dir in conftest | Process-global static Qt never reverts — the documented §11.4 incident this ADR's gate now forbids outright. |

**Consequences.** `tests/conftest.py` has one isolation fixture instead of two, and it yields the displaced production `(organization, application)` pair so tests can assert that pair is never touched without hardcoding it. `tests/integration/test_settings_isolation.py` builds the whole app and spies on Python-level `QSettings.value`/`setValue`: pre-fix it records 3 reads + 3 writes against the real store (verified by reverting the chokepoint), post-fix zero, with anti-vacuity assertions that the spy and the app both did something. Independently confirmed by hashing the real registry key's 29 values around a 47-test full-app file: byte-identical. Two clean-ups fell out of having one ownership story: `main.py` now takes the `QApplication` organization/application names from `settings` instead of repeating the literals, and `AppSettings`' duplicate, never-called `window_geometry`/`window_state` pair (keys `window/geometry`, `window/state`) is deleted — window geometry belongs to `UiStateStore` alone. **Note what the first clean-up widened:** those two constants were the settings-store identity; they are now also the `QApplication` names, which is what `QStandardPaths.AppDataLocation` derives from — i.e. where `main._write_crash_log` puts `crash.log`. The literals are unchanged so nothing moves today, but a future fixture that rebinds them in a scope where something calls `setOrganizationName()` would move the user-data directory with them. One more thing "one chokepoint" does *not* mean: one object. `AppSettings` and `UiStateStore` hold independent `QSettings` instances on the same key, with independent caches and no explicit `sync()` discipline between them — unchanged from before #285, and fine because their key groups are disjoint, but the phrase is about construction, not coherence. Adding a new persisted setting needs no new store — add a key to `AppSettings`; adding a genuinely separate store means calling `create_qsettings()` *at runtime*, and the gates will say so if you forget either part.

## Addendum — Linux settings protection (A1, #453, 2026-10-13)

The owner chose fail-closed startup over temporary settings. The existing factory
secures its actual Linux user file to mode 0600 before returning a backend. New
application directories use mode 0700; existing shared ancestors are unchanged.
The descriptor must identify a regular file owned by the current user. A legitimate
symlink is supported through its validated target. Existing preferences and plaintext
credentials retain their keys; Windows registry and macOS behavior are unchanged.
No keyring dependency or encryption is introduced.

The baseline was reproduced in isolated Python 3.11 / Qt 6.11: native QSettings
creates mode 0644 under umask 022. Tests run fresh subprocesses under umasks 022
and 000, exercise an existing 0644 store, repeated atomic sync, safe symlinks,
special files and simulated chmod failure. The factory does not alter global
umask, QSettings format or path statics. A protection failure produces a sanitized,
translated startup error using the system locale and exits before the main window.

## ADR-041 addendum — the chokepoint refuses an unsafe production context (#587, 2026-10-25)

**Context.** A review probe built `GardenPlannerApp` in a scratchpad to measure the
Plan & Sun strip. It gave the QApplication a throwaway name and called
`QSettings.setDefaultFormat(IniFormat)`, both of which look like isolation; neither
redirects `create_qsettings()`, which passes the module's own names to
`QSettings(org, app)` and that constructor always uses the native format. The write
reached the owner's registry and switched off the startup Welcome dialog; three more
probes that day had the same defect. Written rules and the existing
`tests/integration/test_script_isolation.py` gate cover only `scripts/`, not a probe in
a temp directory.

**Decision.** The chokepoint itself refuses the production names in a process that is
not the product or a deliberately isolated script. `SettingsIsolationError` is raised
when `(ORGANIZATION_NAME, APPLICATION_NAME)` is the production pair and any of these
holds: the Qt platform is `offscreen`/`minimal` (the product never runs there), or an
exact agent-session variable is set (`CODEX_HOME`, `CODEX_SANDBOX`, `CLAUDECODE`,
`CLAUDE_CODE*`, `OPENCODE*` — exact names, so an API key such as `CODEX_API_KEY` does
not trigger it). The product marks itself with `OGP_PRODUCT_PROCESS=1` in `main()`
(not at module import: a probe that imports `main` for a helper must not inherit it).
`script_isolation.isolate_settings()` rebinds the names to a throwaway pair, which is
the other sanctioned way through. `OGP_ALLOW_PRODUCTION_SETTINGS=1` is the explicit
override for a one-off tool that really must read the real store. A plain desktop
shell with production names is allowed — that is how the app runs. The check keys
on the *production* pair, so a test or script that rebinds the names is unaffected.

**Rejected alternatives.** Logging loudly instead of refusing was the incident's shape
with a different verb: a probe that ignores a warning still writes the registry. Keying
on the QApplication name or on `setDefaultFormat` is what the probe already did and is
not an isolation mechanism. Refusing while the real GUI runs from an agent shell was
avoided by the product marker, so the frozen exe and `python -m open_garden_planner`
still start from a tooling terminal.

**Consequences.** `tests/unit/test_settings_isolation_guard.py` pins the refusal, the
product marker's placement inside `main()`, the explicit override and the exact-name
scan; the suite and `scripts/script_isolation.py` rebind the names rather than set a
marker. PF-TST-29 and §8.8 record the rule. No stored key, `.ogp` field or product behaviour changes.
