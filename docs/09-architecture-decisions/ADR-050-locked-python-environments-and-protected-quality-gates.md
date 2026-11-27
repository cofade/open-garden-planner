---
id: ADR-050
title: "Locked Python environments and protected quality gates"
status: "Accepted, 2026-10-08; released v1.29.6, 2026-10-09. Master protection was activated and independently verified before the normal approved merge. Issues #404, #401, #402 and #399; implemented in [PR #422](https://github.com/cofade/open-garden-planner/pull/422)."
legacy_anchor: adr-050-locked-python-environments-and-protected-quality-gates
---

# ADR-050: Locked Python environments and protected quality gates

**Status:** Accepted, 2026-10-08; released v1.29.6, 2026-10-09. Master protection was activated
and independently verified before the normal approved merge. Issues #404, #401, #402 and #399;
implemented in [PR #422](https://github.com/cofade/open-garden-planner/pull/422).

**Context.** The release resolved floating Python dependencies, strict mypy was configured but
absent from CI, and coverage was documented without measurement. Master allowed administrator
merges with no required checks. A solo maintainer needs the existing single finalize-us
invocation to finish release and mechanical version sync without direct pushes to master.

**Decision: dependency selection.** Use uv's universal native lock as the installation source,
plus a checked PEP 751 pylock.toml export for interoperability. The exact uv bootstrap version
is declared once in pyproject.toml. Seed the first lock from the verified v1.29.5 release,
not from an undeclared developer environment. Preserve runtime/dev selections; add the build
group with released PyInstaller/hooks and explicit setuptools/wheel backend pins. Provenance
and backend additions are recorded in quality/dependency-provenance.json. Platform markers
select Windows/Linux dependencies. One composite action checks freshness, installs locked
runtime/dev/build dependencies, installs the editable app without dependency resolution or
build isolation, and checks consistency. CI never repairs tracked lock/export files. The
promise covers Python dependency selection, excluding byte-identical installers, OS images
and NSIS. uv is MIT/Apache-2.0; existing dependency-license requirements remain in force.
See [uv lock and sync](https://docs.astral.sh/uv/concepts/projects/sync/) and
[uv export](https://docs.astral.sh/uv/reference/cli/#uv-export).

**Decision: type allowances.** Keep strict mypy over all production source, including the
spike. Remove ignores measured unused on both platforms; retain the platform-dependent one.
Schema-1 quality/mypy-baseline.json names target Python 3.11, locked mypy, and separate Linux
and Windows per-file counts. A new file has allowance zero; improvements elsewhere cannot
pay for an increase. Lower counts pass and a fix should lower its allowance. Counts do not
identify individual diagnostics. Tool upgrades/rebaselining require a separate reviewed
change. scripts/check_mypy_baseline.py reuses the audit parser and validates summary counts,
paths, metadata and process exit. Default checks never write the baseline; --write-baseline
is explicit. Exit 0 means compliance, 1 regression, 2 invalid tooling/configuration/report.

**Decision: coverage rollout.** The Linux/Python 3.11 full suite measures lines and branches.
Schema-1 quality/coverage-floors.json records a floor for every nonempty top-level production
package, including (root) and spike_q3d. First line floors round the fresh percentage down
to an integer; comparisons use exact covered/total counts. Every new package needs an entry.
The shared audit aggregation defines non-UI as all packages except ui. Branch coverage is
reported without a branch floor. The Coverage job fails below a floor and uploads artifacts
on failure, but initially is not a GitHub-required check. Finalization still investigates any
failed CI. Missing/invalid XML, unresolved layouts and expected packages fail visibly.

**Decision: protected finalization.** Keep PRs, zero approving reviews/no code-owner review,
strict required checks and administrator enforcement; retain blocked force pushes/deletion.
The eight concrete check names are in quality/master-protection.json; deployment docs describe
the seven job keys and matrix expansion. Unrelated live settings must be preserved on apply.
The read-only protection verifier and current-head check verifier refuse missing/failed results.
After owner-approved manual testing, finalize-us refreshes the branch when needed, waits for
actual results, marks ready, and normally squash-merges with --match-head-commit. The release
must belong to that merge SHA and its workflow must succeed. No bypass is available. Chore-only
finalization skips waiting for a release.

**Version sync.** The same authorization covers a separately reviewed mechanical chore PR.
The preparation CLI is dry-run-first, validates the tag before writes, stages both version
edits and the editable lock-record version, then validates/refreshes the native lock offline,
regenerates the export, and compares full third-party
records. Apply rolls back source files on write failure. Resume an existing branch/PR or
already synchronized versions; never duplicate work. Review, draft PR, CI, ready and normal
merge still apply; no second manual-test confirmation is needed. The chore title prevents a
second release. Wiki push and cleanup finish the same invocation.

**Alternatives.** Rejected a platform-specific pip freeze (developer-only packages and weak
marker portability), global mypy counts (one file can hide another's regression), an initial
universal 80% floor (unsupported by the measured tree), administrator bypasses, and direct
version-sync pushes. Requiring a human approving review would block this solo workflow.

**Validation.** Subprocess fixtures exercise real commands and exit codes without remote
merges. Baselines use clean locked Windows/Linux environments. Workflow inventory, context
parity and skill citations prevent documentation drift. Full pytest, lint/security/secrets,
translation, lock/export, type/coverage and frozen startup/subsystem gates apply. Protection
refusal/acceptance passed on isolated PR #420 using the proposed policy; its temporary
branches/policy were removed. Master protection was activated and independently read back
before PR #422 merged normally. Release v1.29.6 succeeded for that exact merge SHA, including
locked installation, frozen subsystem verification and build-provenance attestation. Release resumption resolves the tag
and successful workflow by merge SHA without needing a pre-merge tag after a restart.

**ADR-050 implementation evidence: cold offline cache.** A locked install does not cache
registry metadata for every platform/Python split. A bare version change triggered an offline
universal re-resolve and failed on Linux; even uv lock --check did not prime that metadata.
The sync helper seeds only the editable-project version before native offline validation,
with full third-party-record comparison. Its subprocess test passes with an empty UV_CACHE_DIR
on Linux and Windows, preserving the supported-Python range and dependency selections.

## ADR-050 addendum: per-file coverage enforcement (#406, 12 October 2026)

**Decision.** Extend the shared audit coverage parser and the existing coverage-floor CLI.
Add optional schema-1 `file_line_floors`, keyed by normalized paths relative to the production
package. Enforce `core/tools/constraint_tool.py: 60` using exact covered-line counts; rounded
percentages are presentation only. Preserve all package floors, CLI arguments and exit-code
contracts. Report branch coverage separately with no invented branch floor. Missing required
files, invalid floor paths/values, malformed or contradictory XML and unresolved layouts fail.
Explicit Linux/Python 3.11 package rebaselining retains reviewed file floors.

**Evidence.** Tests cover below/exact-floor boundaries, a rounded 60.0% that is below the exact
floor, missing-file and malformed-report cases, Linux/Windows layouts and package compatibility.
Registered tool workflows and graph/geometry/history assertions provide behavioral evidence;
the coverage threshold is a regression floor, not a substitute for those assertions.

## ADR-050 addendum: toolchain pins, the locked audit and the update path (A2 #454, 13 October 2026)

**Status**: Accepted (2026-10-13). No lock replacement; no release-right change.

**Decision.** Close the parts of the build that the Python lock cannot see, and give the
dependency-update path a documented home:

1. **Interpreter patch pinned** — `python-version: "3.11.9"` in `release.yml` and in the
   shared `setup-locked-env` composite, so every CI job and the release use one patch. The
   `requires-python = ">=3.11"` install contract is deliberately unchanged. **3.11.9 is
   the newest 3.11 with a Windows x64 build** in `actions/python-versions`' manifest
   (verified 2026-10-13): 3.11 entered security-only mode after it, and the later patches
   ship Linux artifacts only, so pinning one of those broke the Windows matrix jobs in CI
   run 38463742285 with "The version '3.11.17' with architecture 'x64' was not found for
   Windows 2025". The drift test only requires a full `3.11.x`; changing the patch on
   purpose means re-checking both platform builds.
2. **Installer toolchain pinned** — `choco install nsis --version=3.13.0` (the newest
   version in Chocolatey's community feed on 2026-10-13), replacing a floating install.
3. **External actions pinned to commit SHAs** with a readable `# vX.Y.Z` comment, in
   `ci.yml`, `release.yml` and the composite action. `scripts/check_action_pins.py` is the
   drift guard (wired into the `agent-context` CI job) and covers the composite action too.
4. **Build evidence** — `scripts/emit_build_evidence.py` records the actual Python, `uv`,
   PyInstaller, `pyinstaller-hooks-contrib`, `setuptools`, `wheel` and NSIS versions plus
   the commit and run id into `dist/build-evidence.json`, uploaded as a workflow artifact.
   `--require-complete` makes the release fail rather than publish a build whose toolchain
   it cannot state.
5. **Lock-based vulnerability scan** — the `dependencies` CI job exports the committed lock
   (`uv export --locked --all-extras --group build`) and runs `pip-audit` over it **on both
   matrix operating systems**, because pip-audit evaluates requirement markers against the
   running interpreter: the export is universal, so a Linux-only scan never sees the
   Windows-only runtime dependency (`pywin32`, required by `mcp`). One exception was recorded
   by ID: the `setuptools` advisory `PYSEC-2026-3447` (`GHSA-h35f-9h28-mq5c`), which only
   affects publishing macOS source distributions — a thing this project does not do. **It
   ended on 2026-10-24** (#571, #572): the build group moved to setuptools 84.1.0 for
   GHSA-xmj3-9gf7-h52w, which contains the 83.0.0 fix, and a waiver that matches nothing in
   the lock would hide a widened advisory unreviewed. No advisory is waived now; a new waiver
   is named in `tests/unit/test_dependency_governance.py::WAIVERS` and justified in §11.2.
6. **Update automation: verified unavailable, manual fallback adopted.** Dependabot's uv
   ecosystem image ships uv **0.12.19** (`uv/Dockerfile` in dependabot-core, read
   2026-10-13) while this project pins `uv ==0.12.23`; a `required-version` mismatch makes
   the updater exit before doing any work, so no automated dependency PR can exist today.
   `.github/workflows/dependency-review.yml` therefore runs monthly, computes what
   `uv lock --upgrade` would change with `--dry-run` (measured: `uv.lock`'s hash is
   unchanged; the workflow fails if the dry run ever writes it), and opens or refreshes
   **one** issue with the report. It never pushes, commits, opens a PR or merges. The
   runbook lives in `docs/07-deployment-view` §7.4, and the Qt four-pack / `mcp` v1 caps
   are pinned by `tests/unit/test_dependency_governance.py`. Automation is to be revisited
   when hosted uv reaches the pin.
7. **One dependency source of truth.** `requirements.txt` / `requirements-dev.txt` were
   deleted (AUD-052); they listed 2 of 15 runtime dependencies and still carried
   `PyQt6>=6.6.0`, the exact spec behind #277. Installation is
   `UV_PROJECT_ENVIRONMENT=venv uv sync --locked --all-extras --group build` from
   `pyproject.toml` + `uv.lock` + `pylock.toml`, and a test keeps the files deleted and
   unreferenced.

**Evidence.** The pins were resolved from primary sources on 2026-10-13 (setup-python's
versions manifest; Chocolatey's feed; dependabot-core's `uv/Dockerfile`). The scan was run
against the shipped command's export: 93 requirement lines, one vulnerable package
(setuptools, including code collected into the executable); the affected macOS sdist
publishing operation is unused, and no unwaived finding remains. `tests/unit/test_build_toolchain_pins.py`,
`tests/unit/test_action_pins.py`, `tests/unit/test_dependency_governance.py` and
`tests/unit/test_no_stale_requirement_manifests.py` pin the behaviour, and the frozen
build proves the pins produce a working artifact.

**Consequences.** Bumping the interpreter patch or NSIS version is now a deliberate edit
with a test-visible value, not an implicit drift. A new vulnerability fails the audit
unless it is explicitly recorded with a justification. The parse of `pylock.toml` remains
read-only; no file format, runtime behaviour or `.ogp` version changes.

## ADR-050 addendum: Release version attribution from triggering commit (#543, 20 October 2026)

**Status:** Accepted (2026-10-20).

**Context.** PR #484 (Phase 17 L1) was merged with the `minor` label on 2026-10-19 as commit `bf4fd77a`. The Release workflow published `v1.30.14`, a patch release, instead of `v1.31.0`. The root cause was `.github/workflows/release.yml` using `gh pr list --state merged --base master --limit 1` to pick the PR whose labels to inspect. `gh pr list` sorts by PR creation date (`createdAt` descending), not merge time or triggering commit SHA. PR #484 was created weeks earlier and was shadowed by PR #521 (created and merged earlier on the same day without a label). Additionally, `echo "$LABELS" | grep -q "minor"` used substring matching rather than exact line matching.

**Decision.**
1. Delegate version determination in `.github/workflows/release.yml` directly to `python scripts/resolve_release_pr.py --write-github-output`, maintaining one canonical implementation.
2. In `scripts/resolve_release_pr.py`, resolve the merged PR from the triggering commit SHA:
   - Primary: `gh api "repos/${REPO}/commits/${COMMIT_SHA}/pulls"` selecting the newest master-merged PR.
   - Fallback: parse `(#N)` suffix or merge syntax from the commit subject (`git log -1 --format=%s`).
   - Query `gh pr view` for labels when resolved via subject fallback.
3. Match labels with exact set equality (`"major"`, `"minor"`), eliminating substring matches.
4. Pin the behavior in `tests/unit/test_release_version.py` covering multi-PR timestamp ordering, squash subject regex, exact label matching, subprocess error recovery, CLI output formats, and workflow static guards.

## ADR-050 addendum — PEP 639 license metadata in the project manifest (#574, 2026-10-25)

**Context.** The senior review of #571/#575 found setuptools 82.0.0/84.1.0 warning
about two `[project]` forms: `license = {text = "GPL-3.0-or-later"}` and the
`License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)`
classifier. The warning carries a 2027-02-18 due date, after which setuptools may
refuse to build. The build group pins `setuptools==84.1.0`, but
`[build-system] requires = ["setuptools>=61.0", "wheel"]` floats for an isolated
build, so a plain `pip install .` or `uv build` picks the newest setuptools.

**Decision.** `pyproject.toml` uses the PEP 639 form: `license = "GPL-3.0-or-later"`,
`license-files = ["LICENSE"]`, no license classifier, and the build floor is
`setuptools>=77` (the first release with PEP 639 support). The wheel's metadata is
`Metadata-Version: 2.4` with `License-Expression: GPL-3.0-or-later` and
`License-File: LICENSE`; the LICENSE is inside `dist-info/licenses/`. No runtime
dependency, SBOM schema, notices format or `.ogp` field changes.

**Evidence.** A no-isolation `pip wheel` with 84.1.0 and an isolated `uv build` both
complete with no `SetuptoolsDeprecationWarning`; the wheel metadata above was read
from the built artifact. `tests/unit/test_packaging_metadata.py` pins the SPDX
string, the license file, the absence of a `License ::` classifier and the floor.
PF-CI-14 records the rule.

## ADR-050 addendum — the frozen version module is generated, not tracked (#596 manual pass, 2026-10-25)

**Context.** A direct `python -m PyInstaller installer/ogp.spec` build showed **1.2.0** in
Help → About while `pyproject.toml` and `src/open_garden_planner/__init__.py` said
1.31.1. `get_current_version()` reads `open_garden_planner._version` when frozen; the
release path (`installer/build_installer.py`) writes that module, but a direct PyInstaller
build bundled a tracked file last written on 2026-03-01. The 2026-10 audit had already
recorded the three disagreeing version sources as AUD-072.

**Decision.** `_version.py` is a build artifact. It is removed from the repository and
gitignored; `build_installer.py` writes it before PyInstaller (the release version may lead
`pyproject.toml` until the sync) and deletes it in a `finally` afterwards, and a direct
PyInstaller build has no such file, so the frozen app falls back to `__version__`. The module is read with
`importlib.import_module` so type checkers do not require a tracked file; that removes the
static import edge PyInstaller followed, so `installer/ogp.spec` lists
`open_garden_planner._version` as a hidden import when the file exists. Either build path
reports a version, and neither can report a tracked stale one.
**Evidence.** `tests/unit/test_packaging_metadata.py` pins the write/remove pair, the
fallback (`sys.frozen` + no module), the release direction (a module whose `__version__`
differs from the package's wins) and the spec's conditional hidden import; `--selftest`
checks the frozen version against `OGP_EXPECTED_VERSION`. The rebuilt direct exe's About
reports 1.31.1. The release path is unchanged: `build_installer.py` still writes the module before
PyInstaller, and the frozen bundle includes it. No runtime dependency, `.ogp` field or
product behaviour changes.

## ADR-050 addendum — Tag conflict recovery and release classification (A11: AUD-038, AUD-086, AUD-090, 2026-10-28)

**Context.** The 2026-10 repository audit identified three related release-path debt items in A11:
1. **AUD-038**: `release.yml` used a naive `git rev-parse "$TAG"` existence check, silently skipping releases on both legitimate idempotent workflow retries and catastrophic tag conflicts (where a calculated tag already points to a *different* commit SHA).
2. **AUD-086**: Post-release version-sync PRs (`prepare_version_sync.py`) update `pyproject.toml`, `__init__.py`, and lockfiles under reviewed PR finalization. The maintenance cost and architectural tradeoff of dynamic git-tag version derivation versus explicit checked-in manifests required formal evaluation.
3. **AUD-090**: `release.yml` skipped workflow execution strictly based on commit message prefixes (`chore:` / `chore(...)`), creating a vulnerability where a commit labeled as a chore could conceal unreleased executable code in `src/` or `installer/`.

**Decision.**
1. **Tag disposition resolution (AUD-038)**: `scripts/resolve_release_pr.py` now implements `check_tag_disposition(tag, commit_sha)` returning `'new'`, `'idempotent_retry'`, or `'conflict'`. If a tag already exists and points to a different commit, `.github/workflows/release.yml` halts with `::error::` (exit 1) rather than silently skipping. Idempotent workflow retries on the same commit SHA gracefully skip without error.
2. **Version derivation evaluation (AUD-086)**: Dynamic derivation at build time (e.g. `setuptools_scm`) was evaluated against OGP's single-binary offline desktop distribution model. OGP requires deterministic offline packaging, strict dependency hashing (`uv.lock`), zero-network local developer builds, and frozen binary verification. The maintenance cost of a 30-second automated version-sync chore PR per release is far lower than the risk of build-time version drift, tag-parsing desyncs across multi-platform worktrees, or untracked dirty builds. CI remains the authoritative source of releases; `prepare_version_sync.py` keeps manifests synchronized under human review.
3. **Release classification gate (AUD-090)**: Added `scripts/check_release_classification.py` to differentiate executable modifications (`src/`, `installer/`, package dependencies) from documentation and mechanical version-sync chores. The classification enforces that no chore commit may alter executable paths, preventing unreleased code from being masked by chore prefixes.

**Evidence.**
- Pinned by `tests/unit/test_release_version.py` (59 tests passing) and `tests/unit/test_release_classification.py` (20 tests passing).
- Static workflow tests verify `release.yml` attributes PRs and checks tag disposition.
