# Pitfalls: CI, release and supply chain

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-CI-01

- **Rule:** Attribute frozen code from collected files, not only declared dependencies
- **Pinned by:** `tests/unit/test_frozen_inventory.py`; `tests/integration/test_distribution_inventory_pipeline.py::test_frozen_hook_dependencies_are_in_the_inventory`
- **Source:** #454, #490
- **Status:** standing
- **Legacy:** README L112

- **Attribute frozen code from collected files, not only declared dependencies**
  (PR #490 / #454): the 47-component SBOM check passed while the executable's PYZ
  contained unreported setuptools, packaging, pytest/mypy dependencies and nested
  vendored libraries. `Requires-Dist` and a hardcoded hook exception did not describe
  what PyInstaller collected. `installer/frozen_inventory.py` now maps actual Analysis
  source paths through wheel RECORDs, with nested vendored precedence, and bundles
  those owners' metadata/licenses plus a module/file ownership manifest. The checker
  compares it with the executable PYZ and locks containing-wheel versions for vendored
  copies; declared license files must exist and their text must reach the notices.
  Pinned by `tests/unit/test_frozen_inventory.py` and
  `tests/integration/test_distribution_inventory_pipeline.py::test_frozen_hook_dependencies_are_in_the_inventory`
  (observed failing on the original artifact). Synthetic fixtures constructed from the
  expected closure prove orchestration, not complete frozen attribution.

### PF-CI-02


- **Rule:** A stale `*.egg-info` on `sys.path` silently shrinks anything derived from installed metadata (#454, 2026-10-13).
- **Pinned by:** none — pending Phase 3 review
- **Source:** #454, #490
- **Status:** pointer → [debug-verbose: Case study: frozen code absent from a passing SBOM (#454, 2026-10-14)](../../../.claude/skills/debug-verbose/SKILL.md#case-study-frozen-code-absent-from-a-passing-sbom-454-2026-10-14)
- **Legacy:** README L126

Held in [debug-verbose: Case study: frozen code absent from a passing SBOM (#454, 2026-10-14)](../../../.claude/skills/debug-verbose/SKILL.md#case-study-frozen-code-absent-from-a-passing-sbom-454-2026-10-14). The entry keeps the rule and its pin; the account is in the link.

### PF-CI-03

- **Rule:** A source checkout's `.env` is not automatically present in a packaged build, and a credential setting must not become a project secret.
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #342
- **Status:** standing
- **Legacy:** README L203

- **A source checkout's `.env` is not automatically present in a packaged build, and a credential setting must not become a project secret.** The satellite picker originally read only `OGP_GOOGLE_MAPS_KEY`, so Python launches that loaded the repository `.env` worked while a frozen executable showed a disabled menu. The supported fallback remains the process environment or `.env` beside the executable. Issue #342 adds a Preferences value at `api_keys/google_maps_key`, with Preferences-first resolution and blank-field fallback to the environment. The key is intentionally absent from `.ogp` serialization, PyInstaller data, logs, and user-facing error details; never "fix" a frozen-build credential problem by bundling or auto-copying the secret. Regression coverage pins both resolution precedence and the immediate menu refresh after saving/clearing Preferences.

### PF-CI-04

- **Rule:** A windowed PyInstaller build launched with no console has `sys.stdout is None`, and uvicorn's default log config dereferences it — the Agent API was dead in every released exe (issue #291, closed).
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #277, #291, #334
- **Status:** standing
- **Legacy:** README L232

**A windowed PyInstaller build launched with no console has `sys.stdout is None`, and uvicorn's default log config dereferences it — the Agent API was dead in every released exe (issue #291, closed).** Symptom: the Preferences "Enable Agent API" box is ticked, nothing listens on the port, no error dialog appears, and "Connect AI Assistant…" reports *"the Agent API is currently disabled"* about an already-enabled feature. Works perfectly from source. **Root cause**: `console=False` (what we ship) allocates no console, so when the exe is launched detached — a double-click, or `Start-Process` — `sys.stdout`/`sys.stderr` are `None` (**not** unconditionally; see the correction below); `uvicorn.Config.__init__` calls `configure_logging()`, and uvicorn's default formatter does `self.use_colors = sys.stdout.isatty()` (`uvicorn/logging.py`), so `dictConfig` raises `ValueError: Unable to configure formatter 'default'` and the server never starts. **Fix**: pass `log_config=None` to `uvicorn.Config` — we want none of uvicorn's logging anyway (`log_level` and `access_log=False` are already set, the latter deliberately so the `?token=` query param never reaches a log). **Why it hid for six releases, three compounding reasons**: (1) the failure is caught by `_start_agent_api`'s `except Exception` → `logger.exception`, but **no logging handler is configured anywhere in this app**, and with `sys.stderr is None` even `logging.lastResort` is mute — the traceback is destroyed; (2) the only user-visible trace is an 8-second status-bar message; (3) every diagnostic instinct reaches for a `console=True` build, **which has a real stdout and therefore cannot reproduce it** — the observation changes the result. **Lessons**: a frozen-exe check that only asserts "the app survives 8 seconds" cannot see a silently-dead subsystem, which is why `--selftest` now starts the server and asserts it binds — the same reasoning that produced the Qt3D `--selftest` after #277. **Corrected 2026-08-19 (PR #334):** this entry previously said the windowed exe has `sys.stdout is None` *unconditionally*, so `--selftest` reproduced the shipping condition "for free". Measured: it does not. `console=False` means no console is *allocated*, but a redirected handle is still inherited — launched from a shell pipe the frozen exe wrote **~300 bytes to stdout**, so `sys.stdout` was a live pipe and a regression of the `log_config=None` fix would pass. The shipping condition needs **no inherited stdout handle**: launch it detached (`Start-Process -Wait -PassThru`, which is what `release.yml` does and what the gate lists now prescribe). The observation-changes-the-result trap in this very entry had a second storey; and when a UI message explains an absent thing, check whether the absence has more than one cause — `agent_api_running_url()` returning `None` meant both "switched off" and "failed to start", and the copy named only the first.


Hard-won lessons from implementation. Read these before modifying the related subsystems.

### PF-CI-05

- **Rule:** Release workflow race condition with chore commits
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** none recorded
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l270-release-workflow-race-condition-with-chore-commits)
- **Legacy:** README L270

### PF-CI-06

- **Rule:** PyInstaller-frozen exe fails to load Qt3D DLLs on a `PyQt6-3D-Qt6` ↔ `PyQt6-Qt6` micro-version mismatch
- **Pinned by:** none — retired with its subject
- **Source:** #274, #277
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l317-pyinstaller-frozen-exe-fails-to-load-qt3d-dlls-on-a-pyqt6-3d-qt6--pyqt6-qt6-micro-version-mismatch)
- **Legacy:** README L317

### PF-CI-07

- **Rule:** Never default a file dialog into the install directory; never let the uninstaller wipe it blind
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #199
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l354-never-default-a-file-dialog-into-the-install-directory-never-let-the-uninstaller-wipe-it-blind)
- **Legacy:** README L354

### PF-CI-08

- **Rule:** A non-critical CI job that fails permanently is indistinguishable from one that does nothing — and it trains everyone to scroll past the Actions tab
- **Pinned by:** none — retired with its subject
- **Source:** #161, #293
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l400-a-non-critical-ci-job-that-fails-permanently-is-indistinguishable-from-one-that-does-nothing--and-it-trains-everyone-to-scroll-past-the-actions-tab)
- **Legacy:** README L400

### PF-CI-09

- **Rule:** CI/release hardening: locked metadata also contains the application version
- **Pinned by:** `tests/integration/test_wiki_publication.py`
- **Source:** #399, #402, #404, #417, #420, #422
- **Status:** standing
- **Legacy:** README L2886

A version-only edit to `pyproject.toml` makes `uv.lock` stale. The measured probe failed
`uv lock --check --offline`, then `uv lock --offline` changed only the editable project's
version. `scripts/prepare_version_sync.py` stages and validates this refresh before applying
any source writes, compares full third-party records, and regenerates the export. The
version-sync chore must therefore include the lock alongside both source declarations.
Pinned by `test_version_sync_cli_is_offline_transactional_and_idempotent`.

Fresh baselines must use declared locked dependencies: the developer venv included undeclared
Qt stubs and older type/coverage tools. Linux and Windows also disagreed about one ignore: 229
were unused on both platforms, while one Windows-unused ignore remained needed on Linux.
Only common unused directives were removed; allowances are measured per platform. Pinned by
`test_baseline_keeps_platforms_independent_and_rejects_tool_drift`.


**Offline refresh is not the same as a universal re-resolve.** A cold locked Linux install
cached its selected wheels but lacked other-platform resolver metadata. Changing only the
project version triggered a re-resolve and failed offline; a freshness check did not fix it.
Version sync now stages the editable lock-record version before native offline validation,
then verifies all third-party records unchanged. The real subprocess test uses an empty cache
on both platforms. Underlying tool stderr must be reported; a process exit alone hid the cause.

**CI hardening review findings (#404/#402/#399).** A fresh Windows checkout changed the export's
1,857 LF endings to CRLF; a working-copy byte check missed it. Generated locks now have explicit
LF attributes. Coverage records must have unique normalized file/line identities and supplied
summary counts must agree with aggregates, or duplicated XML statements can inflate a floor.
An injected second-file write failure verifies full version-sync rollback. Release recovery
resolves a published tag and successful workflow from the feature merge SHA; tag transition
is required only when observing a new merge, so restart after publication can finish normally.
The isolated protection PR #420 rejected its failing head and merged its corrected green head
without a bypass under the proposed admin-enforced policy; temporary branches/policy were
removed. Master enforcement was activated and verified before PR #422 merged normally. Evidence: quality/protection-validation.json.

**Hosted update tooling can lag a reproducible CI pin (2026-10-09).** The first security
update attempt failed with `tool_version_not_supported`: detected uv `==0.12.23`, supported
uv `0.12.18`. Evidence: [Dependabot run 37951191628](https://github.com/cofade/open-garden-planner/actions/runs/37951191628).
The project CI and release used the agreed pinned tool successfully. Preserve the pin and
perform the setuptools advisory update in a separately reviewed manual dependency PR;
automatic security-update support is unresolved, not a successful remediation. An exact
bootstrap pin must be checked against hosted update tooling as well as installation tooling.

**Unicode CLI output needs an explicit stream encoding** (issue #417): UTF-8 wiki files did not prevent redirected Windows stdout from using cp1252. The comparison command emitted byte 0x96 for an en dash and failed to encode a check mark. `scripts/sync_wiki.py` now sets stdout and stderr to UTF-8 before printing. The subprocess comparison regression in `tests/integration/test_wiki_publication.py` captures real Unicode diffs without a UTF-8 environment override.
