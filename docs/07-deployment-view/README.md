# 7. Deployment View

## 7.1 Distribution Strategy

Open Garden Planner is distributed as:

1. **Windows Installer (primary)**: NSIS-based installer wrapping a PyInstaller bundle
2. **pip install (secondary)**: For Python users who prefer package manager installation
3. **Source (developer)**: Clone repository and run with `python -m open_garden_planner`

## 7.2 Windows Installer (NSIS)

### Build Pipeline

```mermaid
flowchart TD
    Src([Source Code])
    PI["PyInstaller<br/>(--onedir, installer/ogp.spec)<br/>bundles Python 3.11 + locked deps + resources,<br/>windowed mode, app icon"]
    Bundle["dist/OpenGardenPlanner/<br/>~611 MiB (local v1.29.6 measurement)"]
    NSIS["NSIS Installer Script<br/>(installer/ogp_installer.nsi)<br/>wizard, Start Menu + desktop shortcut,<br/>file association, upgrade detection,<br/>EN+DE languages"]
    Out["OpenGardenPlanner-v1.29.6-Setup.exe<br/>~171 MiB download (LZMA solid)"]

    Src --> PI --> Bundle --> NSIS --> Out
```

See the **Installer Features** table below for the full feature list.

### How to Build

The build is orchestrated by `installer/build_installer.py`:

```bash
# Prerequisites
# Install the locked environment including its build group (README development setup)
# Install NSIS from https://nsis.sourceforge.io/ (the release pins choco's 3.13.0)

# Full build (PyInstaller + inventory + NSIS)
python installer/build_installer.py

# PyInstaller only (skip NSIS)
python installer/build_installer.py --skip-nsis

# NSIS only (requires existing PyInstaller output in dist/)
python installer/build_installer.py --skip-pyinstaller
```

Without `--version`, the build takes the version from `pyproject.toml`; CI passes the
release-computed version explicitly. Between the PyInstaller step and the NSIS step the
build writes `dist/THIRD_PARTY_NOTICES.md` and `dist/ogp-sbom.cdx.json` from the bundle's
own metadata and then **checks** them (`--lock pylock.toml`): a distribution whose metadata
is missing, a version that disagrees with the lock, or a distribution with no discoverable
license fails the build instead of shipping an incomplete notice.

### Installer Files

| File | Purpose |
|------|---------|
| `installer/ogp.spec` | PyInstaller spec file (entry point, resources, excludes, icon; bundles the runtime distributions' `.dist-info` metadata for the inventory) |
| `installer/ogp_installer.nsi` | NSIS installer script (wizard, registry, file association) |
| `installer/build_installer.py` | Build orchestration script (PyInstaller → distribution inventory → NSIS) |
| `installer/runtime_closure.py` | The one runtime-closure resolver used by both the spec and the inventory generator |
| `installer/ogp_app.ico` | Application icon (multi-size: 16–256px) |
| `installer/ogp_file.ico` | `.ogp` file type icon |
| `LICENSE` | GPLv3 license text (displayed during install) |
| `dist/THIRD_PARTY_NOTICES.md` | Consolidated third-party notices, generated from the frozen bundle and installed next to `LICENSE` (AUD-051) |
| `dist/ogp-sbom.cdx.json` | CycloneDX 1.5 SBOM of the frozen bundle, published and attested with each release (AUD-055) |

### Installer Features

| Feature | Description |
|---------|-------------|
| **Welcome Page** | Branded welcome with app description |
| **License Display** | GPLv3 license agreement |
| **Install Path** | User-selectable (default: `C:\Program Files (x86)\Open Garden Planner` — NSIS `$PROGRAMFILES` on 64-bit Windows, see §11.4 issue #199) |
| **Components** | Core (required), desktop shortcut (optional), file association (optional) |
| **Start Menu** | Shortcut in Start Menu Programs folder + uninstaller shortcut |
| **Desktop Shortcut** | Optional desktop shortcut (component checkbox) |
| **File Association** | `.ogp` files open with Open Garden Planner |
| **Custom File Icon** | OGP logo icon for `.ogp` files in Explorer |
| **Upgrade Support** | Detects existing installation, offers silent uninstall before upgrade |
| **Uninstaller** | Clean removal via Add/Remove Programs |
| **User-Data Preservation** | Before wiping `$INSTDIR`, the uninstaller copies any `*.ogp` plans found there to `Documents\Open Garden Planner\Recovered Plans` (issue #199) |
| **Installer Size** | v1.29.6 download: 178,834,358 bytes (~171 MiB), measured from release metadata on 2026-10-09. Local frozen folder: ~611 MiB. Allow at least 1 GiB for the application plus temporary/download and user-data storage. These are dated measurements, not fixed limits. |
| **Languages** | English, German |

> **Why user-data preservation matters (issue #199):** The uninstall section runs
> `RMDir /r "$INSTDIR"`, and the upgrade path silently invokes the *old* uninstaller
> before installing the new build — so an in-place update wipes the entire install
> directory. Users who had saved `.ogp` plans inside the install folder lost them. Two
> guards now exist: (1) the app defaults all save/open/export dialogs to
> `Documents\Open Garden Planner` (`app/paths.get_projects_dir()`) so new data never
> lands under `$INSTDIR`; (2) the uninstaller backs up any pre-existing `$INSTDIR\*.ogp`
> to `Documents\Open Garden Planner\Recovered Plans` before the recursive delete.

### File Association

Registry entries created by the installer:

```
HKCR\.ogp                                          → "OpenGardenPlanner.Project"
HKCR\.ogp\Content Type                              → "application/x-ogp"
HKCR\OpenGardenPlanner.Project                      → "Open Garden Planner Project"
HKCR\OpenGardenPlanner.Project\DefaultIcon          → "$INSTDIR\ogp_file.ico,0"
HKCR\OpenGardenPlanner.Project\shell\open\command   → "$INSTDIR\OpenGardenPlanner.exe" "%1"
```

The application accepts a `.ogp` file path as a command-line argument (`main.py` handles `sys.argv`), enabling double-click-to-open.

### Add/Remove Programs

Registry entries under `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Open Garden Planner`:

| Key | Value |
|-----|-------|
| `DisplayName` | Open Garden Planner |
| `DisplayVersion` | 1.0.0 |
| `Publisher` | cofade |
| `URLInfoAbout` | https://github.com/cofade/open-garden-planner |
| `DisplayIcon` | `$INSTDIR\ogp_app.ico` |
| `UninstallString` | `$INSTDIR\Uninstall.exe` |
| `EstimatedSize` | (computed at install time) |

## 7.3 Release Process (GitHub Releases)

### Creating a Release (Automated)

Releases are fully automated via the `release.yml` GitHub Actions workflow:

1. **Create a PR** to `master` with your changes
2. **Add a version label** to the PR: `major`, `minor`, or `patch` (default if no label)
3. **Merge the PR** — the release workflow automatically:
   - Computes the next version from the latest git tag + PR label
   - Records the actual toolchain in `dist/build-evidence.json` (uploaded as a workflow artifact)
   - Builds the Windows installer (PyInstaller + NSIS) on a Windows runner; the build writes `ogp-sbom.cdx.json` and `THIRD_PARTY_NOTICES.md` from the frozen bundle and fails if they cannot be verified
   - Generates SHA256 checksums
   - Creates a GitHub Release with auto-generated notes (a verification
     preamble with the checksum + attestation commands is prepended)
   - Uploads the installer `.exe`, `SHA256SUMS.txt`, `ogp-sbom.cdx.json` and
     `THIRD_PARTY_NOTICES.md` as release assets
   - Tags the release as `vX.Y.Z`
   - Attests build provenance (`actions/attest-build-provenance`,
     Sigstore-backed; see §7.3 Verification and ADR-044) for the installer,
     `SHA256SUMS.txt`, the raw app exe, the SBOM and the notices — run *after*
     the release is published so a Sigstore hiccup never costs a release

### Creating a Release (Manual Fallback)

If CI/CD is unavailable, releases can be built locally:

1. **Build a local verification artifact** for the intended version; never create tags manually. CI remains the sole release/tag authority.
2. **Build the installer**: `python installer/build_installer.py --version 1.0.0`
3. **Generate checksums**:
   ```powershell
   (Get-FileHash dist\OpenGardenPlanner-v1.0.0-Setup.exe -Algorithm SHA256).Hash > dist\SHA256SUMS.txt
   ```
4. **Do not publish manually**: restore CI and use its normal release workflow for tagged artifacts.
5. **Release notes**: Include changelog, system requirements, and verification instructions

Note: build provenance attestation (§7.3 Verification) requires GitHub's OIDC
token and can only be produced by an `actions/attest-build-provenance` step
running inside GitHub Actions — a manually-built release has no attestation
to verify, checksums only.

### Release Assets

Each release should include:

| Asset | Purpose |
|-------|---------|
| `OpenGardenPlanner-v{VERSION}-Setup.exe` | Windows installer |
| `SHA256SUMS.txt` | SHA-256 checksum for download verification |
| `ogp-sbom.cdx.json` | CycloneDX 1.5 SBOM of the bundled Python distributions (AUD-055) |
| `THIRD_PARTY_NOTICES.md` | Consolidated third-party notices (also installed next to `LICENSE`) |
| Build provenance attestation | Not an uploaded asset — stored by GitHub against the installer, `SHA256SUMS.txt`, the raw app exe, the SBOM and the notices; verify with `gh attestation verify` (§7.3 Verification, ADR-044) |

### Verification

Users verify download integrity by comparing checksums:

```powershell
# PowerShell
(Get-FileHash .\OpenGardenPlanner-v1.0.0-Setup.exe -Algorithm SHA256).Hash
# Compare with SHA256SUMS.txt from release page
```

From the next release onward, users can additionally verify build
provenance — a cryptographic proof, independent of the checksum, that a
release artifact was produced by this repo's public `release.yml` run from a
specific public commit (not built or modified anywhere else). This covers
the installer, `SHA256SUMS.txt`, the raw app exe the installer packages
(`OpenGardenPlanner.exe`, the file named in issue #356's Defender report),
and the two inventory files (`ogp-sbom.cdx.json`, `THIRD_PARTY_NOTICES.md`),
each attested independently:

```bash
gh attestation verify OpenGardenPlanner-v1.0.0-Setup.exe -R cofade/open-garden-planner --signer-workflow cofade/open-garden-planner/.github/workflows/release.yml
```

`--signer-workflow` pins verification to this repo's own release workflow
specifically, not merely "any workflow with `attestations: write` in this
repository."

This does not make the installer Authenticode-signed and does not by itself
suppress SmartScreen/Defender (issue #356) or Norton FileRep (issue #358)
warnings — see §11.1/§11.2 and ADR-044.

## 7.4 CI/CD Pipeline (GitHub Actions)

Three workflow files in `.github/workflows/` (`ci.yml`, `release.yml`, and the report-only
`dependency-review.yml` described below):

### CI Workflow (`ci.yml`)

**Trigger**: every branch push and every PR to `master`. Python dependencies come from
`uv.lock` through the shared setup-locked-env action. The PEP 751 export is checked for drift.
Qt workflows use `QT_QPA_PLATFORM=offscreen`; xvfb is not part of this CI recipe.

| Job key | Check name | Platform | Behavior |
|---|---|---|---|
| `agent-context` | Agent context parity | Linux | Root instructions and mirrored agent context; external action pins |
| `lint` | Lint | Linux | Ruff over source, tests and scripts |
| `test` | Test | Linux | Full pytest suite, Qt offscreen |
| `security` | Security | Linux | Bandit HIGH findings, tracked-secret scan and the lock-based dependency audit (AUD-054) |
| `dependencies` | Dependencies (ubuntu-latest/windows-latest) | Matrix | Clean locked installation, freshness and export checks |
| `types` | Types (ubuntu-latest/windows-latest) | Matrix | Strict mypy against per-file platform allowances |
| `coverage` | Coverage | Linux | Full-suite line/branch report and per-package line floors |

The matrix jobs each emit two concrete check names. The reviewed protection payload requires
the existing checks plus both dependency/type matrix results and an up-to-date PR. Coverage
is initially not required by GitHub protection; failed CI still requires investigation before
finalization. Master protection was activated and independently verified during approved v1.29.6 finalization (PR #422).

```mermaid
flowchart LR
    Push[Push or PR] --> Setup[Shared locked Python setup]
    Setup --> Gates[Lint / Test / Security / Dependencies / Types / Coverage]
    Push --> Context[Agent context parity]
    Gates --> Review[Review and owner manual test]
    Context --> Review
    Review --> Merge[Normal protected squash merge]
    Merge --> Release[Windows release build from the same lock]
    Release --> Sync[Automatic reviewed version-sync chore PR]
```

Local frozen-exe build, startup smoke and subsystem self-test remain mandatory before merge.
The release job repeats its subsystem self-test after the installer build. See ADR-050.

### Release Workflow (`release.yml`)

**Trigger**: Push to `master` (i.e., PR merge)

**Version bumping**: Automatic based on PR labels:
- Label `major` → bump major (1.0.0 → 2.0.0)
- Label `minor` → bump minor (1.0.0 → 1.1.0)
- Label `patch` or no label → bump patch (1.0.0 → 1.0.1)

```mermaid
flowchart TD
    Trigger(["push to master / PR merge"])
    subgraph Job["Release job (windows-latest)"]
        R1[Checkout with full history<br/>for git tags]
        R2[Determine next version<br/>latest tag + PR labels]
        R3{Tag<br/>already exists?}
        R4[Set up Python 3.11]
        R5[Install locked deps + build tools]
        R6[Install NSIS via choco]
        R6b[Emit build evidence<br/>python / uv / PyInstaller / NSIS versions]
        R7["Build installer:<br/>python installer/build_installer.py --version X.Y.Z<br/>(also writes the notices + SBOM from the bundle)"]
        R8[Generate SHA256 checksum]
        R8b[Write release notes preamble<br/>checksum + attestation commands]
        R9[Create GitHub Release<br/>notes preamble + auto-generated notes]
        R10a[Upload OpenGardenPlanner-vX.Y.Z-Setup.exe]
        R10b[Upload SHA256SUMS.txt]
        R10c[Upload ogp-sbom.cdx.json + THIRD_PARTY_NOTICES.md]
        R11["Attest build provenance<br/>actions/attest-build-provenance<br/>installer + checksum + raw app exe + SBOM + notices"]
        Skip([Skip<br/>idempotent])

        R1 --> R2 --> R3
        R3 -->|yes| Skip
        R3 -->|no| R4 --> R5 --> R6 --> R6b --> R7 --> R8 --> R8b --> R9
        R9 --> R10a
        R9 --> R10b
        R9 --> R10c
        R9 --> R11
    end

    Trigger --> R1
```

### Toolchain pins and build evidence (AUD-049)

The release is reproducible in the parts the Python lock cannot see: the interpreter
patch (`3.11.17`), the installer toolchain (`choco install nsis --version=3.13.0`) and
every external action (commit SHA + a readable `# vX.Y.Z` comment). Before the build the
workflow writes `dist/build-evidence.json` — the actual Python, `uv`, PyInstaller,
`pyinstaller-hooks-contrib`, `setuptools`, `wheel` and `nsis` versions plus the commit and
run id — and fails (`--require-complete`) if any required version cannot be established.
The file is uploaded as a workflow artifact.

`scripts/check_action_pins.py` is the drift guard: it fails CI if any workflow or the
shared composite action references an action by a mutable tag. To bump a pin, resolve the
tag's commit with `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`, replace the SHA,
update the comment, and run the gate.

### Dependency updates (AUD-050, AUD-054)

`.github/workflows/dependency-review.yml` runs on the 1st of each month. It computes what
`uv lock --upgrade` would change with `--dry-run` (verified: the lock file's hash is
unchanged, and the workflow fails if the dry run ever writes it), and opens or refreshes
one issue with the report — it never pushes, commits, opens a PR or merges. This is the
**documented manual fallback**: automated dependency PRs are not available today because
this project pins `uv ==0.12.23` (`pyproject.toml`) while Dependabot's uv ecosystem image
ships uv 0.12.19 (`uv/Dockerfile` in dependabot-core, verified 2026-10-13), and a
`required-version` mismatch makes the updater exit before doing any work. Revisit
automation when hosted uv reaches the pin.

The runbook for acting on the monthly issue:

1. `git checkout -b chore/dependency-update` and `uv lock --upgrade`.
2. Keep the Qt four-pack (`PyQt6`, `PyQt6-Qt6`, `PyQt6-3D`, `PyQt6-3D-Qt6`) on one micro
   and keep `PyQt6-WebEngine` below 6.11 and `mcp` on v1; `tests/unit/test_dependency_governance.py`
   pins those caps.
3. `python scripts/check_dependency_lock.py` (lock/export agreement) and the full gates,
   including the frozen-exe smoke and `--selftest` — a dependency change is exactly what
   those checks exist for.
4. Open a reviewed PR. No auto-merge.

The `Security` job additionally audits the locked closure with `pip-audit` every run
(`uv export --locked --all-extras --group build`). The only recorded exception is
build-time `setuptools` `PYSEC-2026-3447`; the justification lives in §11.2 and the fix is
reserved for a separately reviewed dependency PR.

### PR Labels for Versioning

| Label | Effect | Example |
|-------|--------|---------|
| `major` | Breaking changes, major new version | 1.0.1 → 2.0.0 |
| `minor` | New features, backward compatible | 1.0.1 → 1.1.0 |
| `patch` | Bug fixes, small improvements (default) | 1.0.1 → 1.0.2 |

## 7.5 System Requirements

| Requirement | Minimum |
|-------------|---------|
| **OS** | Windows 10 (64-bit) |
| **RAM** | 4 GB |
| **Disk** | 200 MB free space |
| **Display** | 1280x720 |
| **GPU** | Any (Qt uses software rendering fallback) |
| **Internet** | Optional (for plant database search) |

## 7.6 Agent API / MCP Bundling (US-D1.1)

The embedded MCP server (`agent_api/`, see §8.19, ADR-033) adds the `mcp` /
`uvicorn` / `starlette` / `pydantic` stack (+ transitive `anyio`,
`sse-starlette`, `pydantic-core`, `pydantic-settings`, `httpx`, `cryptography`).
Freezing this stack into the PyInstaller exe required three fixes in
`installer/ogp.spec`, each found by actually running the **frozen** server (the
US-D1.1 bundling proof) — dev tests don't surface them:

- **Collect dynamic submodules + metadata.** uvicorn/anyio/starlette load
  protocol, loop and lifespan submodules dynamically, and several packages read
  their distribution metadata at import; so the spec does
  `collect_submodules(...)` + `copy_metadata(...)` for the stack.
- **Do NOT walk top-level `mcp`.** `collect_submodules("mcp")` imports
  `mcp.cli`, which calls `sys.exit(1)` when the optional `cli` (`typer`) extra is
  absent, aborting the build. The spec collects the concrete subpackages
  (`mcp.server`, `mcp.shared`, `mcp.types`) instead, wrapped in a
  `_safe_collect_submodules` guard.
- **Do NOT exclude `multiprocessing`.** uvicorn imports it eagerly
  (`uvicorn.supervisors → basereload → _subprocess`) even when run
  single-process; excluding it makes the frozen server raise
  `ModuleNotFoundError: multiprocessing` at start (the GUI still runs, the server
  silently fails). It was removed from the spec `excludes`.
- **UPX.** `pydantic_core*.pyd` is `upx_exclude`d (UPX can corrupt the compiled
  extension).

**Verify after any change to the stack:** build the exe, enable the Agent API
(Preferences), and confirm an MCP client can reach `http://127.0.0.1:8765/mcp`
from the *frozen* app — not just from `pytest`.

### Locked development and release environments

`pyproject.toml` declares dependency constraints, the build group and the exact uv tool pin.
`uv.lock` selects universal/platform package versions; `pylock.toml` is its generated PEP 751
export. The lock preserves v1.29.5 selections recorded in `quality/dependency-provenance.json`;
setuptools and wheel are explicit build-backend additions. uv is MIT/Apache-2.0 dual licensed
and is a development tool, not an application dependency. PyInstaller retains its bundling
exception; hooks-contrib remains build tooling. Python dependencies are locked; runner images,
Python patch versions and NSIS are outside this reproducibility claim.

Use the project-pinned uv bootstrap shown in the README. Install with
`uv sync --locked --python 3.11 --all-extras --group build --no-install-project`, then
`uv pip install --python .venv/Scripts/python.exe --no-deps --no-build-isolation --editable .`
on Windows (`.venv/bin/python` on Linux). The build backend is already in the locked environment.
Run `uv pip check` and `python scripts/check_dependency_lock.py` using that environment.

Dependency refreshes are separately reviewed `chore(deps):` PRs with licence and frozen-build
checks. Regenerate the export with the command in ADR-050; never hand-edit its package records.

### Protected finalization

After owner manual-test approval, `finalize-us` verifies the current head and all required
checks, marks the feature ready and merges normally. It waits for the successful Release run
and tag belonging to that merge SHA, then prepares `chore/sync-vX.Y.Z-pr-N`. The helper
`scripts/prepare_version_sync.py` updates both source versions and refreshes the lock offline
without changing third-party selections. A reviewed draft chore PR is checked and merged under
the same authorization, followed by wiki sync and cleanup; no second confirmation is needed.
The chore squash prefix skips Release. A chore-only finalization never waits for a new tag.

Activation is reviewed separately from code delivery: apply `quality/master-protection.json`
during the approved #399 finalization and verify with `scripts/check_branch_protection.py`.
It removes the current review requirement, enforces checks for administrators and retains
blocked force pushes/deletion. Test refusal and acceptance on a temporary protected validation
base; never attempt a deliberately broken merge into master.

## 7.7 Wiki and community documentation publication

The six existing wiki pages now have reviewed sources in `docs/wiki/` (ADR-051, issue #417).
`scripts/sync_wiki.py --check` validates sources offline in the existing Lint CI job.
CI neither accesses the wiki checkout nor publishes content.

The tool renders named pages into an external review directory with `--output DIR`.
`--check-published --wiki-dir DIR` compares an existing checkout without edits.
The canonical roadmap supplies three fixed inclusions. Other wiki pages remain concise summaries.
See [the maintenance guide](../wiki/README.md) for source ownership, exit codes, and publication steps.

Publish after owner approval and protected merge using the separate wiki repository.
Read and reconcile direct wiki edits, preserve unrelated pages, and push without force.
Record source and wiki commit SHAs. An unavailable checkout leaves publication pending.
Do not close #417 on the source PR merge alone.

Repository community files own contributor, conduct, security, and accessibility guidance.
GitHub's private vulnerability reporting setting must be enabled before SECURITY.md goes live.
Abuse reports to GitHub Support are separate from vulnerability reports to maintainers.
The community profile and PR-template recognition require post-merge verification.

## In-app installation verification (A1, #453)

The application requires the matching release's `SHA256SUMS.txt` before launching
the installer. Missing/invalid metadata, unpermitted redirects, byte-count mismatch,
checksum mismatch or cancellation prevent launch. Manual download remains available
from the release page. This adds download-integrity verification; installers remain
unsigned, and build-provenance attestation remains independently verifiable as before.
Linux settings files from earlier releases migrate to owner-only permissions on startup;
an unprotectable store causes an actionable startup error instead of insecure persistence.

The A1 frozen self-test also exercises strict plan persistence, all four supported
image codecs and verified-installer hashing in an isolated temporary directory.
On the 2026-10-13 local build, PyInstaller collected ICU 78.3 from the host's Poppler
directory on PATH. That DLL lacks the unsuffixed ICU exports required by Qt and
caused a frozen WebEngine import error. The source environment loaded Windows'
native ICU 72.1. A clean rebuild with PATH restricted to the locked environment,
Windows system directories, Python and Git passed detached `--selftest` (exit 0)
and the eight-second smoke (exit 124). No dependency pin or spec change was needed.
