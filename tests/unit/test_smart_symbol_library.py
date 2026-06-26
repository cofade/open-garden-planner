"""Loader-resilience tests for the smart-symbol library (US-C4).

The module contract (and CLAUDE.md): a malformed **bundled** file is a packaging
bug and crashes loud, but a malformed **user** file must be skipped with a
warning — one bad drop-in must never break app startup. The risky case is a file
that loads structurally but blows up during the eager dry-run generation
(divide-by-zero / overflow / bad-round), because those raise ``ArithmeticError``/
``TypeError``, not ``ValueError`` — the bug this test pins shut.
"""

import json
from pathlib import Path

import pytest

from open_garden_planner.services.smart_symbol_library import SmartSymbolLibrary

_VALID = {
    "id": "ok", "version": 1, "name": "OK", "name_de": "OK", "category": "c",
    "parameters": [{"name": "L", "type": "length", "label": "L", "default": 10}],
    "elements": [{"kind": "rect", "x": 0, "y": 0, "w": "L", "h": "L"}],
}

# Structurally valid, but a default-valued coordinate divides by zero — the
# dry-run in from_dict raises ZeroDivisionError (an ArithmeticError, NOT a
# ValueError). Pre-fix this escaped the loader and crashed startup.
_POISONED_DIVZERO = {
    "id": "boom", "version": 1, "name": "Boom", "name_de": "Boom", "category": "c",
    "parameters": [{"name": "n", "type": "number", "label": "N", "default": 0}],
    "elements": [{"kind": "line", "x1": 0, "y1": 0, "x2": "10 / n", "y2": 0}],
}

# Float-power overflow (OverflowError, also an ArithmeticError).
_POISONED_OVERFLOW = {
    "id": "ov", "version": 1, "name": "Ov", "name_de": "Ov", "category": "c",
    "parameters": [],
    "elements": [{"kind": "rect", "x": 0, "y": 0, "w": "9 ** 9 ** 9", "h": 1}],
}

# A deeply-chained expression — without the evaluator's node cap this blows the
# stack with RecursionError (a RuntimeError, NOT a ValueError/ArithmeticError),
# the family that escaped the first fix. Must be skipped, not fatal.
_POISONED_RECURSION = {
    "id": "rec", "version": 1, "name": "Rec", "name_de": "Rec", "category": "c",
    "parameters": [],
    "elements": [{"kind": "rect", "x": 0, "y": 0,
                  "w": "+".join(["1"] * 5000), "h": 1}],
}


def _write(d: Path, name: str, data: dict) -> None:
    with open(d / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_poisoned_user_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write(bundled, "ok", _VALID)
    _write(user, "boom", _POISONED_DIVZERO)
    _write(user, "ov", _POISONED_OVERFLOW)
    _write(user, "rec", _POISONED_RECURSION)
    _write(user, "good", {**_VALID, "id": "good"})

    lib = SmartSymbolLibrary(bundled_dir=bundled, user_dir=user)
    # Must not raise — the poisoned files are skipped, the rest load.
    ids = {d.id for d in lib.definitions()}
    assert ids == {"ok", "good"}
    assert lib.get("boom") is None
    assert lib.get("ov") is None
    assert lib.get("rec") is None


@pytest.mark.parametrize("bad_params", [42, "x", None, [1, 2], [42], ["x"], [None]])
def test_structurally_poisoned_user_file_is_skipped(tmp_path: Path, bad_params) -> None:
    # A non-dict ``parameters`` value (or non-dict entry) makes the STRUCTURAL
    # phase of from_dict raise AttributeError/TypeError — which runs BEFORE the
    # dry-run generate() and so is not covered by generate()'s wrapper. The
    # loader's untrusted-input boundary must still skip it, never crash.
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write(bundled, "ok", _VALID)
    _write(user, "bad", {**_VALID, "id": "bad", "parameters": bad_params})
    _write(user, "good", {**_VALID, "id": "good"})

    lib = SmartSymbolLibrary(bundled_dir=bundled, user_dir=user)
    assert {d.id for d in lib.definitions()} == {"ok", "good"}
    assert lib.get("bad") is None


def test_non_object_user_file_is_skipped(tmp_path: Path) -> None:
    # The whole JSON document is a list/number, not an object.
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write(bundled, "ok", _VALID)
    (user / "arr.json").write_text("[1, 2, 3]", encoding="utf-8")
    (user / "num.json").write_text("42", encoding="utf-8")

    lib = SmartSymbolLibrary(bundled_dir=bundled, user_dir=user)
    assert {d.id for d in lib.definitions()} == {"ok"}


def test_malformed_json_user_file_is_skipped(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write(bundled, "ok", _VALID)
    (user / "broken.json").write_text("{ not valid json", encoding="utf-8")

    lib = SmartSymbolLibrary(bundled_dir=bundled, user_dir=user)
    assert {d.id for d in lib.definitions()} == {"ok"}


def test_malformed_bundled_file_crashes_loud(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    _write(bundled, "boom", _POISONED_DIVZERO)

    lib = SmartSymbolLibrary(bundled_dir=bundled, user_dir=user)
    # A packaging bug must surface, not be silently swallowed.
    with pytest.raises(ValueError):
        lib.definitions()
