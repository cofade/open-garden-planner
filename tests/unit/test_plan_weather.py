"""A plan's showcase weather (#944): an additive key, validated at the boundary."""

from __future__ import annotations

import json

import pytest

from open_garden_planner.core.project import FILE_VERSION, ProjectData
from open_garden_planner.core.scene3d.weather import WEATHERS


def test_a_weather_is_an_additive_plan_key_and_the_version_stays() -> None:
    clear = ProjectData().to_dict()
    snowy = ProjectData(weather="snow").to_dict()
    assert "weather" not in clear
    assert snowy["weather"] == "snow"
    assert snowy["version"] == FILE_VERSION == "1.4"
    assert set(snowy) - set(clear) == {"weather"}
    assert ProjectData.from_dict(json.loads(json.dumps(snowy))).weather == "snow"


@pytest.mark.parametrize("written", [None, "", "today", "storm", 7, ["snow"]])
def test_a_plan_weather_this_build_does_not_know_opens_clear(written) -> None:
    data = ProjectData().to_dict()
    data["weather"] = written
    assert ProjectData.from_dict(data).weather == "clear"


def test_every_concrete_weather_can_be_stored() -> None:
    for weather in WEATHERS:
        written = ProjectData(weather=weather).to_dict()
        assert written.get("weather", "clear") == weather
