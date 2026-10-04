#!/usr/bin/env python3
"""Repository metrics baseline for Open Garden Planner (dev-only, read-only).

Writes ONE JSON snapshot of measurable repository health so a later run can be diffed
against it: lines of code, complexity ranks (radon, optional), mypy error counts
(optional), ruff findings per directory (optional), layering (imports of ``ui``/``app``
from the lower layers, classified by scope), coverage per package (from a
``coverage.xml`` you pass in), test counts, git churn (full history only), repository
hygiene files and documentation sizes.

Usage, from the repository root inside the dev venv::

    python scripts/audit_metrics.py --out metrics.json [--coverage-xml coverage.xml]
                                    [--no-git] [--no-mypy] [--no-ruff] [--no-radon]

``--coverage-xml`` accepts the XML of either invocation, ``pytest --cov`` (the project's
``[tool.coverage.run] source``, filenames relative to the package) or
``pytest --cov=open_garden_planner`` (filenames under ``src/``); files that resolve to
neither make the coverage section unavailable rather than wrong.

Optional tools: ``radon`` (``pip install radon``) for complexity; ``mypy`` and ``ruff``
from the dev extras. A tool that is missing or whose output cannot be parsed yields
``{"available": false, "reason": ...}``, never a crash and never a zero; a section
disabled with ``--no-*`` is ``null``. The script never modifies the repository. Tool
versions, the load average at start and end, and whether the tree was dirty are recorded
in ``meta``: mypy counts depend on the mypy version, coverage on test order and timing.

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

SCHEMA_VERSION = 2
PACKAGE = "open_garden_planner"
LOWER_LAYERS = ("core", "services", "models", "agent_api")
UI_APP = (f"{PACKAGE}.ui", f"{PACKAGE}.app")
QT_WIDGETS = "PyQt6.QtWidgets"
#: Share of coverage statements allowed outside the package before the section fails closed.
COVERAGE_OTHER_TOLERANCE = 0.01
HYGIENE_FILES = (
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    ".editorconfig",
    ".pre-commit-config.yaml",
    ".mailmap",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/pull_request_template.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)


def run(cmd: list[str], cwd: Path, timeout: int = 600) -> tuple[int | None, str, str]:
    """Run a command; never raise. Returns (returncode or None, stdout, stderr)."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def reason(text: str, fallback: str) -> str:
    """A degradation reason without local paths (a snapshot must not record them)."""
    cleaned = (text or "").strip().replace(sys.executable, "python")
    cleaned = cleaned.replace(str(Path.cwd()), ".")
    return cleaned[:300] or fallback


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


def rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def parse_python(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def tool_version(module: str, root: Path) -> str | None:
    rc, out, _ = run([sys.executable, "-m", module, "--version"], root, timeout=60)
    return out.strip().splitlines()[0][:80] if rc == 0 and out.strip() else None


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
    largest = sorted(((count_lines(p), rel_posix(p, root)) for p in py_files(src)), reverse=True)
    return {
        "src_total": sum(per_pkg.values()),
        "src_files": sum(files_per_pkg.values()),
        "src_per_package": dict(sorted(per_pkg.items(), key=lambda kv: -kv[1])),
        "tests_total": sum(count_lines(p) for p in tests),
        "tests_files": len(tests),
        "scripts_total": sum(count_lines(p) for p in scripts),
        "largest_src_files": [{"path": p, "lines": n} for n, p in largest[:10]],
    }


def radon_section(root: Path) -> dict[str, Any]:
    rc, out, err = run([sys.executable, "-m", "radon", "cc", "-s", "-j", f"src/{PACKAGE}"], root)
    try:
        data = json.loads(out) if rc == 0 else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return {"available": False, "reason": reason(err or out, "radon not importable")}
    ranks: Counter[str] = Counter()
    worst: list[tuple[int, str, str]] = []
    per_file_sum: dict[str, int] = {}
    for fname, items in data.items():
        if not isinstance(items, list):
            continue
        path = fname.replace("\\", "/")
        for it in items:
            # radon lists methods both nested under their class and as top-level "method"
            # blocks, and gives the class an aggregate: count top-level functions/methods once.
            if it.get("type") not in ("function", "method"):
                continue
            ranks[it["rank"]] += 1
            per_file_sum[path] = per_file_sum.get(path, 0) + int(it["complexity"])
            name = f"{it['classname']}.{it['name']}" if it.get("classname") else it["name"]
            worst.append((int(it["complexity"]), path, name))
    worst.sort(reverse=True)
    rc_mi, out_mi, _ = run(
        [sys.executable, "-m", "radon", "mi", "-s", "-j", f"src/{PACKAGE}"], root
    )
    mi: dict[str, float] = {}
    try:
        mi_data = json.loads(out_mi) if rc_mi == 0 else {}
    except json.JSONDecodeError:
        mi_data = {}
    for fname, val in mi_data.items():
        if isinstance(val, dict) and "mi" in val:
            mi[fname.replace("\\", "/")] = round(float(val["mi"]), 2)
    top_files = sorted(per_file_sum.items(), key=lambda kv: -kv[1])[:10]
    return {
        "available": True,
        "rank_histogram": dict(sorted(ranks.items())),
        "functions_rank_d_or_worse": sum(v for k, v in ranks.items() if k in ("D", "E", "F")),
        "top_30_by_cc": [{"cc": c, "path": f, "name": n} for c, f, n in worst[:30]],
        "files_with_mi_below_10": sorted(f for f, v in mi.items() if v < 10),
        "sum_cc_top_10_files": [{"path": f, "sum_cc": s} for f, s in top_files],
    }


_MYPY_FOUND = re.compile(r"Found (\d+) errors? in (\d+) files?")
_MYPY_SUCCESS = re.compile(r"Success: no issues found")


def parse_mypy(rc: int | None, out: str, err: str) -> dict[str, Any]:
    """Parse mypy output. Exit code 1 is ALSO what a missing mypy returns, so only a
    summary line ("Found N errors in M files" / "Success: no issues found") counts."""
    found = _MYPY_FOUND.search(out)
    if rc not in (0, 1) or not (found or _MYPY_SUCCESS.search(out)):
        return {"available": False, "reason": reason(err or out, "mypy produced no summary")}
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
        "errors": int(found.group(1)) if found else 0,
        "files_with_errors": int(found.group(2)) if found else 0,
        "per_package": dict(per_pkg.most_common()),
        "top_error_codes": dict(codes.most_common(10)),
        "unused_type_ignores": codes.get("unused-ignore", 0),
    }


def mypy_section(root: Path) -> dict[str, Any]:
    t0 = time.monotonic()
    result = parse_mypy(*run([sys.executable, "-m", "mypy", f"src/{PACKAGE}"], root, timeout=1800))
    if result["available"]:
        result["seconds"] = round(time.monotonic() - t0, 1)
    return result


def ruff_section(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"available": True, "check": {}, "format_would_reformat": {}}
    for target in ("src", "tests", "scripts"):
        if not (root / target).exists():
            continue
        cmd = [sys.executable, "-m", "ruff", "check", target, "--output-format", "json"]
        rc, out, err = run(cmd, root)
        try:
            items = json.loads(out) if rc in (0, 1) else None
        except json.JSONDecodeError:
            items = None
        if not isinstance(items, list):
            return {"available": False, "reason": reason(err or out, "ruff not importable")}
        rules = Counter(i.get("code") for i in items)
        result["check"][target] = {"findings": len(items), "top_rules": dict(rules.most_common(8))}
        rc_f, out_f, err_f = run([sys.executable, "-m", "ruff", "format", "--check", target], root)
        text = out_f + "\n" + err_f
        summary = re.search(r"(\d+) files? would be reformatted", text)
        if summary:
            would = int(summary.group(1))
        else:  # older ruff: one "Would reformat: path" line per file
            prefixes = ("Would reformat", "unformatted:")
            would = sum(1 for line in text.splitlines() if line.startswith(prefixes))
        result["format_would_reformat"][target] = would if rc_f in (0, 1) else None
    return result


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def classify_imports(tree: ast.AST) -> list[tuple[ast.Import | ast.ImportFrom, str]]:
    """Every import with its scope: ``module`` (runs at import time, including inside a
    module-level ``try``/``if`` or class body), ``function_local`` (inside a def or
    lambda) or ``type_checking`` (inside a module-level ``if TYPE_CHECKING:``)."""
    found: list[tuple[ast.Import | ast.ImportFrom, str]] = []

    def visit(node: ast.AST, scope: str) -> None:
        if isinstance(node, ast.Import | ast.ImportFrom):
            found.append((node, scope))
            return
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            for child in ast.iter_child_nodes(node):
                visit(child, "function_local")
            return
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for stmt in node.body:
                visit(stmt, "type_checking" if scope == "module" else scope)
            for stmt in node.orelse:
                visit(stmt, scope)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, "module")
    return found


def _import_targets(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    return [node.module or ""]


def _matches(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def layering_section(root: Path) -> dict[str, Any]:
    """Imports of ``open_garden_planner.ui``/``.app`` from the lower layers, by scope.

    A module-level ``core -> ui`` import breaks architecture-contract invariant 11; a
    module-level ``app`` import from a lower layer contradicts the module map (``app`` is
    the top layer). Function-local imports are the sanctioned cycle-avoidance device
    (invariant 11) and ``TYPE_CHECKING`` imports never execute, so both are counted, not
    flagged. Module-level ``PyQt6.QtWidgets`` imports are information only.
    """
    src = root / "src" / PACKAGE
    module_level: list[dict[str, Any]] = []
    per_scope: dict[str, Counter[str]] = {"function_local": Counter(), "type_checking": Counter()}
    qt_module_level: Counter[str] = Counter()
    unparsed: list[str] = []
    for layer in LOWER_LAYERS:
        for path in py_files(src / layer):
            tree = parse_python(path)
            if tree is None:
                unparsed.append(rel_posix(path, root))
                continue
            for node, scope in classify_imports(tree):
                targets = _import_targets(node)
                hits = [t for t in targets if _matches(t, UI_APP)]
                if hits and scope == "module":
                    module_level.append(
                        {"path": rel_posix(path, root), "line": node.lineno, "imports": hits}
                    )
                elif hits:
                    per_scope[scope][layer] += 1
                if scope == "module" and any(_matches(t, (QT_WIDGETS,)) for t in targets):
                    qt_module_level[layer] += 1
    per_layer = Counter(v["path"].split("/")[2] for v in module_level)
    return {
        "rule": (
            "module-level imports of open_garden_planner.ui/.app from core, services, models, "
            "agent_api: core->ui breaks architecture invariant 11, ->app contradicts the module "
            "map; function-local (invariant 11) and TYPE_CHECKING imports are counted, not flagged"
        ),
        "module_level_violations_total": len(module_level),
        "module_level_per_layer": dict(per_layer),
        "module_level_violations": module_level[:50],
        "function_local_ui_app_imports_per_layer": dict(per_scope["function_local"]),
        "type_checking_ui_app_imports_per_layer": dict(per_scope["type_checking"]),
        "module_level_qtwidgets_imports_per_layer_informational": dict(qt_module_level),
        "unparsed_files": unparsed,
    }


def _package_relative(filename: str, sources: list[str]) -> str | None:
    """``core/x.py`` for any coverage filename that resolves into the package, else None."""
    marker = f"{PACKAGE}/"
    for candidate in [filename] + [f"{s.rstrip('/')}/{filename}" for s in sources]:
        norm = candidate.replace("\\", "/")
        if norm.startswith(marker):
            return norm[len(marker) :]
        idx = norm.find("/" + marker)
        if idx >= 0:
            return norm[idx + 1 + len(marker) :]
    return None


def coverage_section(xml_path: Path | None) -> dict[str, Any] | None:
    if xml_path is None:
        return None
    if not xml_path.exists():
        return {"available": False, "reason": f"{xml_path.name} not found"}
    try:
        tree = ET.parse(xml_path)  # noqa: S314 - a coverage.xml the caller produced
    except ET.ParseError as exc:
        return {"available": False, "reason": f"{xml_path.name}: {exc}"}
    sources = [s.text or "" for s in tree.getroot().iter("source")]
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    files: list[tuple[int, int, str]] = []
    other_statements = 0
    for cls in tree.getroot().iter("class"):
        rel = _package_relative(cls.get("filename") or "", sources)
        lines = cls.findall("lines/line")
        valid, covered = len(lines), sum(1 for ln in lines if ln.get("hits") != "0")
        if rel is None:
            other_statements += valid
            continue
        parts = rel.split("/")
        pkg = parts[0] if len(parts) > 1 else "(root)"
        bv = bc = 0
        for ln in lines:
            cond = ln.get("condition-coverage") or ""
            if ln.get("branch") == "true" and "(" in cond:
                a, b = cond[cond.index("(") + 1 : cond.index(")")].split("/")
                bc += int(a)
                bv += int(b)
        for i, v in enumerate((valid, covered, bv, bc)):
            agg[pkg][i] += v
        files.append((valid - covered, valid, f"src/{PACKAGE}/{rel}"))
    in_package = sum(v[0] for v in agg.values())
    if in_package == 0 or other_statements > COVERAGE_OTHER_TOLERANCE * (
        in_package + other_statements
    ):
        return {
            "available": False,
            "reason": (
                f"{other_statements} of {in_package + other_statements} statements do not resolve "
                f"into src/{PACKAGE}: unrecognised coverage.xml layout"
            ),
        }

    def pct(a: int, b: int) -> float | None:
        return round(100 * a / b, 1) if b else None

    def summary(v: list[int]) -> dict[str, Any]:
        return {"statements": v[0], "line_pct": pct(v[1], v[0]), "branch_pct": pct(v[3], v[2])}

    per_pkg = {k: summary(v) for k, v in sorted(agg.items(), key=lambda kv: -kv[1][0])}
    tot = [sum(v[i] for v in agg.values()) for i in range(4)]
    non_ui = [sum(v[i] for k, v in agg.items() if k != "ui") for i in range(4)]
    files.sort(reverse=True)
    return {
        "available": True,
        "source": xml_path.name,  # basename only: a snapshot must not record local paths
        "total": summary(tot),
        "non_ui": {**summary(non_ui), "definition": "all packages except ui"},
        "per_package": per_pkg,
        "least_covered_large_files": [
            {"path": f, "statements": v, "missed": m} for m, v, f in files if v >= 150
        ][:10],
    }


def tests_section(root: Path) -> dict[str, Any]:
    per_dir: dict[str, dict[str, int]] = {}
    total = 0
    unparsed: list[str] = []
    for path in py_files(root / "tests"):
        if not path.name.startswith("test_"):
            continue
        tree = parse_python(path)
        if tree is None:
            unparsed.append(rel_posix(path, root))
            continue
        n = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
        )
        rel = path.relative_to(root / "tests")
        sub = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        d = per_dir.setdefault(sub, {"files": 0, "test_functions": 0})
        d["files"] += 1
        d["test_functions"] += n
        total += n
    return {
        "test_functions_total": total,
        "per_directory": per_dir,
        "unparsed_files": unparsed,
        "note": "test functions, not parametrised cases; pytest --collect-only counts cases",
    }


def git_section(root: Path) -> dict[str, Any]:
    rc, out, _ = run(["git", "rev-parse", "--is-shallow-repository"], root)
    if rc != 0:
        return {"available": False, "reason": "git not available or not a repository"}
    if out.strip() == "true":
        return {
            "available": False,
            "reason": "shallow clone: churn needs the full history (git fetch --unshallow)",
        }
    log_cmd = ["git", "log", "--format=%H%x09%an%x09%s", "--name-only", "--", "src"]
    rc, log, _ = run(log_cmd, root, timeout=300)
    if rc != 0:
        return {"available": False, "reason": "git log failed"}
    churn: Counter[str] = Counter()
    for line in log.splitlines():
        if line.endswith(".py") and "\t" not in line:
            churn[line] += 1
    _, count, _ = run(["git", "rev-list", "--count", "HEAD"], root)
    _, subjects, _ = run(["git", "log", "--format=%s"], root, timeout=300)
    subj = [s.lstrip("﻿") for s in subjects.splitlines()]
    types: Counter[str] = Counter()
    for s in subj:
        m = re.match(r"^([a-z]+)", s)
        types[m.group(1) if m else "other"] += 1
    _, authors, _ = run(["git", "shortlog", "-sn", "--no-merges", "HEAD"], root, timeout=300)
    return {
        "available": True,
        "commits": int(count.strip() or 0),
        "commit_type_histogram": dict(types.most_common()),
        "version_sync_commits": sum(1 for s in subj if s.startswith("chore: sync version")),
        "author_identities": len([ln for ln in authors.splitlines() if ln.strip()]),
        "churn_top_20": [{"path": p, "commits": n} for p, n in churn.most_common(20)],
    }


def hygiene_section(root: Path) -> dict[str, Any]:
    present = {f: (root / f).exists() for f in HYGIENE_FILES}
    claude = root / "CLAUDE.md"
    agents = root / "AGENTS.md"
    skills = sorted((root / ".claude" / "skills").glob("*/SKILL.md"))
    largest = sorted(
        ({"path": rel_posix(p, root), "bytes": p.stat().st_size} for p in skills),
        key=lambda d: -d["bytes"],
    )
    return {
        "standard_files": present,
        "claude_md_bytes": claude.stat().st_size if claude.exists() else None,
        "agents_md_bytes": agents.stat().st_size if agents.exists() else None,
        "skills": len(skills),
        "skill_md_total_bytes": sum(p.stat().st_size for p in skills),
        "largest_skills": largest[:5],
    }


def docs_section(root: Path) -> dict[str, Any]:
    docs = sorted(
        ((count_lines(p), rel_posix(p, root)) for p in (root / "docs").rglob("*.md")),
        reverse=True,
    )
    return {"markdown_files": len(docs), "largest": [{"path": p, "lines": n} for n, p in docs[:8]]}


# --------------------------------------------------------------------------- main


def build(
    root: Path, coverage_xml: Path | None, *, git: bool, mypy: bool, ruff: bool, radon: bool
) -> dict[str, Any]:
    _, head, _ = run(["git", "rev-parse", "--short", "HEAD"], root)
    rc_status, status, _ = run(["git", "status", "--porcelain", "--untracked-files=no"], root)
    enabled = (("mypy", mypy), ("ruff", ruff), ("radon", radon))
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": head.strip() or None,
            "tracked_files_modified": bool(status.strip()) if rc_status == 0 else None,
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "tool_versions": {name: tool_version(name, root) for name, on in enabled if on},
            "load_average_start": load_average(),
            "disabled": [k for k, v in (("git", git), *enabled) if not v],
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
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="repository root (default: cwd)"
    )
    parser.add_argument("--out", type=Path, required=True, help="output JSON path")
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        default=None,
        help="coverage.xml from 'pytest --cov' or 'pytest --cov=open_garden_planner'",
    )
    parser.add_argument("--no-git", action="store_true")
    parser.add_argument("--no-mypy", action="store_true")
    parser.add_argument("--no-ruff", action="store_true")
    parser.add_argument("--no-radon", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / "src" / PACKAGE).is_dir():
        print(
            f"error: {root} does not look like the repository root (no src/{PACKAGE})",
            file=sys.stderr,
        )
        return 2
    snap = build(
        root,
        args.coverage_xml,
        git=not args.no_git,
        mypy=not args.no_mypy,
        ruff=not args.no_ruff,
        radon=not args.no_radon,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    loc, lay = snap["loc"], snap["layering"]
    types = snap["types"] or {}
    cov = snap["coverage"] or {}
    print(
        f"wrote {args.out}: src {loc['src_total']} LOC in {loc['src_files']} files; "
        f"tests {snap['tests']['test_functions_total']} functions; "
        f"module-level layering violations {lay['module_level_violations_total']}; "
        f"mypy errors {types.get('errors', 'n/a')}; "
        f"coverage non-UI {(cov.get('non_ui') or {}).get('line_pct', 'n/a')}% lines"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
