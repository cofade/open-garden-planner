"""Dependency governance gates: locked scan, monthly fallback, caps, SBOM release wiring."""

import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
RELEASE = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
REVIEW = (ROOT / ".github/workflows/dependency-review.yml").read_text(encoding="utf-8")


def _requirement(name: str) -> Requirement:
    for raw in PYPROJECT["project"]["dependencies"]:
        requirement = Requirement(raw)
        if requirement.name.lower() == name.lower():
            return requirement
    raise AssertionError(f"{name} is not a runtime dependency")


def test_ci_audits_the_locked_closure_on_every_shipped_platform() -> None:
    assert "pip-audit" in CI
    assert "--ignore-vuln PYSEC-2026-3447" in CI, (
        "the one build-time exception must be named explicitly, not by disabling the scan"
    )
    assert "uv export --locked --all-extras --group build" in CI, (
        "the audit must run against the committed lock export, not installed state"
    )
    dependencies_job = CI.split("  dependencies:", 1)[1].split("\n  types:", 1)[0]
    assert "pip-audit" in dependencies_job, (
        "the audit belongs in the two-OS matrix job: pip-audit evaluates markers for the "
        "running platform, so a Linux-only scan never sees the Windows-only runtime "
        "dependency (pywin32)"
    )
    assert "os: [ubuntu-latest, windows-latest]" in dependencies_job
    assert "shell: bash" in dependencies_job, (
        "the Windows runner needs bash so the export redirection stays UTF-8"
    )
    docs = (ROOT / "docs/11-risks-and-technical-debt/README.md").read_text(encoding="utf-8")
    assert "PYSEC-2026-3447" in docs or "GHSA-h35f-9h28-mq5c" in docs, (
        "the exception must stay justified in the risk register"
    )


def test_pip_audit_is_part_of_the_locked_dev_environment() -> None:
    dev = PYPROJECT["project"]["optional-dependencies"]["dev"]
    assert any(Requirement(raw).name.lower() == "pip-audit" for raw in dev)


def test_the_qt_four_pack_moves_as_one_and_mcp_stays_on_v1() -> None:
    qt = {name: _requirement(name) for name in ("PyQt6", "PyQt6-Qt6", "PyQt6-3D", "PyQt6-3D-Qt6")}
    versions = {str(r.specifier) for r in qt.values()}
    assert len(versions) == 1 and versions.pop().startswith("==6.11.0"), (
        "all four Qt wheels must pin the SAME micro or the frozen 3D import breaks (#277)"
    )
    webengine = _requirement("PyQt6-WebEngine")
    assert "<6.11" in str(webengine.specifier)
    mcp = _requirement("mcp")
    assert "<2.0" in str(mcp.specifier) and ">=1.23" in str(mcp.specifier)


def test_release_publishes_and_attests_the_inventory() -> None:
    assert "dist/ogp-sbom.cdx.json" in RELEASE
    assert "dist/THIRD_PARTY_NOTICES.md" in RELEASE
    subject_block = RELEASE.split("subject-path:", 1)[1]
    assert "ogp-sbom.cdx.json" in subject_block and "THIRD_PARTY_NOTICES.md" in subject_block, (
        "provenance must cover the inventory the release publishes"
    )
    assert "dist/build-evidence.json" in RELEASE


def test_the_monthly_review_never_writes_without_review() -> None:
    assert "schedule:" in REVIEW and "workflow_dispatch:" in REVIEW
    assert "uv lock --upgrade --dry-run" in REVIEW, (
        "--dry-run is the mechanical guarantee that the schedule cannot write the lock"
    )
    assert "if ! uv lock --upgrade --dry-run" in REVIEW, (
        "a failed dry run must fail the workflow; a silent 'up to date' is a lying gate"
    )
    assert "|| true" not in REVIEW
    assert "grep -q '^Resolved '" in REVIEW, (
        "an unrecognized uv output shape must fail loudly, not report 'no updates'"
    )
    assert "grep -q '^Update '" in REVIEW, (
        "the report parses this literal; if a uv bump renames it, the marker guard must "
        "catch it rather than reporting 'no updates'"
    )
    assert "git diff --exit-code -- uv.lock" in REVIEW, (
        "the workflow must verify the dry run really wrote nothing"
    )
    for forbidden in ("git push", "gh pr create", "gh pr merge", "--admin", "git commit"):
        assert forbidden not in REVIEW, f"the monthly review must not {forbidden!r}"
    assert "issues: write" in REVIEW


def test_dependency_update_runbook_is_documented() -> None:
    deployment = (ROOT / "docs/07-deployment-view/README.md").read_text(encoding="utf-8")
    assert "Dependency update" in deployment or "dependency update" in deployment
    assert "dependency-review.yml" in deployment
