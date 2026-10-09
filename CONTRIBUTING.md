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

Windows delivery also requires a frozen build, startup check, and subsystem self-test.
Follow **ogp-change-control §2.8** in the [change-control skill](.agents/skills/ogp-change-control/SKILL.md).
Do not replace the subsystem test with a startup-only check.
If a required check cannot run, state that limitation in the PR.

## Tests, translations, and documentation

Every user story requires an end-to-end integration test. Bug fixes need regression tests at the appropriate layer.
Developer tools should have subprocess tests. Documentation-only edits need relevant documentation checks.
Do not add an unrelated UI test to a prose-only change.
See [the integration-test policy](docs/08-crosscutting-concepts/README.md#810-integration-test-policy).

Wrap every new application display string for Qt translation. Register and compile its translations.
See [translation instructions](docs/08-crosscutting-concepts/README.md#83-internationalization-i18n).
Public documentation is English. This requirement does not add application translations for Markdown prose.

Update arc42 documentation when behaviour, architecture, or requirements change.
Use [docs/wiki/README.md](docs/wiki/README.md) for wiki maintenance.
Edit repository wiki sources rather than published pages.
Keep `AGENTS.md` and `CLAUDE.md` synchronized. Keep project skills in both agent libraries synchronized.

## Pull requests and review

Open a **draft PR** with the problem, resulting behaviour, related issue, validation evidence, and manual review checklist.
The project requires an independent senior-reviewer pass before opening the draft.
Address all P0/P1 findings and repeat review after fixes.
If that review cannot run, state the unmet gate and keep the PR draft.

The PR remains draft until the owner confirms manual testing or documentation review passed.
Then use the normal protected merge with the verified head commit. Never bypass a failed check.
Wiki publication follows approval and merge. It does not run in CI.

Contributions use the project's [GPL-3.0-or-later licence](LICENSE).
Respect separate licences and attribution requirements for bundled data and assets.
