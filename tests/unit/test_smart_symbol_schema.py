"""CI schema validator for every bundled smart-symbol JSON (US-C4).

Satisfies the acceptance criterion "add a schema validator that runs in CI for
every file under data/smart_symbols/". Each bundled file must load, validate,
have every expression parse, and generate ≥1 primitive at its defaults.
"""

import json
from pathlib import Path

import pytest

from open_garden_planner.models.smart_symbol import SmartSymbolDefinition

_BUNDLED_DIR = (
    Path(__file__).parent.parent.parent
    / "src" / "open_garden_planner" / "resources" / "data" / "smart_symbols"
)

_FILES = sorted(_BUNDLED_DIR.glob("*.json"))


def test_bundled_dir_exists_and_has_symbols() -> None:
    assert _BUNDLED_DIR.is_dir()
    assert len(_FILES) >= 5, "the starter set requires ≥5 bundled symbols"


@pytest.mark.parametrize("path", _FILES, ids=[p.stem for p in _FILES])
def test_bundled_symbol_is_valid(path: Path) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    definition = SmartSymbolDefinition.from_dict(data)  # validates structure + expressions
    assert definition.id == path.stem, "symbol id should match its filename"
    assert definition.name and definition.name_de, "needs name + name_de"
    specs = definition.generate(definition.param_defaults())
    assert len(specs) >= 1, "must generate at least one primitive at defaults"
    for param in definition.parameters:
        assert param.label, f"param {param.name} needs a label"


def test_all_ids_unique() -> None:
    ids = []
    for path in _FILES:
        with open(path, encoding="utf-8") as f:
            ids.append(json.load(f)["id"])
    assert len(ids) == len(set(ids)), "duplicate symbol ids across bundled files"
