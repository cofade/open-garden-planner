#!/usr/bin/env python3
"""Repository metrics baseline for Open Garden Planner (dev-only, read-only).

Writes ONE JSON snapshot of measurable repository health so a later run can be diffed
against it: lines of code, complexity ranks (radon, optional), mypy error counts
(optional), ruff findings per directory (optional), layering violations (module-level
imports of ``ui``/``app``/``PyQt6.QtWidgets`` from the Qt-free layers), coverage per
package (from a ``coverage.xml`` you pass in), test counts, git churn (full history
only), repository hygiene files and documentation sizes.

Usage, from the repository root inside the dev venv::

    python scripts/audit_metrics.py --out metrics.json [--coverage-xml coverage.xml]
                                    [--no-git] [--no-mypy] [--no-ruff] [--no-radon]

Optional tools: ``radon`` (``pip install radon``) for complexity; ``mypy`` and ``ruff``
from the dev extras. A missing tool yields a ``null`` section with a reason, never a
crash. The script never modifies the repository. Timings depend on machine load, so the
snapshot records the load average alongside every tool run.

First produced for the 2026-10 repository audit (docs/11-risks-and-technical-debt/).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PACKAGE = "open_garden_planner"
QT_FREE_LAYERS = ("core", "services", "models", "agent_api")
FORBIDDEN_IMPORTS = (f"{PACKAGE}.ui", f"{PACKAGE}.app", "PyQt6.QtWidgets")
HYGIENE_FILES = (
    "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md", ".editorconfig",
    ".pre-commit-config.yaml", ".mailmap", ".github/CODEOWNERS", ".github/dependabot.yml",
    ".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
)


def run(cmd: list[str], cwd: Path, timeout: int = 600) -> tuple[int | None, str, str]:
    """Run a command; never raise. Returns (returncode or None, stdout, stderr)."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def load_average() -> list[float] | None:
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):  # Windows has no getloadavg
        return None


def py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


# --------------------------------------------------------------------------- sections


def loc_section(root: Path) -> dict[str, Any]:
    src = root / "src" / PACKAGE
    per_pkg: dict[str, int] = {}
    files_per_pkg: dict[str, int] = {}
    for path in py_files(src):
        rel = path.relative_to(src)
        pkg = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        per_pkg[pkg] = per_pkg.get(pkg, 0) + count_lines(path)
        files_per_pkg[pkg] = files_per_pkg.get(pkg, 0) + 1
    tests = py_files(root / "tests")
    scripts = py_files(root / "scripts")
    largest = sorted(((count_lines(p), str(p.relative_to(root))) for p in py_files(src)), reverse=True)
    return {
        "src_total": sum(per_pkg.values()),
        "src_files": sum(files_per_pkg.values()),
        "src_per_package": dict(sorted(per_pkg.items(), key=lambda kv: -kv[1])),
        "tests_total": sum(count_lines(p) for p in tests),
        "tests_files": len(tests),
        "scripts_total": sum(count_lines(p) for p in scripts),
        "largest_src_files": [{"path": p, "lines": n} for n, p in largest[:10]],
    }


def radon_section(root: Path) -> dict[str, Any] | None:
    rc, out, err = run([sys.executable, "-m", "radon", "cc", "-s", "-j", f"src/{PACKAGE}"], root)
    if rc != 0 or not out.strip():
        return {"available": False, "reason": (err or out).strip()[:300] or "radon not importable"}
    data = json.loads(out)
    ranks: Counter[str] = Counter()
    worst: list[tuple[int, str, str]] = []
    per_file_sum: dict[str, int] = {}
    for fname, items in data.items():
        if not isinstance(items, list):
            continue
        for it in items:
            # radon lists methods both nested under their class and as top-level "method" blocks, and
            # gives the class an aggregate complexity: count top-level functions/methods only.
            if it.get("type") not in ("function", "method"):
                continue
            ranks[it["rank"]] += 1
            per_file_sum[fname] = per_file_sum.get(fname, 0) + int(it["complexity"])
            name = f"{it['classname']}.{it['name']}" if it.get("classname") else it["name"]
            worst.append((int(it["complexity"]), fname, name))
    worst.sort(reverse=True)
    rc_mi, out_mi, _ = run([sys.executable, "-m", "radon", "mi", "-s", "-j", f"src/{PACKAGE}"], root)
    mi: dict[str, float] = {}
    if rc_mi == 0 and out_mi.strip():
        for fname, val in json.loads(out_mi).items():
            if isinstance(val, dict) and "mi" in val:
                mi[fname] = round(float(val["mi"]), 2)
    return {
        "available": True,
        "rank_histogram": dict(sorted(ranks.items())),
        "functions_rank_d_or_worse": sum(v for k, v in ranks.items() if k in ("D", "E", "F")),
        "top_30_by_cc": [{"cc": c, "path": f, "name": n} for c, f, n in worst[:30]],
        "files_with_mi_below_10": sorted(f for f, v in mi.items() if v < 10),
        "sum_cc_top_10_files": [
            {"path": f, "sum_cc": s} for f, s in sorted(per_file_sum.items(), key=lambda kv: -kv[1])[:10]
        ],
    }


def mypy_section(root: Path) -> dict[str, Any] | None:
    t0 = time.monotonic()
    rc, out, err = run([sys.executable, "-m", "mypy", f"src/{PACKAGE}"], root, timeout=1800)
    if rc is None or (rc not in (0, 1)):
        return {"available": False, "reason": (err or out).strip()[:300]}
    m = re.search(r"Found (\d+) errors? in (\d+) files?", out)
    per_pkg: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    for line in out.splitlines():
        if ": error:" not in line:
            continue
        pm = re.match(rf"src/{PACKAGE}/([A-Za-z_0-9]+)", line.replace("\\", "/"))
        per_pkg[pm.group(1) if pm else "(root)"] += 1
        cm = re.search(r"\[([a-z-]+)\]\s*$", line)
        if cm:
            codes[cm.group(1)] += 1
    return {
        "available": True,
        "errors": int(m.group(1)) if m else 0,
        "files_with_errors": int(m.group(2)) if m else 0,
        "per_package": dict(per_pkg.most_common()),
        "top_error_codes": dict(codes.most_common(10)),
        "unused_type_ignores": codes.get("unused-ignore", 0),
        "seconds": round(time.monotonic() - t0, 1),
    }


def ruff_section(root: Path) -> dict[str, Any] | None:
    result: dict[str, Any] = {"available": True, "check": {}, "format_would_reformat": {}}
    for target in ("src", "tests", "scripts"):
        if not (root / target).exists():
            continue
        rc, out, err = run([sys.executable, "-m", "ruff", "check", target, "--output-format", "json"], root)
        if rc is None or rc not in (0, 1) or not out.strip().startswith("["):
            return {"available": False, "reason": (err or out).strip()[:300] or "ruff not importable"}
        items = json.loads(out)
        rules = Counter(i.get("code") for i in items)
        result["check"][target] = {"findings": len(items), "top_rules": dict(rules.most_common(8))}
        rc_f, out_f, err_f = run([sys.executable, "-m", "ruff", "format", "--check", target], root)
        text = out_f + "\n" + err_f
        summary = re.search(r"(\d+) files? would be reformatted", text)
        if summary:
            would = int(summary.group(1))
        else:  # older ruff: one "Would reformat: path" line per file; newer: "unformatted:" blocks
            would = sum(1 for line in text.splitlines() if line.startswith(("Would reformat", "unformatted:")))
        result["format_would_reformat"][target] = would if rc_f in (0, 1) else None
    return result


def layering_section(root: Path) -> dict[str, Any]:
    """Module-level imports that cross the declared layer boundary.

    Rule (architecture contract, invariant 11): ``core``, ``services``, ``models`` and
    ``agent_api`` must not import ``open_garden_planner.ui`` or ``.app`` at MODULE level;
    function-local imports are the sanctioned cycle-avoidance device. ``PyQt6.QtWidgets``
    imports from those layers are reported separately as information only (the contract
    does not forbid Qt in ``core``; the audit uses the number to size a possible Qt-free core).
    """
    src = root / "src" / PACKAGE
    ui_app = (f"{PACKAGE}.ui", f"{PACKAGE}.app")
    module_level: list[dict[str, Any]] = []
    qt_module_level: Counter[str] = Counter()
    nested_counts: Counter[str] = Counter()
    for layer in QT_FREE_LAYERS:
        for path in py_files(src / layer):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    targets = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    targets = [node.module or ""]
                else:
                    continue
                hits_ui = [x for x in targets if any(x == f or x.startswith(f + ".") for f in ui_app)]
                hits_qt = [x for x in targets if x == "PyQt6.QtWidgets" or x.startswith("PyQt6.QtWidgets.")]
                at_top = node.col_offset == 0
                rel = str(path.relative_to(root)).replace("\\", "/")
                if hits_ui and at_top:
                    module_level.append({"path": rel, "line": node.lineno, "imports": hits_ui})
                elif hits_ui:
                    nested_counts[layer] += 1
                if hits_qt and at_top:
                    qt_module_level[layer] += 1
    per_layer = Counter(v["path"].split("/")[2] for v in module_level)
    return {
        "rule": "no module-level imports of open_garden_planner.ui/.app from core, services, models, "
                "agent_api (architecture invariant 11; function-local imports are allowed)",
        "module_level_violations_total": len(module_level),
        "module_level_per_layer": dict(per_layer),
        "module_level_violations": module_level[:50],
        "function_local_ui_app_imports_per_layer": dict(nested_counts),
        "module_level_qtwidgets_imports_per_layer_informational": dict(qt_module_level),
    }


def coverage_section(xml_path: Path | None) -> dict[str, Any] | None:
    if xml_path is None:
        return None
    if not xml_path.exists():
        return {"available": False, "reason": f"{xml_path} not found"}
    tree = ET.parse(xml_path)
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    files: list[tuple[int, int, str]] = []
    for cls in tree.getroot().iter("class"):
        fname = (cls.get("filename") or "").replace("\\", "/")
        parts = fname.split("/")
        pkg = parts[2] if len(parts) > 3 and parts[1] == PACKAGE else "(other)"
        lines = cls.findall("lines/line")
        valid, covered = len(lines), sum(1 for ln in lines if ln.get("hits") != "0")
        bv = bc = 0
        for ln in lines:
            cond = ln.get("condition-coverage") or ""
            if ln.get("branch") == "true" and "(" in cond:
                a, b = cond[cond.index("(") + 1:cond.index(")")].split("/")
                bc += int(a)
                bv += int(b)
        for i, v in enumerate((valid, covered, bv, bc)):
            agg[pkg][i] += v
        files.append((valid - covered, valid, fname))

    def pct(a: int, b: int) -> float | None:
        return round(100 * a / b, 1) if b else None

    per_pkg = {k: {"statements": v[0], "line_pct": pct(v[1], v[0]), "branch_pct": pct(v[3], v[2])}
               for k, v in sorted(agg.items(), key=lambda kv: -kv[1][0])}
    tot = [sum(v[i] for v in agg.values()) for i in range(4)]
    non_ui = [sum(v[i] for k, v in agg.items() if k != "ui") for i in range(4)]
    files.sort(reverse=True)
    return {
        "available": True,
        "source": xml_path.name,  # basename only: a snapshot must not record local paths
        "total": {"statements": tot[0], "line_pct": pct(tot[1], tot[0]), "branch_pct": pct(tot[3], tot[2])},
        "non_ui": {"statements": non_ui[0], "line_pct": pct(non_ui[1], non_ui[0]),
                   "branch_pct": pct(non_ui[3], non_ui[2]), "definition": "all packages except ui"},
        "per_package": per_pkg,
        "least_covered_large_files": [
            {"path": f, "statements": v, "missed": m} for m, v, f in files if v >= 150
        ][:10],
    }


def tests_section(root: Path) -> dict[str, Any]:
    per_dir: dict[str, dict[str, int]] = {}
    total = 0
    for path in py_files(root / "tests"):
        if not path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        n = sum(1 for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_"))
        rel = path.relative_to(root / "tests")
        sub = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        d = per_dir.setdefault(sub, {"files": 0, "test_functions": 0})
        d["files"] += 1
        d["test_functions"] += n
        total += n
    return {"test_functions_total": total, "per_directory": per_dir,
            "note": "test functions, not parametrised cases; pytest --collect-only counts cases"}


def git_section(root: Path) -> dict[str, Any] | None:
    rc, out, _ = run(["git", "rev-parse", "--is-shallow-repository"], root)
    if rc != 0:
        return {"available": False, "reason": "git not available or not a repository"}
    if out.strip() == "true":
        return {"available": False, "reason": "shallow clone: churn needs the full history (git fetch --unshallow)"}
    rc, log, _ = run(["git", "log", "--format=%H%x09%an%x09%s", "--name-only", "--", "src"], root, timeout=300)
    if rc != 0:
        return {"available": False, "reason": "git log failed"}
    churn: Counter[str] = Counter()
    for line in log.splitlines():
        if line.endswith(".py") and "\t" not in line:
            churn[line] += 1
    _, count, _ = run(["git", "rev-list", "--count", "HEAD"], root)
    _, subjects, _ = run(["git", "log", "--format=%s"], root, timeout=300)
    subj = subjects.splitlines()
    types = Counter((re.match(r"^([a-z]+)", s) or re.match(r"(.*)", "other")).group(1) for s in subj)
    _, authors, _ = run(["git", "shortlog", "-sn", "--no-merges", "HEAD"], root, timeout=300)
    return {
        "available": True,
        "commits": int(count.strip() or 0),
        "commit_type_histogram": dict(types.most_common(8)),
        "version_sync_commits": sum(1 for s in subj if s.startswith("chore: sync version")),
        "author_identities": len([ln for ln in authors.splitlines() if ln.strip()]),
        "churn_top_20": [{"path": p, "commits": n} for p, n in churn.most_common(20)],
    }


def hygiene_section(root: Path) -> dict[str, Any]:
    present = {f: (root / f).exists() for f in HYGIENE_FILES}
    claude = root / "CLAUDE.md"
    agents = root / "AGENTS.md"
    skills = sorted((root / ".claude" / "skills").glob("*/SKILL.md"))
    return {
        "standard_files": present,
        "claude_md_bytes": claude.stat().st_size if claude.exists() else None,
        "agents_md_bytes": agents.stat().st_size if agents.exists() else None,
        "claude_agents_identical": (claude.read_bytes() == agents.read_bytes())
        if claude.exists() and agents.exists() else None,
        "skills": len(skills),
        "skills_total_bytes": sum(p.stat().st_size for p in skills),
        "largest_skills": sorted(
            ({"path": str(p.relative_to(root)), "bytes": p.stat().st_size} for p in skills),
            key=lambda d: -d["bytes"])[:5],
    }


def docs_section(root: Path) -> dict[str, Any]:
    docs = sorted(((count_lines(p), str(p.relative_to(root))) for p in (root / "docs").rglob("*.md")),
                  reverse=True)
    return {"markdown_files": len(docs), "largest": [{"path": p, "lines": n} for n, p in docs[:8]]}


# --------------------------------------------------------------------------- main


def build(root: Path, coverage_xml: Path | None, *, git: bool, mypy: bool, ruff: bool, radon: bool,
          ) -> dict[str, Any]:
    _, head, _ = run(["git", "rev-parse", "--short", "HEAD"], root)
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": head.strip() or None,
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "load_average_start": load_average(),
            "disabled": [k for k, v in (("git", git), ("mypy", mypy), ("ruff", ruff), ("radon", radon)) if not v],
        },
        "loc": loc_section(root),
        "complexity": radon_section(root) if radon else None,
        "types": mypy_section(root) if mypy else None,
        "lint": ruff_section(root) if ruff else None,
        "layering": layering_section(root),
        "coverage": coverage_section(coverage_xml),
        "tests": tests_section(root),
        "git": git_section(root) if git else None,
        "hygiene": hygiene_section(root),
        "docs": docs_section(root),
    }
    snapshot["meta"]["load_average_end"] = load_average()
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: cwd)")
    parser.add_argument("--out", type=Path, required=True, help="output JSON path")
    parser.add_argument("--coverage-xml", type=Path, default=None, help="coverage.xml from pytest --cov")
    parser.add_argument("--no-git", action="store_true")
    parser.add_argument("--no-mypy", action="store_true")
    parser.add_argument("--no-ruff", action="store_true")
    parser.add_argument("--no-radon", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / "src" / PACKAGE).is_dir():
        print(f"error: {root} does not look like the repository root (no src/{PACKAGE})", file=sys.stderr)
        return 2
    snap = build(root, args.coverage_xml, git=not args.no_git, mypy=not args.no_mypy,
                 ruff=not args.no_ruff, radon=not args.no_radon)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    loc, lay = snap["loc"], snap["layering"]
    types = snap["types"] or {}
    cov = snap["coverage"] or {}
    print(f"wrote {args.out}: src {loc['src_total']} LOC in {loc['src_files']} files; "
          f"tests {snap['tests']['test_functions_total']} functions; "
          f"module-level layering violations {lay['module_level_violations_total']}; "
          f"mypy errors {types.get('errors', 'n/a')}; "
          f"coverage non-UI {(cov.get('non_ui') or {}).get('line_pct', 'n/a')}% lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
