"""Action-pin drift gate (AUD-053): externals must be commit-pinned with a version comment."""

from pathlib import Path

from scripts.check_action_pins import _violations_in, main

ROOT = Path(__file__).resolve().parents[2]
SHA = "11d5960a326750d5838078e36cf38b85af677262"


def test_pinned_reference_is_accepted() -> None:
    text = f"      - uses: actions/checkout@{SHA} # v4.4.0\n"
    assert _violations_in(text) == []


def test_local_and_docker_references_are_allowed() -> None:
    text = (
        "      - uses: ./.github/actions/setup-locked-env\n"
        "      - uses: docker://alpine:3\n"
    )
    assert _violations_in(text) == []


def test_mutable_tag_is_rejected() -> None:
    found = _violations_in("      - uses: actions/checkout@v4\n")
    assert found and found[0][1] == "actions/checkout@v4"


def test_sha_without_version_comment_is_rejected() -> None:
    found = _violations_in(f"      - uses: actions/checkout@{SHA}\n")
    assert found and "comment" in found[0][2]


def test_non_sha_pin_is_rejected() -> None:
    found = _violations_in("      - uses: actions/checkout@v4.4.0 # v4.4.0\n")
    assert found and "40-hex" in found[0][2]


def test_missing_at_and_empty_repo_are_rejected() -> None:
    assert _violations_in("      - uses: actions/checkout\n")
    assert _violations_in("      - uses: @v4.4.0 # v4.4.0\n")


def test_inline_step_form_is_checked_too() -> None:
    found = _violations_in("    - uses: actions/upload-artifact@v4\n")
    assert found and found[0][0] == 1


def test_flow_style_step_is_checked_too() -> None:
    found = _violations_in("      - {name: Checkout, uses: actions/checkout@v4}\n")
    assert found and found[0][1] == "actions/checkout@v4"
    pinned = _violations_in(f"      - {{name: Checkout, uses: actions/checkout@{SHA}}}}} # v4.4.0\n")
    assert pinned == []


def test_yaml_workflows_are_discovered(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "flow.yaml").write_text(
        "jobs:\n  x:\n    steps:\n      - uses: actions/checkout@v4\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 2


def test_real_repository_passes_the_gate() -> None:
    assert main(["--root", str(ROOT)]) == 0


def test_real_workflows_contain_no_mutable_action_tags() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    assert "actions/checkout@v" not in text
    assert "actions/setup-python@v" not in text
    assert "actions/upload-artifact@v" not in text
    assert "actions/attest-build-provenance@v" not in text


def test_gate_fails_on_a_fixture_tree(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bad.yml").write_text(
        "jobs:\n  x:\n    steps:\n      - uses: actions/checkout@v4\n", encoding="utf-8"
    )
    assert main(["--root", str(tmp_path)]) == 2
