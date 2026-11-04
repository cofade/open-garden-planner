"""Replay an explicit A5 mutation sample in isolated fresh pytest processes.

No development source is overwritten. A temporary import finder substitutes only
the selected module; tests, resources and Qt still use the current checkout.
This is a sampled experiment, not a mutmut population score.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_TESTS = {"test_constraint_solver_invariants.py", "test_constraint_descriptors.py",
             "test_constraint_presentation_workflow.py", "test_constraint_mutation_replay.py"}


@dataclass(frozen=True)
class Mutation:
    name: str
    module: str
    function: str
    before: str
    after: str


NEWTON = "open_garden_planner.core.constraint_solver_newton"
GRAPH = "open_garden_planner.core.constraints"
MUTATIONS = (
    Mutation("newton-horizontal-axis", NEWTON, "newton_refine",
             "ay + by - 2.0 * axis_y", "ay + by - axis_y"),
    Mutation("newton-vertical-axis", NEWTON, "newton_refine",
             "ax + bx - 2.0 * axis_x", "ax + bx - axis_x"),
    Mutation("newton-pinned-offset-y", NEWTON, "newton_refine",
             "return p[0] + off[0], p[1] + off[1]", "return p[0] + off[0], p[1] - off[1]"),
    Mutation("newton-reported-error", NEWTON, "newton_refine",
             "    write_x(x)\n    return max_err <= tol, max_err",
             "    write_x(x)\n    return max_err <= tol, 0.0"),
    Mutation("newton-no-writeback", NEWTON, "newton_refine",
             "    write_x(x)\n    return max_err <= tol, max_err",
             "    # mutant: discard final state\n    return max_err <= tol, max_err"),
    Mutation("anchored-ignore-pins", GRAPH, "solve_anchored",
             "pinned_items = set(pinned_items)", "pinned_items = set()"),
    Mutation("anchored-offset-y", GRAPH, "solve_anchored",
             "positions[item_id][1] + off[1]", "positions[item_id][1] - off[1]"),
    Mutation("conflict-drop-identities", GRAPH, "find_conflicting_constraints",
             "return conflicting", "return []"),
)


def relevant_tests(selection: str) -> list[str]:
    """Explicit direct consumers plus every constraint-named test, all test layers."""
    files = []
    pattern = re.compile(
        r"\b(ConstraintType|ConstraintGraph|newton_refine|solve_anchored|"
        r"find_conflicting_constraints|project_to_feasible)\b"
    )
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        if selection == "baseline" and path.name in NEW_TESTS:
            continue
        if "constraint" in path.name or pattern.search(path.read_text(encoding="utf-8")):
            files.append(path.relative_to(ROOT).as_posix())
    return files


def dispatch_inventory() -> list[dict[str, object]]:
    """Count type-sensitive if conditions by function, not historical co-change."""
    inventory = []
    enum_source = ast.parse(module_source(GRAPH, None))
    enum = next(node for node in enum_source.body if isinstance(node, ast.ClassDef) and node.name == "ConstraintType")
    names = {target.id for node in enum.body if isinstance(node, ast.Assign)
             for target in node.targets if isinstance(target, ast.Name)}
    for path in sorted((ROOT / "src/open_garden_planner").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "ConstraintType" not in source and "constraint_type_name" not in source:
            continue
        tree = ast.parse(source)
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            def body_nodes(node: ast.AST):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        continue
                    yield child
                    yield from body_nodes(child)

            conditions = [node.test for node in body_nodes(function) if isinstance(node, ast.If)]
            count = sum(any(
                isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "ConstraintType"
                or isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in names
                for node in ast.walk(condition)
            ) for condition in conditions)
            if count:
                inventory.append({"path": path.relative_to(ROOT).as_posix(),
                                  "function": function.name, "line": function.lineno,
                                  "type_sensitive_if_conditions": count})
    return inventory


def module_source(module: str, source_ref: str | None) -> str:
    path = Path("src") / Path(*module.split(".")).with_suffix(".py")
    if source_ref:
        return subprocess.run(["git", "show", f"{source_ref}:{path.as_posix()}"], cwd=ROOT,
                              check=True, capture_output=True, text=True, encoding="utf-8").stdout
    return (ROOT / path).read_text(encoding="utf-8")


def mutated_source(mutation: Mutation, source: str) -> str:
    path = ROOT / "src" / Path(*mutation.module.split(".")).with_suffix(".py")
    # Restrict replacements to the named top-level function or class method.
    pattern = re.compile(rf"^(?P<indent> *)def {mutation.function}\(", re.MULTILINE)
    match = pattern.search(source)
    if match is None:
        raise ValueError(f"Missing function: {mutation.function}")
    following = re.search(rf"^{match['indent']}def \w+\(", source[match.end():], re.MULTILINE)
    end = match.end() + following.start() if following else len(source)
    body = source[match.start():end]
    if body.count(mutation.before) != 1:
        raise ValueError(f"{mutation.name}: expected exactly one source match")
    changed = source[:match.start()] + body.replace(mutation.before, mutation.after) + source[end:]
    compile(changed, str(path), "exec")
    return changed


def run_tests(files: list[str], timeout: int, mutation: Mutation | None,
              sources: dict[str, str]) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ogp-a5-mutant-") as directory:
        overlay = Path(directory)
        env = dict(os.environ, PYTHONUTF8="1", QT_QPA_PLATFORM="offscreen")
        replacements = dict(sources)
        if mutation:
            replacements[mutation.module] = mutated_source(mutation, sources[mutation.module])
        paths = {}
        for index, (module, source) in enumerate(replacements.items()):
            path = overlay / f"replacement_{index}.py"
            path.write_text(source, encoding="utf-8")
            paths[module] = str(path)
        (overlay / "sitecustomize.py").write_text(
                "import importlib.abc, importlib.util, pathlib, sys\n"
                f"PATHS = {paths!r}\n"
                "class MutantFinder(importlib.abc.MetaPathFinder):\n"
                "    def find_spec(self, fullname, path=None, target=None):\n"
                "        if fullname in PATHS:\n"
                "            return importlib.util.spec_from_file_location(fullname, PATHS[fullname])\n"
                "sys.meta_path.insert(0, MutantFinder())\n", encoding="utf-8",
            )
        env["PYTHONPATH"] = str(overlay) + os.pathsep + env.get("PYTHONPATH", "")
        # `-n 0` is load-bearing here for two reasons. The mutant is installed via a
        # `sys.meta_path` finder in a `sitecustomize` overlay, and an xdist worker is a
        # separate interpreter that does not necessarily get that overlay's import
        # hook early enough to be the one under test. And this replay is run once per
        # mutant against a wall-clock timeout, so `addopts`' `-n auto` would spend the
        # budget on worker start-up for a handful of files (#509).
        command = [sys.executable, "-m", "pytest", *files, "-q", "-x", "--tb=short",
                   "-n", "0"]
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"name": mutation.name if mutation else "control", "status": "timeout"}
        status = {0: "survived" if mutation else "passed", 1: "killed"}.get(result.returncode, "invalid")
        # A collection/Qt startup crash is not evidence that an assertion killed a mutant.
        if result.returncode == 1 and ("ERROR collecting" in result.stdout or "FAILED" not in result.stdout):
            status = "invalid"
        return {
            "name": mutation.name if mutation else "control", "status": status,
            "returncode": result.returncode,
            "summary": result.stdout[-4500:], "stderr": result.stderr[-1500:],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", choices=("baseline", "strengthened"), default="baseline")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--source-ref", help="Replay both solver modules from this git revision")
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--only", choices=[m.name for m in MUTATIONS], action="append")
    args = parser.parse_args()
    if args.inventory_only:
        args.output.write_text(json.dumps(dispatch_inventory(), indent=2) + "\n", encoding="utf-8")
        return 0
    files = relevant_tests(args.selection)
    if args.selection == "strengthened":
        files.sort(key=lambda name: (not name.endswith("test_constraint_solver_invariants.py"), name))
    sources = {module: module_source(module, args.source_ref) for module in (NEWTON, GRAPH)}
    control = run_tests(files, args.timeout, None, sources)
    report = {"selection": args.selection, "source_ref": args.source_ref,
              "source_sha256": {module: hashlib.sha256(source.encode()).hexdigest() for module, source in sources.items()},
              "tests": files, "mutations": [asdict(m) for m in MUTATIONS],
              "control": control, "results": []}
    if control["status"] != "passed":
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Control {control['status']}: {control.get('summary', 'no pytest summary')}")
        return 1
    results = report["results"]
    for mutation in MUTATIONS:
        if args.only and mutation.name not in args.only:
            continue
        result = run_tests(files, args.timeout, mutation, sources)
        results.append(result)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"{mutation.name}: {result['status']}", flush=True)
    return int(any(result["status"] in {"timeout", "invalid"} for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
