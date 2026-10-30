"""The engine package in the frozen exe and in CI, pinned as text (Phase 17 L1.2, #385).

Neither the PyInstaller build nor GitHub's runners run in the test suite, so the
things that silently drop the 3D engine from a release are pinned where they
are written down:

- ``installer/ogp.spec`` ships the QML and shader files and names the lazily
  imported package (a missing data file only fails when a Model uses the shader);
- ``release.yml`` still runs ``--selftest`` the one way that tests the shipping
  condition, decides by the exit code alone, cannot hang, and prints the log in a
  step of its own that always runs;
- ``frozen-selftest.yml`` runs the same gate on pull requests, with the release
  recipe and the same step scripts, whenever shipped code changes;
- ``ci.yml`` has the ``render3d`` job on both platforms, running files that
  exist and are opt-in, and the job is not a required check.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "src" / "open_garden_planner" / "ui" / "view3d" / "quick3d"
SPEC = (REPO / "installer" / "ogp.spec").read_text(encoding="utf-8")
CI = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
RELEASE = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
FROZEN = (REPO / ".github" / "workflows" / "frozen-selftest.yml").read_text(encoding="utf-8")
RENDER_TESTS = ("tests/integration/test_quick3d_render.py",
                "tests/integration/test_quick3d_engine.py",
                "tests/integration/test_quick3d_selftest.py",
                "tests/integration/test_quick3d_lifecycle.py",
                "tests/integration/test_scene3d_ground_render.py")  # the baked ground (L1.5)
#: The default workspace's real-host gates (#540) — close and compatibility only in CI.
WORKSPACE_RENDER = "tests/integration/test_view3d_workspace_render.py"
#: The subset: G5's close rows (with the frozen-exe variants, which skip without the exe)
#: and G6's crash-marker / compatibility / try-hardware rows. Everything else in that file
#: is a budget, a soak, the camera rule, WebEngine or shortcut-focus work.
WORKSPACE_K = (
    '-k "closes_clean or start_that_died or compatibility_mode or try_hardware"'
)


def _code(text: str) -> str:
    """A file without its ``#`` comment lines (a rule named only in a comment is not a rule)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


class TestSpec:
    def test_the_qml_and_shader_files_are_bundled(self) -> None:
        loop = re.search(
            r'for f in \(SRC / "open_garden_planner" / "ui" / "view3d" / "quick3d" / "qml"\)'
            r'\.rglob\("\*"\):\n\s+if f\.is_file\(\):\n\s+rel = f\.relative_to\(SRC\)\n'
            r"\s+datas\.append\(\(str\(f\), str\(rel\.parent\)\)\)", _code(SPEC))
        assert loop is not None, "ogp.spec no longer bundles ui/view3d/quick3d/qml/*"
        assert sorted(p.name for p in (PACKAGE / "qml").iterdir()) == [
            "Garden.qml", "foliage.frag", "foliage.vert", "foliage_door.frag", "foliage_door.vert",
            "grass.vert", "grass_door.vert", "ground.frag", "lawn.frag", "overlay.frag", "overlay.vert", "ring.frag",
            "ring.vert",
            "screen.frag", "screen.vert", "water.frag", "water_door.frag"]

    def test_every_module_of_the_package_is_a_hidden_import(self) -> None:
        """The package is imported lazily; the spec names each module, as it does for
        every other lazily loaded part of the app."""
        code = _code(SPEC)
        assert '"open_garden_planner.ui.view3d.quick3d",' in code
        for module in sorted(PACKAGE.glob("*.py")):
            if module.name != "__init__.py":
                name = f'"open_garden_planner.ui.view3d.quick3d.{module.stem}",'
                assert name in code, f"{module.name} is missing from ogp.spec's hiddenimports"
        for binding in ("PyQt6.QtQuick", "PyQt6.QtQml", "PyQt6.QtQuick3D"):
            assert f'"{binding}",' in code

    def test_the_spike_left_the_bundle_with_l1_10(self) -> None:
        """L1.10 trimmed the spec with the spike: its QML, its modules and
        ``PyQt6.QtQuickWidgets`` (which only the spike's ``quick.py`` imported — the
        product hosts a ``QQuickView``, never a ``QQuickWidget``)."""
        code = _code(SPEC)
        assert "spike_q3d" not in code
        assert '"PyQt6.QtQuickWidgets",' not in code


def _step(workflow: str, name: str) -> str:
    """One step of a workflow — from its ``- name:`` up to the next step (or the comment
    block that introduces the next step)."""
    start = workflow.index(f"- name: {name}")
    end = workflow.find("\n      - name:", start + 10)
    step = workflow[start:] if end < 0 else workflow[start:end]
    lines = step.rstrip().splitlines()
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        lines.pop()  # the next step's comment block is not part of this one
    return "\n".join(lines) + "\n"


def _selftest_step(workflow: str) -> str:
    return _step(workflow, "Verify frozen subsystems")


def _log_step(workflow: str) -> str:
    return _step(workflow, "Print the self-test log")


def _script(step: str) -> str:
    """The step's ``run: |`` block."""
    return step[step.index("        run: |\n") + len("        run: |\n"):]


class TestReleaseWorkflow:
    def _step(self) -> str:
        return _selftest_step(RELEASE)

    def test_the_step_names_the_new_coverage(self) -> None:
        step = self._step()
        assert "Qt Quick 3D" in step.splitlines()[0]
        failure = next(line for line in step.splitlines() if "Frozen self-test failed" in line)
        assert failure.strip().startswith('Write-Host "::error::Frozen self-test failed (exit ')
        for covered in ("#277", "#291", "Qt Quick 3D", "WARP", "watchdog", "The next step prints"):
            assert covered in failure, covered

    def test_the_verdict_is_still_the_exit_code_alone(self) -> None:
        """Nothing but ``$p.ExitCode`` decides — and the step does nothing else."""
        step = self._step()
        assert step.count("exit 1") == 2  # the missing exe, the failed self-test — as before
        assert re.search(r"\$p = Start-Process -FilePath \$exe -ArgumentList \"--selftest\" "
                         r"-Wait -PassThru", step)
        decisions = [line.strip() for line in step.splitlines() if line.strip().startswith("if (")]
        assert decisions == [
            'if (-not (Test-Path $exe)) { Write-Host "::error::Frozen exe not found: $exe"; exit 1 }',
            "if ($p.ExitCode -ne 0) {",
        ]
        script = _script(step)
        order = [script.index(marker) for marker in (
            "$p = Start-Process", "if ($p.ExitCode -ne 0) {", "Frozen self-test failed",
            "            exit 1\n", "Frozen self-test passed")]
        assert order == sorted(order), order
        assert "Write-Error" not in script, "Write-Error ends the step at once"
        assert "Get-Content" not in script, "the log is the next step's business"

    def test_the_exe_writes_its_log_where_the_next_step_reads_it(self) -> None:
        """The exe has no stdout; ``OGP_SELFTEST_LOG`` is the only way to its log. Both
        steps get the SAME path, from the step's own ``env`` (the child inherits it)."""
        path = "          OGP_SELFTEST_LOG: ${{ runner.temp }}/ogp-selftest-3d.log\n"
        for step in (self._step(), _log_step(RELEASE)):
            assert step.count(path) == 1 and step.index("        env:\n") < step.index(path) < step.index(
                "        run: |\n")
        assert "Get-Content -LiteralPath $env:OGP_SELFTEST_LOG -ErrorAction Stop" in _log_step(RELEASE)

    def test_the_log_is_printed_by_a_step_that_always_runs_and_cannot_fail(self) -> None:
        """Review round 2, P2-6. The self-test step used to print the log itself, after
        the verdict: a step cut off by its time limit prints nothing after the cut —
        and that is the run whose log says where it hung. The log step comes right
        after, runs ``always()`` (in a release run: when a release is being built at
        all), reads inside try/catch and ends with ``exit 0``."""
        after = RELEASE[RELEASE.index("      - name: Verify frozen subsystems"):]
        names = re.findall(r"^      - name: (.+)$", after, re.MULTILINE)
        assert names[:2] == ["Verify frozen subsystems (Agent API #291, A1 checks, Qt Quick 3D "
                             "render #277)", "Print the self-test log"]
        step = _log_step(RELEASE)
        assert "        if: always() && steps.check_tag.outputs.exists == 'false'\n" in step
        script = _script(step)
        order = [script.index(marker) for marker in (
            "try {", "Get-Content", "} catch {", "The verdict of the self-test step stands",
            "          exit 0\n")]
        assert order == sorted(order), order
        assert "exit 1" not in script and "Write-Error" not in script
        assert script.rstrip().endswith("exit 0")

    def test_neither_the_step_nor_the_job_can_run_for_six_hours(self) -> None:
        """Review P1-4 (1): the step and the job are bounded — and so is the exe itself
        (``main.SELFTEST_WATCHDOG_S``), well inside the step's limit."""
        # read, not imported: main.py imports QtWebEngine, which refuses to load once a
        # QApplication exists — an import here would pass or fail by test order
        source = (REPO / "src" / "open_garden_planner" / "main.py").read_text(encoding="utf-8")
        watchdog = re.search(r"^SELFTEST_WATCHDOG_S = (\d+(?:\.\d+)?)$", source, re.MULTILINE)
        assert watchdog is not None, "main.py no longer declares SELFTEST_WATCHDOG_S"
        step = self._step()
        assert "        timeout-minutes: 10\n" in step
        assert float(watchdog.group(1)) <= 0.5 * 10 * 60, "the in-exe watchdog must fire first"
        job = RELEASE[RELEASE.index("\n  release:\n"):RELEASE.index("\n    steps:\n")]
        assert re.search(r"\n    timeout-minutes: \d+\n", job), "the release job has no time limit"


class TestFrozenSelftestWorkflow:
    """Review P1-4 (2): the frozen gate BEFORE a merge, not only after it."""

    def _triggers(self) -> str:
        return _code(FROZEN[FROZEN.index("\non:\n"):FROZEN.index("\npermissions:")])

    def test_it_runs_on_demand_and_on_every_pull_request_that_changes_shipped_code(self) -> None:
        """Review round 2, P2-11: the first filter named the 3D package and ``main.py`` —
        but ``--selftest`` also exercises ``core/scene3d`` and the Agent API, and the
        project's rule is "build and verify the exe before every merge". The whole
        package, then."""
        triggers = self._triggers()
        assert "  workflow_dispatch:\n" in triggers
        assert "  pull_request:\n    branches: [master]\n    paths:\n" in triggers
        assert "push:" not in triggers, "not on every push: the build takes minutes"
        paths = re.findall(r'^      - "([^"]+)"$', triggers, re.MULTILINE)
        assert paths == [
            "src/open_garden_planner/**",
            "installer/**",
            "pyproject.toml",
            "uv.lock",
            "pylock.toml",
            ".github/workflows/frozen-selftest.yml",
            ".github/workflows/release.yml",
            ".github/actions/setup-locked-env/**",
        ]

    def test_every_filtered_path_exists(self) -> None:
        """A path filter that matches nothing is a workflow that never runs."""
        for pattern in re.findall(r'^      - "([^"]+)"$', self._triggers(), re.MULTILINE):
            target = REPO / pattern.removesuffix("/**")
            assert target.exists(), pattern
        for shipped in ("ui/view3d/quick3d/selftest.py", "core/scene3d/sync.py",
                        "agent_api/__init__.py", "main.py"):
            assert (REPO / "src/open_garden_planner" / shipped).is_file(), shipped

    def test_it_can_only_read_the_repository(self) -> None:
        assert "\npermissions:\n  contents: read\n" in FROZEN
        assert FROZEN.count("permissions:") == 1, "no job widens the workflow's permissions"

    def test_it_uses_no_action_that_ci_does_not_use(self) -> None:
        used = set(re.findall(r"uses: (\S+)", _code(FROZEN)))
        assert used == {"actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "./.github/actions/setup-locked-env"}
        assert used <= set(re.findall(r"uses: (\S+)", _code(CI)))

    def test_it_builds_with_the_release_recipe_not_a_copy_of_it(self) -> None:
        code = _code(FROZEN)
        assert "runs-on: windows-latest" in code
        assert "        run: python installer/build_installer.py --skip-nsis\n" in code
        assert "PyInstaller" not in code and "ogp.spec" not in code, "no second build recipe"
        assert "run: python installer/build_installer.py --version" in _code(RELEASE)
        script = (REPO / "installer" / "build_installer.py").read_text(encoding="utf-8")
        assert '"--skip-nsis"' in script and '"--noconfirm"' in script and '"--clean"' in script

    def test_every_step_has_a_limit_and_the_jobs_is_larger_than_their_sum(self) -> None:
        """Review round 2, P2-10: only the job's 45 minutes bounded the build. Round 3,
        P2-9: the three step limits then added up to exactly those 45 — before checkout
        and the environment — and this test pinned ``max(limits) < job``, the wrong
        inequality. The job's limit must never be what ends a step (the step that
        prints the log would not get its turn): EVERY step has a limit, and the job's
        is larger than their sum."""
        step = _step(FROZEN, "Build the bundle")
        assert "        timeout-minutes: 30\n" in step
        code = _code(FROZEN)
        steps = re.findall(r"^      - (?:name|uses): (.+)$", code, re.MULTILINE)
        limits = [int(n) for n in re.findall(r"^        timeout-minutes: (\d+)$", code, re.MULTILINE)]
        job = int(re.search(r"^    timeout-minutes: (\d+)$", FROZEN, re.MULTILINE).group(1))  # type: ignore[union-attr]
        assert len(steps) == 7 and steps[:3] == ["actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
                                                 "./.github/actions/setup-locked-env",
                                                 "Read the version this bundle will report"]
        assert limits == [5, 10, 1, 30, 5, 10, 2], "one limit per step, in the steps' order"
        for name, after in zip(steps, re.split(r"^      - (?:name|uses): .+$", code, flags=re.MULTILINE)[1:],
                               strict=True):
            assert len(re.findall(r"^        timeout-minutes: \d+$", after, re.MULTILINE)) == 1, name
        assert job > sum(limits), f"the job's {job} min must exceed the steps' {sum(limits)}"
        assert job - sum(limits) >= 5, "and leave room for the runner's own set-up and clean-up"
        assert f"({sum(limits)} minutes)" in FROZEN, "the comment beside the job's limit states the sum"

    def test_the_comments_say_what_the_bundle_and_the_smoke_really_are(self) -> None:
        """Review round 2, P2-7 / P2-10. The workflow said "no ``_version.py`` is written"
        — the build script always writes one; without ``--version`` it is the version in
        ``pyproject.toml`` (master's #490 — it was a fixed ``1.0.0`` before), so the
        pull-request exe runs the update check as the last synced release during the
        smoke. And "survived 8 seconds" is also true of a process blocked in an error
        dialog. Pinned against the files the statements are about."""
        script = (REPO / "installer" / "build_installer.py").read_text(encoding="utf-8")
        assert "APP_VERSION = _manifest_version()" in script
        assert 'tomllib.load(fh)["project"]["version"]' in script
        assert re.search(
            r"if not args\.skip_pyinstaller:\n\s+_write_version_module\(APP_VERSION\)"
            r"\n\s+try:\n\s+run_pyinstaller\(\)\n\s+finally:\n\s+_remove_version_module\(\)",
            script,
        ), "the generated module must be removed after PyInstaller (PF-CI-15)"
        application = (REPO / "src/open_garden_planner/app/application.py").read_text(encoding="utf-8")
        start = application.index("    def _start_update_check(self) -> None:")
        body = application[start:application.index("\n    def ", start + 10)]
        assert 'if not getattr(sys, "frozen", False):' in body
        assert "environ" not in body and "argv" not in body, (
            "the app has a switch for the update check now: use it for the smoke, and say so")
        checker = (REPO / "src/open_garden_planner/services/update_checker.py").read_text(encoding="utf-8")
        assert "except Exception:" in checker[checker.index("class UpdateChecker"):]
        comments = "\n".join(line for line in FROZEN.splitlines() if line.lstrip().startswith("#"))
        assert "no _version.py" not in comments.lower()
        for statement in ("writes _version.py with the version in pyproject.toml", "calls itself by the last synced release",
                          "blocked in an error dialog", "The self-test below is the real gate",
                          "the app has no switch to turn", "swallows every network error"):
            assert " ".join(statement.split()) in " ".join(comments.replace("#", " ").split()), statement

    def test_it_runs_the_same_two_steps_as_the_release(self) -> None:
        """One script each, two workflows: a fix to a release step that is not made here
        (or the other way round) would leave the pull-request gate testing something
        else."""
        assert _script(_selftest_step(FROZEN)) == _script(_selftest_step(RELEASE))
        assert _script(_log_step(FROZEN)) == _script(_log_step(RELEASE))
        assert "        shell: pwsh\n        timeout-minutes: 10\n" in _selftest_step(FROZEN)
        assert "        if: always()\n" in _log_step(FROZEN)
        after = FROZEN[FROZEN.index("      - name: Verify frozen subsystems"):]
        assert re.findall(r"^      - name: (.+)$", after, re.MULTILINE)[1:] == ["Print the self-test log"]

    def test_the_job_is_bounded_and_not_a_required_check(self) -> None:
        job = FROZEN[FROZEN.index("\njobs:\n"):FROZEN.index("    steps:\n")]
        assert re.search(r"\n    timeout-minutes: \d+\n", job)
        name = re.search(r"\n    name: (.+)\n", job)
        assert name is not None
        protection = json.loads((REPO / "quality" / "master-protection.json").read_text(encoding="utf-8"))
        contexts = protection["required_status_checks"]["contexts"]
        assert name.group(1) not in contexts and not [c for c in contexts if "frozen" in c.lower()]


class TestRenderJob:
    def _job(self) -> str:
        start = CI.index("\n  render3d:\n")
        return CI[start:]

    def test_the_job_runs_on_both_platforms_with_the_tier_switched_on(self) -> None:
        job = _code(self._job())
        assert "os: [ubuntu-24.04, windows-latest]" in job
        assert 'OGP_RENDER3D: "1"' in job
        assert "fail-fast: false" in job and "timeout-minutes:" in job
        assert "- uses: ./.github/actions/setup-locked-env" in job

    def test_linux_renders_under_xvfb_with_opengl_on_llvmpipe(self) -> None:
        job = _code(self._job())
        linux = next(line for line in job.splitlines() if "xvfb-run" in line and "pytest" in line)
        assert linux.strip().startswith('run: xvfb-run -a -s "-screen 0 1920x1080x24" python -m pytest')
        assert "QSG_RHI_BACKEND: opengl" in job and 'LIBGL_ALWAYS_SOFTWARE: "1"' in job
        packages = next(line for line in job.splitlines() if "apt-get install" in line)
        for package in ("xvfb", "libegl1", "libxcb-cursor0", "libgl1-mesa-dri"):
            assert f" {package}" in packages, package

    def test_both_platforms_run_the_same_opt_in_files_and_the_workspace_gates(self) -> None:
        job = _code(self._job())
        runs = [line for line in job.splitlines() if "python -m pytest" in line]
        budget_runs = [line for line in runs if "::test_real_engine_scrubs_300_models_within_frame_budget" in line]
        scene_runs = [line for line in runs if line not in budget_runs]
        assert len(budget_runs) == 2
        assert len(scene_runs) == 4, "two engine runs AND two workspace runs, per OS"
        engine_runs = [line for line in scene_runs if any(name in line for name in RENDER_TESTS)]
        workspace_runs = [line for line in scene_runs if WORKSPACE_RENDER in line]
        assert len(engine_runs) == len(workspace_runs) == 2, (engine_runs, workspace_runs)
        for line in engine_runs:
            # -k is a SESSION filter: on the engine command it would deselect the engine
            # files (#540's first review found exactly that).
            assert " -k " not in line, line
            assert WORKSPACE_RENDER not in line, line
            assert "tests/integration/test_plant_forge_workspace.py" in line
        for line in workspace_runs:
            # #540: the default workspace's close/compat gates now run on a real host,
            # with the wall-clock bounds and the multi-process soaks kept local.
            assert '-m "not perf and not soak"' in line, line
            assert WORKSPACE_K in line, line
        for line in budget_runs:
            assert "-m perf -n 0" in line
        assert sum("xvfb-run" in line for line in budget_runs) == 1
        for name in RENDER_TESTS:
            source = (REPO / name).read_text(encoding="utf-8")
            assert "render_tier" in source, f"{name} is not marked as render tier"
        assert "QT_QPA_PLATFORM" not in job, (
            "the pytest process stays offscreen; the test helper gives the DRIVER a real "
            "platform (quick3d_render_support.render_env)")

    def test_every_workspace_filter_term_still_names_a_test(self) -> None:
        """A renamed test would make `-k` select nothing and CI would stay green."""
        source = (REPO / WORKSPACE_RENDER).read_text(encoding="utf-8")
        names = set(re.findall(r"^def (test_\w+)", source, flags=re.MULTILINE))
        terms = re.findall(r"(\w+)", WORKSPACE_K.split('"')[1])
        assert len(terms) == 7 and "or" in terms  # four terms, three "or"s
        for term in (t for t in terms if t != "or"):
            assert any(term in name for name in names), f"-k term {term!r} matches no test"

    def test_the_soaks_are_marked_and_the_workspace_file_is_render_tier(self) -> None:
        """#540: an unmarked soak would be pulled into the CI job by the file name."""
        source = (REPO / WORKSPACE_RENDER).read_text(encoding="utf-8")
        assert "pytestmark = render_tier" in source
        assert source.count("@pytest.mark.soak") >= 10
        job = _code(self._job())
        assert '-m "not perf and not soak"' in job
        settings = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        assert '"soak: ' in settings, "the marker must be registered"

    def test_the_job_is_not_a_required_check(self) -> None:
        protection = json.loads((REPO / "quality" / "master-protection.json").read_text(encoding="utf-8"))
        contexts = protection["required_status_checks"]["contexts"]
        assert not [name for name in contexts if "render" in name.lower() or "3d" in name.lower()]

    def test_frames_and_logs_are_uploaded_even_when_the_job_fails(self) -> None:
        job = _code(self._job())
        assert "OGP_RENDER3D_ARTIFACTS: ${{ github.workspace }}/render3d-artifacts" in job
        upload = job[job.index("- name: Upload frames, results and logs"):]
        assert "if: always()" in upload and "path: render3d-artifacts/" in upload


def test_the_render_helper_skips_cleanly_without_the_switch(monkeypatch) -> None:
    """On all three platforms: without ``OGP_RENDER3D=1`` the tier is skipped with a
    reason; on Linux it also needs a display; on Windows the switch is enough (the
    driver process gets the real platform — the test process is offscreen)."""
    from tests.integration import quick3d_render_support as support

    monkeypatch.delenv("OGP_RENDER3D", raising=False)
    assert "OGP_RENDER3D=1" in (support.render_tier_skip_reason() or "")
    monkeypatch.setenv("OGP_RENDER3D", "1")
    for platform, display, expected in (("win32", None, None), ("linux", None, "xvfb"),
                                        ("linux", ":99", None), ("darwin", None, None)):
        monkeypatch.setattr(support.sys, "platform", platform)
        if display is None:
            monkeypatch.delenv("DISPLAY", raising=False)
        else:
            monkeypatch.setenv("DISPLAY", display)
        reason = support.render_tier_skip_reason()
        assert (reason is None) if expected is None else (expected in (reason or "")), (platform, reason)


def test_the_driver_gets_a_real_platform_and_this_checkouts_code(monkeypatch, tmp_path: Path) -> None:
    from tests.integration import quick3d_render_support as support

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")  # what the test process runs under
    monkeypatch.setattr(support.sys, "platform", "win32")
    windows = support.render_env(tmp_path)
    assert "QT_QPA_PLATFORM" not in windows  # the default platform: Direct3D 11
    monkeypatch.setattr(support.sys, "platform", "linux")
    monkeypatch.delenv("QSG_RHI_BACKEND", raising=False)
    linux = support.render_env(tmp_path)
    assert (linux["QT_QPA_PLATFORM"], linux["QSG_RHI_BACKEND"]) == ("xcb", "opengl")
    assert linux["LIBGL_ALWAYS_SOFTWARE"] == "1" and linux["XDG_CONFIG_HOME"].startswith(str(tmp_path))
    for env in (windows, linux):
        hook, first, second = env["PYTHONPATH"].split(support.os.pathsep)[:3]
        assert Path(hook) == support.CHILD_SITE, "the settings hook comes before everything"
        assert Path(first) == REPO / "src" and Path(second) == REPO
    forced = support.render_env(tmp_path, QT_QPA_PLATFORM="offscreen")
    assert forced["QT_QPA_PLATFORM"] == "offscreen"  # a test may ask for the no-3D platform


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_no_child_of_an_engine_test_can_reach_the_developers_data_or_profile(
        monkeypatch, tmp_path: Path, platform: str) -> None:
    """Review round 2, P2-8 / P2-9: the environment HANDED TO THE CHILD, inspected.

    The render driver loads a plan through ``ProjectManager`` — which creates the app's
    data directory — and it inherited the developer's real ``APPDATA``. Every child a
    test of the engine package starts now gets, whatever the parent's environment
    says: its data directories under the test's own scratch directory, and a user
    profile of the test process's own (``QStandardPaths`` and the graphics driver's
    caches follow the profile, not ``APPDATA`` — measured)."""
    from tests.integration import quick3d_render_support as support

    data = [name for name, _folder in support.PRIVATE_DIRS]
    # review round 3, P2-8: HOME was left alone off Windows — and every XDG location
    # without a variable of its own (the state directory, Documents) follows it
    moved = ["USERPROFILE", "LOCALAPPDATA"] if platform == "win32" else ["HOME", "XDG_CACHE_HOME"]
    assert data == ["APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"]
    for name in (*data, "USERPROFILE", "LOCALAPPDATA", "XDG_CACHE_HOME", "HOME"):
        monkeypatch.setenv(name, str(tmp_path / "the-developers-own" / name))
    monkeypatch.setattr(support.sys, "platform", platform)
    scratch = tmp_path / "scratch"
    profile = support.session_profile()
    for build in (support.isolated_env, support.render_env):
        env = build(scratch)
        for name, folder in support.PRIVATE_DIRS:
            assert Path(env[name]) == scratch / folder and Path(env[name]).is_dir(), (build, name)
        for name in moved:
            assert Path(env[name]).is_dir(), (build, name)
            assert profile == Path(env[name]) or profile in Path(env[name]).parents, (build, name)
        assert not [name for name in (*data, *moved) if "the-developers-own" in env[name]]
    assert profile.is_dir() and profile.name.startswith("ogp-quick3d-profile-")
    assert support.session_profile() == profile, "one profile per test process"
    assert tmp_path not in profile.parents and profile != Path.home()


def test_what_a_child_keeps_from_the_real_home_is_named(monkeypatch, tmp_path: Path) -> None:
    """Off Windows the child's ``HOME`` is not the developer's. Two things a child reads
    from the real one are handed over by name — Python's per-user site directory and the
    X display's cookie — and only when the parent has not set them itself."""
    from tests.integration import quick3d_render_support as support

    home = tmp_path / "the-developers-own" / "home"
    home.mkdir(parents=True)
    (home / ".Xauthority").write_bytes(b"cookie")
    monkeypatch.setattr(support.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(support.site, "getuserbase", lambda: str(home / ".local"))
    monkeypatch.delenv("PYTHONUSERBASE", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)

    monkeypatch.setattr(support.sys, "platform", "linux")
    env = support.isolated_env(tmp_path / "scratch")
    assert Path(env["HOME"]) != home and support.session_profile() in Path(env["HOME"]).parents
    assert env["PYTHONUSERBASE"] == str(home / ".local")
    assert env["XAUTHORITY"] == str(home / ".Xauthority")
    # what the parent set itself is passed through, not replaced
    monkeypatch.setenv("PYTHONUSERBASE", "/opt/base")
    monkeypatch.setenv("XAUTHORITY", "/tmp/xvfb-run.cookie")  # noqa: S108 - a name, never opened
    env = support.isolated_env(tmp_path / "scratch")
    assert (env["PYTHONUSERBASE"], env["XAUTHORITY"]) == ("/opt/base", "/tmp/xvfb-run.cookie")  # noqa: S108
    # nothing of the kind on Windows: the profile variable is USERPROFILE there
    monkeypatch.delenv("PYTHONUSERBASE")
    monkeypatch.delenv("XAUTHORITY")
    monkeypatch.setattr(support.sys, "platform", "win32")
    assert support.kept_from_the_real_home({}) == {}


_ENV_HELPERS = ("isolated_env", "render_env", "_child_env")


def _helper_call(node: ast.AST | None) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _ENV_HELPERS)


def child_environment_problems(source: str, name: str = "<source>") -> tuple[list[str], int]:
    """What is wrong with the way a test file builds its children's environments, and
    how many children it starts.

    The rule: every ``subprocess.run`` / ``Popen`` gets ``env=`` — a call of one of the
    helpers, or a variable that the SAME function assigns from such a call and from
    nothing else (never a parameter, never a module global). ``os.environ`` is read key
    by key and never handed on whole; a local ``_child_env`` must itself return a
    helper's call. (``taskkill``, the tree kill, runs no code of ours.)"""
    tree = ast.parse(source, filename=name)
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    problems: list[str] = []
    children = 0
    for node in ast.walk(tree):
        whole_environ = (isinstance(node, ast.Attribute) and node.attr == "environ"
                         and isinstance(node.value, ast.Name) and node.value.id == "os")
        if whole_environ and not isinstance(parent.get(node), (ast.Attribute, ast.Subscript, ast.Compare)):
            problems.append(f"{name}:{node.lineno} hands on the parent's whole environment: "
                            f"{ast.unparse(parent[node])[:60]}")
        if isinstance(node, ast.FunctionDef) and node.name == "_child_env":
            returns = [inner for inner in ast.walk(node) if isinstance(inner, ast.Return)]
            if len(returns) != 1 or not _helper_call(returns[0].value):
                problems.append(f"{name}:{node.lineno} _child_env() does not return a helper's call")
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("run", "Popen")
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
            continue
        if "taskkill" in ast.unparse(node):
            continue
        children += 1
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        if "env" not in keywords:
            problems.append(f"{name}:{node.lineno} starts a child with the parent's environment")
            continue
        value = keywords["env"]
        if _helper_call(value):
            continue
        function: ast.AST | None = node
        while function is not None and not isinstance(function, ast.FunctionDef):
            function = parent.get(function)
        if not isinstance(value, ast.Name) or function is None:
            problems.append(f"{name}:{node.lineno}: env={ast.unparse(value)[:60]} is not a helper's call")
            continue
        arguments = function.args
        if value.id in {argument.arg for argument in (
                *arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)}:
            problems.append(f"{name}:{node.lineno}: env={value.id} is a parameter of "
                            f"{function.name}(): anything could be passed")
            continue
        sources = [inner.value for inner in ast.walk(function)
                   if isinstance(inner, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
                   and any(isinstance(target, ast.Name) and target.id == value.id
                           for target in (inner.targets if isinstance(inner, ast.Assign) else [inner.target]))]
        if not sources or not all(_helper_call(made) for made in sources):
            problems.append(f"{name}:{node.lineno}: env={value.id} is not built by a helper alone "
                            f"in {function.name}()")
    return problems, children


def test_every_child_environment_of_the_engine_tests_is_built_by_the_helper() -> None:
    """…and nobody builds a child's environment by hand again (``child_environment_problems``
    states the rule). Review round 3, P2-8: this guard used to accept ANY variable that
    was called ``env``."""
    files = [*sorted((REPO / "tests").glob("*/test_quick3d_*.py")),
             *sorted((REPO / "tests" / "integration").glob("quick3d_*.py")),
             REPO / "tests" / "unit" / "test_main_hardening.py"]
    assert len(files) >= 14
    children = 0
    for path in files:
        if path.name == "quick3d_render_support.py":
            continue  # the helper itself
        problems, started = child_environment_problems(path.read_text(encoding="utf-8"), path.name)
        assert not problems, "\n".join(problems)
        children += started
    assert children >= 14


@pytest.mark.parametrize(("body", "problem"), [
    ("    subprocess.run(cmd, env=isolated_env(tmp_path))\n", None),
    ("    env = render_env(tmp_path)\n    env['X'] = '1'\n    subprocess.run(cmd, env=env)\n", None),
    ("    subprocess.run(['taskkill', '/F'], check=False)\n", None),
    ("    home = os.environ.get('HOME')\n    subprocess.run(cmd, env=_child_env(tmp_path))\n", None),
    ("    subprocess.run(cmd)\n", "starts a child with the parent's environment"),
    ("    env = dict(os.environ)\n    subprocess.run(cmd, env=env)\n", "whole environment"),
    ("    env = os.environ.copy()\n    subprocess.run(cmd, env=env)\n", "not built by a helper alone"),
    ("    env = {**os.environ, 'X': '1'}\n    subprocess.run(cmd, env=env)\n", "whole environment"),
    ("    env = {'PATH': '/bin'}\n    subprocess.run(cmd, env=env)\n", "not built by a helper alone"),
    ("    env = isolated_env(tmp_path)\n    env = other()\n    subprocess.run(cmd, env=env)\n",
     "not built by a helper alone"),
    ("    env = isolated_env(tmp_path)\n    env.update(os.environ)\n    subprocess.run(cmd, env=env)\n",
     "whole environment"),
    ("    subprocess.Popen(cmd, env=GLOBAL_ENV)\n", "not built by a helper alone"),
    ("    subprocess.run(cmd, env=make_env())\n", "is not a helper's call"),
], ids=["helper call", "variable from a helper", "tree kill", "a key read", "no env", "dict copy",
        "environ.copy", "unpacked", "hand-made", "reassigned", "updated from the parent",
        "module global", "another function"])
def test_the_child_environment_guard_sees_what_it_is_for(body: str, problem: str | None) -> None:
    source = "import os, subprocess\ndef test_it(tmp_path):\n" + body
    problems, children = child_environment_problems(source)
    assert children == (0 if "taskkill" in body else 1), "the tree kill is not a child of ours"
    if problem is None:
        assert problems == []
    else:
        assert any(problem in line for line in problems), problems


def test_the_child_environment_guard_refuses_a_parameter_and_a_loose_wrapper() -> None:
    by_parameter = "import subprocess\ndef run(cmd, env):\n    subprocess.run(cmd, env=env)\n"
    problems, _children = child_environment_problems(by_parameter)
    assert len(problems) == 1 and "is a parameter of run()" in problems[0]
    loose = ("import os, subprocess\ndef _child_env(scratch):\n    return {'HOME': str(scratch)}\n"
             "def test_it(tmp_path):\n    subprocess.run(['x'], env=_child_env(tmp_path))\n")
    problems, _children = child_environment_problems(loose)
    assert len(problems) == 1 and "_child_env() does not return a helper's call" in problems[0]


# ── the host's state contract is written down in ONE place (review round 3) ──

CONTRACT_HOME = PACKAGE / "lifecycle.py"
#: Every text that once carried a copy of the contract. Nine places; three were wrong.
CONTRACT_LINKERS = (
    PACKAGE / "host.py",
    REPO / "docs" / "05-building-block-view" / "README.md",
    REPO / "docs" / "08-crosscutting-concepts" / "README.md",
    REPO / "docs" / "09-architecture-decisions" / "README.md",
    REPO / "docs" / "11-risks-and-technical-debt" / "README.md",
    REPO / "docs" / "12-glossary" / "README.md",
    REPO / ".claude" / "skills" / "ogp-3d-renderer" / "SKILL.md",
    REPO / ".agents" / "skills" / "ogp-3d-renderer" / "SKILL.md",
)
_STATES = "NEW|STARTING|LIVE|HIDDEN|SPENT|CLOSED"
#: A row of a state table — Markdown (``| `LIVE` | …``) or reStructuredText
#: (````LIVE````, blanks, the rule): a line that BEGINS with a state's name as code.
STATE_ROW = re.compile(
    rf"^[ \t]*(?:\|[ \t]*)?`{{1,2}}({_STATES}|{_STATES.lower()})`{{1,2}}[ \t]*(?:\||[ \t]{{2,}}\S)",
    re.MULTILINE)
#: The states' rules spelled in the facts' letters, and the count the old copies carried.
CONTRACT_PHRASES = ("G and E and R", "V and not M and A", "nine facts")


def test_the_state_contract_is_written_down_in_one_place() -> None:
    """``lifecycle.py``'s module docstring is the contract; every other text LINKS to it.

    After review round 2 the state table stood in nine places and three of them said
    "after every resize the host is starting for one pass" — which the code did not do.
    This cannot check prose for truth; it checks that there is no second copy of the
    TABLE (a row keyed by a state, the rules in the facts' letters) to go stale, and
    that each of those texts names the place where the contract is."""
    home = CONTRACT_HOME.read_text(encoding="utf-8")
    rows = {match.group(1).upper() for match in STATE_ROW.finditer(home)}
    assert rows == set(_STATES.split("|")), f"the contract's own state table is gone: {sorted(rows)}"
    # round 4: no tenth fact — LIVE is what Qt reports when asked, and the frame is the witness
    assert "``LIVE``      else: G and E and R\n" in home and "What raises what" in home
    assert "The contract — three sentences" in home and "THE WITNESS IS A FRAME" in home
    assert "Which call is legal in which state" in home and "``wait_ready``" in home
    for path in CONTRACT_LINKERS:
        text = path.read_text(encoding="utf-8")
        where = path.relative_to(REPO).as_posix()
        assert "lifecycle.py" in text, f"{where} does not say where the contract is"
        copies = [match.group(0).strip() for match in STATE_ROW.finditer(text)]
        assert not copies, f"{where} carries a copy of the state table: {copies[:3]}"
        for phrase in CONTRACT_PHRASES:
            assert phrase not in text, f"{where} restates the contract: {phrase!r}"


@pytest.mark.parametrize(("line", "is_row"), [
    ("| `LIVE` | else: G and E and R | yes | yes |", True),
    ("  | `starting` | everything else | no |", True),
    ("``HIDDEN``    else: not (V and not M and A)", True),
    ("`SPENT`   the one offscreen frame was taken", True),
    ("`LIVE` also needs an area of at least 2 × 2 px.", False),
    ("| `lifecycle.py` | no | the host's state contract |", False),
    ("a host that reads `STARTING` until the next expose", False),
    ("| Field | From | Means |", False),
], ids=["markdown", "markdown lower", "rst", "rst single", "prose", "another table", "mid-line",
        "a header"])
def test_the_state_table_fingerprint_sees_a_copy_and_not_prose(line: str, is_row: bool) -> None:
    assert bool(STATE_ROW.search(line)) is is_row


# ── a child's settings are a test key (review round 3, the coordinator's rule) ──

# The child ASKS before it builds anything: with the developer's names it stops (exit 3).
_SETTINGS_CHILD = r'''
import os, sys
import sitecustomize
print("HOOK", sitecustomize.__file__)
print("APP_BEFORE", sorted(m for m in sys.modules if m.startswith(("open_garden_planner", "PyQt6"))))
import open_garden_planner.app.settings as settings
print("NAMES", settings.ORGANIZATION_NAME, "|", settings.APPLICATION_NAME, "|", os.getpid())
if settings.ORGANIZATION_NAME != "cofade_test" or "Test Child" not in settings.APPLICATION_NAME:
    sys.exit(3)
from open_garden_planner.app.settings import create_qsettings, get_settings
if len(sys.argv) > 1:  # the second child: what did the first one leave in ITS key?
    settings.APPLICATION_NAME = sys.argv[1]
    print("LEFT", get_settings().recent_files)
    sys.exit(0)
print("BUILT_BEFORE", len(sitecustomize.stores_built))
get_settings().add_recent_file("C:/nowhere/plan.ogp")  # what ProjectManager.load() ends with
store = create_qsettings()
print("STORE", store.organizationName(), "|", store.applicationName(), "|", get_settings().recent_files)
print("BUILT", len(sitecustomize.stores_built))
'''


def _settings_child(scratch: Path, *arguments: str, **extra: str) -> dict[str, str]:
    from tests.integration.quick3d_render_support import isolated_env

    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _SETTINGS_CHILD, *arguments],
        env=isolated_env(scratch, QT_QPA_PLATFORM="offscreen", **extra), capture_output=True,
        text=True, timeout=170, cwd=scratch)
    assert proc.returncode == 0, (
        f"exit {proc.returncode} (3: the child had the DEVELOPER's settings names and stopped "
        f"before building a store)\n{proc.stdout}\n{proc.stderr[-2000:]}")
    return dict(line.split(" ", 1) for line in proc.stdout.splitlines() if " " in line)


def test_every_child_environment_starts_with_the_settings_hook(tmp_path: Path) -> None:
    """The app's settings are a registry key on Windows; no environment variable moves it,
    and a child does not import ``tests/conftest.py``. ``isolated_env`` — the one source of
    every child's environment (the guard above) — puts a start-up hook first on the
    child's path. The hook itself imports nothing of the app and names no store."""
    from tests.integration import quick3d_render_support as support

    hook = support.CHILD_SITE / "sitecustomize.py"
    assert hook.is_file() and sorted(p.name for p in support.CHILD_SITE.glob("*.py")) == ["sitecustomize.py"]
    for build in (support.isolated_env, support.render_env):
        env = build(tmp_path)
        assert Path(env["PYTHONPATH"].split(os.pathsep)[0]) == support.CHILD_SITE, build
        assert env[support.ISOLATED_MARK] == "1"
    tree = ast.parse(hook.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom)}
    assert imported <= {"__future__", "atexit", "contextlib", "importlib", "os", "sys", "types",
                        "typing"}, f"the hook imports more than the standard library: {imported}"
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "QSettings" not in names, "only the factory in app/settings.py may name a store (§8.8)"


def test_a_child_that_imports_the_app_builds_its_stores_on_a_key_of_its_own(tmp_path: Path) -> None:
    """End to end, in a real child with the environment every child gets: nothing of the
    app is loaded by the hook; the moment the child imports the settings module the two
    names are a test key of that process; a store built then — and the Recent Files write
    a plan load ends with — lands there; and the key is empty again once the child is
    gone (asked by a second child, which looks into the first one's key)."""
    from tests.integration import quick3d_render_support as support

    report = tmp_path / "stores.txt"
    first = _settings_child(tmp_path, OGP_TEST_CHILD_STORES=str(report))
    assert Path(first["HOOK"]) == support.CHILD_SITE / "sitecustomize.py"
    assert first["APP_BEFORE"] == "[]", "the hook itself loads nothing of the app, and no Qt"
    organisation, application, pid = first["NAMES"].split(" | ")
    assert organisation == "cofade_test" and application == f"Open Garden Planner Test Child {pid}"
    assert first["BUILT_BEFORE"] == "0", "importing the settings module builds no store"
    assert first["STORE"] == f"cofade_test | {application} | ['C:/nowhere/plan.ogp']"
    assert int(first["BUILT"]) >= 1
    imported, built = report.read_text(encoding="utf-8").split()
    assert imported == "1" and int(built) == int(first["BUILT"])
    second = _settings_child(tmp_path, application)
    assert second["LEFT"] == "[]", "the first child's key was not emptied at its exit"
    assert second["NAMES"].split(" | ")[1] != application, "a key per process"


def test_the_driver_is_safe_when_it_is_run_by_hand(monkeypatch, tmp_path: Path) -> None:
    """The render driver loads a plan, and it is also started by hand to look at frames.
    Started through the tests it has the helper's environment (the mark says so) and
    changes nothing; without the mark it points the app's data directory into its own
    output directory itself — and in both cases it rebinds the settings names before
    anything of the app runs."""
    from tests.integration import quick3d_render_driver as driver
    from tests.integration import quick3d_render_support as support

    names = [name for name, _folder in support.PRIVATE_DIRS]
    for name in names:
        monkeypatch.setenv(name, str(tmp_path / "the-developers-own" / name))
    monkeypatch.setenv(support.ISOLATED_MARK, "1")
    driver._isolate_app_data(tmp_path / "out")  # noqa: SLF001
    assert all("the-developers-own" in os.environ[name] for name in names), "started isolated: untouched"
    monkeypatch.delenv(support.ISOLATED_MARK)
    driver._isolate_app_data(tmp_path / "out")  # noqa: SLF001
    for name in names:
        assert tmp_path / "out" / "private" in Path(os.environ[name]).parents, name
        assert Path(os.environ[name]).is_dir()
    # the order in main(): both isolations come before the first import of the engine
    tree = ast.parse(Path(driver.__file__).read_text(encoding="utf-8"))
    (main,) = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"]
    called = {ast.unparse(node.func): node.lineno for node in ast.walk(main)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    imports = [node.lineno for node in ast.walk(main)
               if isinstance(node, (ast.Import, ast.ImportFrom)) and "open_garden_planner" in ast.unparse(node)]
    assert called["_isolate_app_data"] < called["_isolate_settings"] < min(imports)
    finals = [ast.unparse(node) for node in ast.walk(main) if isinstance(node, ast.Try)
              for statement in node.finalbody for node in ast.walk(statement)
              if isinstance(node, ast.Call) and ast.unparse(node.func) == "_clear_settings"]
    assert finals == ["_clear_settings()"], "the driver's test key is emptied also after a failure"
