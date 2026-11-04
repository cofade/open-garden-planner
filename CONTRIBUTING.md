# Contributing to Open Garden Planner

Contributions, including AI-assisted contributions, are welcome.
Contributors remain responsible for correctness, tests, and documentation.
Read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Choose work and ask questions

- Use [Discussions](https://github.com/cofade/open-garden-planner/discussions) for public questions and ideas.
- Use [issues](https://github.com/cofade/open-garden-planner/issues) for bugs and confirmed tasks.
- Read the [roadmap](docs/roadmap.md) and [architecture](docs/05-building-block-view/README.md).
- Comment on an issue before starting substantial work so contributors can coordinate.
- Report vulnerabilities through the private channel in [SECURITY.md](SECURITY.md).

Remove credentials, personal information, and write-enabled Agent API URLs from public attachments.
Discussions and ordinary issues are public.

## Development setup

Windows 10/11 is the primary application platform. CI also tests on Linux.
The locked development environment uses **Python 3.11**. Application metadata permits Python 3.11+.
Install Git and Python 3.11, then clone the repository or your fork.

Bootstrap the exact uv version declared in the manifest:

```text
git clone https://github.com/cofade/open-garden-planner.git
cd open-garden-planner
python -c "import subprocess,sys,tomllib; pin=tomllib.load(open('pyproject.toml','rb'))['tool']['uv']['required-version']; subprocess.run([sys.executable,'-m','pip','install','uv'+pin],check=True)"
uv sync --locked --python 3.11 --all-extras --group build --no-install-project
uv pip install --python .venv/Scripts/python.exe --no-deps --no-build-isolation --editable .
uv pip check --python .venv/Scripts/python.exe
.venv/Scripts/python.exe scripts/check_dependency_lock.py
.venv/Scripts/python.exe -m open_garden_planner
```

On Linux, substitute `.venv/bin/python` for `.venv/Scripts/python.exe`.
CI's Qt system packages are listed in [.github/workflows/ci.yml](.github/workflows/ci.yml).
Use `QT_QPA_PLATFORM=offscreen` for headless Qt tests.
Online service credentials are not required for tests.

`uv.lock` owns the Python dependency selection. `pylock.toml` is its checked export.
Dependency updates require separate review. Do not change locks merely to repair a local environment.

## Branches and commits

Create a branch before editing. Never commit directly to `master`.
Use `feature/US-X.X-description`, `fix/NNN-description`, or `chore/description` as appropriate.
Use conventional commits such as `feat(US-X.X): ...`, `fix(#NNN): ...`, or `chore: ...`.
The release workflow skips chore squash commits. CI owns release tags. Never create tags manually.

## Quality checks

Run commands from the repository root with the locked interpreter:

```text
.venv/Scripts/python.exe -m pytest tests/ -v
.venv/Scripts/python.exe -m pytest tests/ -m perf -n 0
.venv/Scripts/python.exe -m ruff check src/ tests/ scripts/
.venv/Scripts/python.exe -m bandit -r src/ --severity-level high
.venv/Scripts/python.exe scripts/check_no_secrets.py
.venv/Scripts/python.exe scripts/check_agent_context.py
.venv/Scripts/python.exe scripts/check_skill_citations.py
.venv/Scripts/python.exe scripts/check_dependency_lock.py
.venv/Scripts/python.exe scripts/check_mypy_baseline.py
.venv/Scripts/python.exe scripts/sync_wiki.py --check
```

CI also measures coverage and enforces package line floors. Type allowances are per file and platform.
Do not raise allowances or lower coverage floors to hide regressions.
See [quality requirements](docs/10-quality-requirements/README.md) and the CI workflow for the exact gates.

### The two pytest lines are both required

`addopts` runs the suite in parallel (`-n auto --dist worksteal`) and **deselects** the
`perf` marker, so wall-clock-sensitive tests never share a runner with the workers -
they fail intermittently when they do. (`-n auto` is 4 on a CI runner and 20 on a dev
box; eight is the measurement configuration those numbers were taken in, not a constant.)

- `pytest tests/` — everything except the `perf`-marked tests.
- `pytest tests/ -m perf -n 0` — exactly those, on a quiet runner. CI runs it as its own step.

Three details in that second command are load-bearing, and the failure modes are quiet:

| Form | What happens |
|---|---|
| `pytest tests/ -m perf -n 0` | all 14, correctly |
| `pytest tests/perf -m perf` | **7, and it passes** — 7 of the 14 live elsewhere |
| `pytest tests/perf` | **nothing at all** — `addopts`' `-m 'not perf'` wins |
| `pytest tests/ -m perf` | 14, but spread across every worker, i.e. exactly what the split prevents |

Running only the first and assuming the second ran with it is the easy mistake here.
The marker means "wall-clock sensitive", so such tests are marked wherever they live —
7 of the 14 are outside `tests/perf/`. `tests/unit/test_perf_marker_guard.py` fails the
build if a wall-clock assertion is added without the marker, so this list cannot go stale
without something going red.

For a single file or a handful of tests, add `-n 0`: worker start-up dominates when there
is almost nothing to distribute.

Windows delivery also requires a frozen build, startup check, and subsystem self-test.
Follow **ogp-change-control §2.8** in the [change-control skill](.agents/skills/ogp-change-control/SKILL.md).
Do not replace the subsystem test with a startup-only check.
If a required check cannot run, state that limitation in the PR.

## Tests and documentation

Every user story requires an end-to-end integration test. Bug fixes need regression tests at the appropriate layer.
Developer tools should have subprocess tests. Documentation-only edits need relevant documentation checks.
Do not add an unrelated UI test to a prose-only change.
See [the integration-test policy](docs/08-crosscutting-concepts/README.md#810-integration-test-policy).

Public documentation is English. This requirement does not add application translations for Markdown prose.

Update arc42 documentation when behaviour, architecture, or requirements change.
Use [docs/wiki/README.md](docs/wiki/README.md) for wiki maintenance.
Edit repository wiki sources rather than published pages.
Keep `AGENTS.md` and `CLAUDE.md` synchronized. Keep project skills in both agent libraries synchronized.

## Contributing translations and adding languages

Open Garden Planner supports internationalization through Qt Linguist (`.ts` and `.qm` files).
Shipped languages currently include English (`en`, source), German (`de`), and Spanish (`es`).

All supported languages are registered in `src/open_garden_planner/core/i18n.py` under `SUPPORTED_LANGUAGES`.
A strict quality gate (`scripts/check_translations.py`) enforces that **every registered target language must have 100% coverage** of the active UI source inventory.

### Rules for translations

- **100% key coverage**: No missing keys, no obsolete/vanished keys, and no `type="unfinished"` entries.
- **Preserve placeholders and markup**: Format fields like `{name}`, `{0}`, `%1`, and HTML tags (e.g. `<b>`, `<i>`) must remain intact in translated strings.
- **Unique menu mnemonics (`&`)**: Accelerators within the same menu or submenu level must not collide (validated by `tests/integration/test_icon_system.py::TestAppWiring::test_menu_mnemonics_are_unique_per_language`).
- **UTF-8 encoding**: All translation files must be saved as UTF-8 without BOM. Never use PowerShell `Set-Content -Encoding UTF8` (it double-encodes non-ASCII characters).

### Updating or improving existing translations

To fix or improve translations for an existing language (e.g. `de` or `es`):

1. Edit the relevant `.ts` catalog in `src/open_garden_planner/resources/translations/open_garden_planner_<lang>.ts` (using Qt Linguist or a text editor) or update the translation mapping scripts (e.g. `scripts/translations_es/`).
2. Recompile the binary catalog:
   ```powershell
   $env:PYTHONUTF8 = "1"
   .venv/Scripts/python.exe scripts/compile_translations.py
   ```
3. Run the validation gate:
   ```powershell
   $env:PYTHONUTF8 = "1"
   .venv/Scripts/python.exe scripts/check_translations.py
   ```
4. Verify tests pass:
   ```powershell
   .venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py tests/integration/test_translation_gate.py -v
   ```

### Adding a new language

To add a new language to Open Garden Planner:

1. **Register the language**:
   Add the locale code and its native display name to `SUPPORTED_LANGUAGES` in `src/open_garden_planner/core/i18n.py`:
   ```python
   SUPPORTED_LANGUAGES: dict[str, str] = {
       "en": "English",
       "de": "Deutsch",
       "es": "Español",
       "fr": "Français",  # Example
   }
   ```
2. **Extract source keys**:
   Run the translation updater to generate the new `.ts` file with all current source strings:
   ```powershell
   $env:PYTHONUTF8 = "1"
   .venv/Scripts/python.exe scripts/update_translations.py
   ```
   This creates `src/open_garden_planner/resources/translations/open_garden_planner_<code>.ts` with all strings marked as `type="unfinished"`.
3. **Translate the strings**:
   Provide translations for all messages in the new `.ts` file. Remove the `type="unfinished"` attribute as each translation is completed.
4. **Compile the catalog**:
   ```powershell
   $env:PYTHONUTF8 = "1"
   .venv/Scripts/python.exe scripts/compile_translations.py
   ```
   This compiles `open_garden_planner_<code>.qm`.
5. **Run the translation gate**:
   ```powershell
   .venv/Scripts/python.exe scripts/check_translations.py
   ```
   The checker verifies that all source keys exist in the new catalog, placeholders match, and compiled binaries match Qt runtime lookups.
6. **Update installer packaging**:
   In `installer/ogp_installer.nsi`, add the NSIS Modern UI language macro:
   ```nsis
   !insertmacro MUI_LANGUAGE "French"  # Example
   ```
7. **Run the full test suite**:
   Verify unit tests, UI tests, menu mnemonic collision tests, and the translation gate:
   ```powershell
   .venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py tests/ui/test_language_menu.py tests/integration/test_translation_gate.py tests/integration/test_icon_system.py -v
   ```
For further details and source pattern requirements, see [docs/TRANSLATING.md](docs/TRANSLATING.md) and [docs/08-crosscutting-concepts/README.md#83-internationalization-i18n](docs/08-crosscutting-concepts/README.md#83-internationalization-i18n).

## Pull requests and review

Review routing and owner-only recovery actions are in the
[maintainer continuity runbook](docs/07-deployment-view/maintainer-continuity.md).
CODEOWNERS does not grant release privileges.

Open a **draft PR** with the problem, resulting behaviour, related issue, validation evidence, and manual review checklist.
The project requires an independent senior-reviewer pass before opening the draft.
Address all P0/P1 findings and repeat review after fixes.
If that review cannot run, state the unmet gate and keep the PR draft.

The PR remains draft until the owner confirms manual testing or documentation review passed.
Then use the normal protected merge with the verified head commit. Never bypass a failed check.
Wiki publication follows approval and merge. It does not run in CI.

Contributions use the project's [GPL-3.0-or-later licence](LICENSE).
Respect separate licences and attribution requirements for bundled data and assets.
