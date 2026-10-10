"""Guild validation, pure layout, explicit coverage and library isolation."""

from copy import deepcopy

import pytest

from open_garden_planner.models.guild import GuildTemplate, remap_copied_guilds, ring_positions
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.services.guild_service import compute_guilds, guild_diagnostics


@pytest.fixture
def apple(tmp_path):
    return GuildLibrary(user_dir=tmp_path).templates["apple-guild"]


def test_coverage_uses_actual_functions_once_per_explicit_member(apple):
    centre = {"item_id": "a", "guild": {"guild_id": "g", "role": "centre", "name": "A", "template": apple.to_dict()}, "functions": []}
    false_fixer = {"item_id": "b", "guild": {"guild_id": "g", "role": "nitrogen_fixer"}, "functions": []}
    nearby = {"item_id": "unassigned", "functions": ["nitrogen_fixer"]}
    statuses, errors = compute_guilds([centre, false_fixer, nearby])
    assert not errors and statuses[0].present == {}
    assert len(guild_diagnostics(statuses)) == 3
    false_fixer["functions"] = ["nitrogen_fixer", "nitrogen_fixer", "ground_cover", "pollinator_attractor"]
    statuses, _ = compute_guilds([centre, false_fixer, nearby])
    assert statuses[0].present["nitrogen_fixer"] == 1
    assert not statuses[0].missing


@pytest.mark.parametrize("change", [{"version": True}, {"roles": [{"function": "future", "count_min": 1, "ring_radius_cm": 1}]},
    {"roles": [{"function": "ground_cover", "count_min": 200, "ring_radius_cm": 1}]},
    {"roles": [{"function": "ground_cover", "count_min": 1, "ring_radius_cm": float("nan")}]},
    {"roles": [{"function": "ground_cover", "count_min": 1, "ring_radius_cm": True}]}])
def test_invalid_template_refused(apple, change):
    data = apple.to_dict()
    data.update(change)
    with pytest.raises(ValueError):
        GuildTemplate.from_dict(data)


def test_canopy_layout_deterministic_and_spacing_required(apple):
    first = ring_positions(apple, (500, 500), 300)
    assert first == ring_positions(apple, (500, 500), 300)
    assert first[0] == ("nitrogen_fixer", 800, 500)
    with pytest.raises(ValueError, match="spacing"):
        ring_positions(apple, (0, 0), None)


def test_malformed_members_preserved_but_excluded(apple):
    members = [{"item_id": "a", "guild": {"guild_id": "g", "role": "centre", "name": "A", "template": apple.to_dict()}},
               {"item_id": "b", "guild": "broken", "functions": ["nitrogen_fixer"]}]
    saved = deepcopy(members)
    statuses, errors = compute_guilds(members)
    assert len(errors) == 1 and statuses[0].missing["nitrogen_fixer"] == 1
    assert saved == members


def test_user_file_isolation_and_atomic_failure(tmp_path, monkeypatch, apple):
    (tmp_path / "bad.json").write_text("[]", encoding="utf8")
    library = GuildLibrary(user_dir=tmp_path)
    assert len(library.templates) == 3 and library.errors[0][0] == "bad.json"
    path = library.save(apple)
    previous = path.read_bytes()
    def fail(*_args):
        raise OSError("disk full")
    monkeypatch.setattr("open_garden_planner.services.guild_library.os.replace", fail)
    with pytest.raises(OSError):
        library.save(apple)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_copy_complete_and_partial_guild_independent(apple):
    records = [{"item_id": "a", "metadata": {"guild": {"guild_id": "g", "role": "centre", "template": apple.to_dict()}}},
               {"item_id": "b", "metadata": {"guild": {"guild_id": "g", "role": "nitrogen_fixer"}}}]
    copied = remap_copied_guilds(records, complete_member_ids={"g": {"a", "b"}})
    assert copied[0]["metadata"]["guild"]["guild_id"] == copied[1]["metadata"]["guild"]["guild_id"] != "g"
    copied[0]["metadata"]["guild"]["template"]["name"] = "Changed"
    assert records[0]["metadata"]["guild"]["template"]["name"] == "Apple guild"
    partial = remap_copied_guilds(records[:1], complete_member_ids={"g": {"a", "b"}})
    assert "guild" not in partial[0]["metadata"]
