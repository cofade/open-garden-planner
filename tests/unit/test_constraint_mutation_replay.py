"""A control timeout is a reported experiment failure, not a traceback (#457)."""

import json
import subprocess

from scripts import replay_constraint_mutations as replay


def test_control_timeout_saves_report_and_returns_failure(monkeypatch, tmp_path, capsys):
    output = tmp_path / "report.json"
    monkeypatch.setattr(replay.sys, "argv", ["replay", "--output", str(output)])

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 45)

    monkeypatch.setattr(replay.subprocess, "run", timeout)
    assert replay.main() == 1
    assert "Control timeout" in capsys.readouterr().out
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["control"]["status"] == "timeout"
    assert report["results"] == []
