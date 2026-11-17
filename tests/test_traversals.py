# SPDX-License-Identifier: Apache-2.0
import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate

DRAFT = ROOT / "drafts/hallway-corner/0.2.0/world.json"
GOOD = json.loads(DRAFT.read_text())


def place(world, name):
    return next(p for p in world["places"] if p["name"] == name)


def test_one_physical_fixture_two_directions():
    old = json.loads((ROOT / "worlds/hallway-corner/0.1.0/world.json").read_text())
    assert validate.validate(GOOD, draft=True) == []
    assert GOOD["geometry"] == old["geometry"]
    assert GOOD["dimensions"] == old["dimensions"]
    assert place(GOOD, "route-reverse")["points"] == list(
        reversed(place(GOOD, "route-forward")["points"])
    )
    assert place(GOOD, "spawn-west")["yaw_deg"] == 0
    assert place(GOOD, "spawn-north")["yaw_deg"] == -90
    for t in GOOD["traversals"]:
        assert validate.route_length(GOOD, start=t["start"], route=t["route"]) == 5.5
        assert place(GOOD, t["route"])["points"][0] == place(GOOD, t["from"])["reference"]
        assert place(GOOD, t["route"])["points"][-1] == place(GOOD, t["finish"])["reference"]


@pytest.mark.parametrize("key", ["from", "start", "route", "finish"])
@pytest.mark.parametrize("value", ["absent", "corner", None])
def test_missing_or_wrong_references(key, value):
    world = copy.deepcopy(GOOD)
    if value is None:
        del world["traversals"][0][key]
    else:
        world["traversals"][0][key] = value
    assert validate.validate(world, draft=True)


@pytest.mark.parametrize(
    "name,field,value,expected",
    [
        ("spawn-north", "yaw_deg", 90, "face along"),
        ("spawn-west", "position", [-2.5, 0, 1], "floor"),
        ("spawn-west", "position", [0, 1, 0], "first route leg"),
        ("spawn-west", "position", [-3, 0, 0], "first route leg"),
        ("spawn-west", "position", [-2.5, 0.1, 0], "must lie on"),
        ("route-forward", "points", [[-3, 0, 0], [-3, 0, 0], [0, 3, 0]], "repeated"),
        ("route-forward", "points", [[-3, 0, 0], [0, 3, 0]], "closer than"),
        ("end-west", "points", [[-3.75, 0, 0], [-2.25, 0, 0]], "perpendicular"),
    ],
)
def test_inconsistent_places(name, field, value, expected):
    world = copy.deepcopy(GOOD)
    place(world, name)[field] = value
    assert expected in "\n".join(validate.validate(world, draft=True))


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("finish", "end-west", "distinct"),
        ("route", "route-reverse", "must start"),
        ("start", "spawn-north", "first route leg"),
        ("name", "reverse", "unique"),
        ("reverse", True, "UNSUPPORTED"),
    ],
)
def test_inconsistent_traversals(key, value, expected):
    world = copy.deepcopy(GOOD)
    world["traversals"][0][key] = value
    assert expected in "\n".join(validate.validate(world, draft=True))


def test_release_catalog_rejects_unpublished_dependencies():
    assert validate.validate(GOOD)
    assert "unpublished" in validate.validate(GOOD, DRAFT, draft=True)[0]
    assert DRAFT not in validate.world_files()
    for path in (ROOT / "schema").glob("world-0.3*.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_empty_traversals_and_duplicate_places_fail():
    world = copy.deepcopy(GOOD)
    world["traversals"] = []
    assert validate.validate(world, draft=True)
    world = copy.deepcopy(GOOD)
    world["places"].append(copy.deepcopy(world["places"][0]))
    assert "unique" in "\n".join(validate.validate(world, draft=True))


def test_draft_rendering_preserves_geometry_and_is_current():
    import xml.etree.ElementTree as ET

    import render

    original = copy.deepcopy(GOOD)
    expected = render.outputs(DRAFT.parent)
    assert GOOD == original
    assert len([name for name in expected if name.endswith(".svg")]) == 6
    for name, text in expected.items():
        assert (DRAFT.parent / name).read_text() == text
        if name.endswith(".svg"):
            ET.fromstring(text)
            assert "end-west" in text and "end-north" in text
    assert "5.5 m" in expected["README.md"]
    assert render.readme_section_errors(expected["README.md"]) == []


@pytest.mark.parametrize("direction", ["forward", "reverse"])
@pytest.mark.parametrize("offset", [0, 0.5e-9])
def test_non_adjacent_repeated_vertex(direction, offset):
    world = copy.deepcopy(GOOD)
    points = [[-3, 0, 0], [0, 0, 0], [-1, 0, 0], [offset, 0, 0], [0, 3, 0]]
    traversal = next(t for t in world["traversals"] if t["name"] == direction)
    place(world, traversal["route"])["points"] = points if direction == "forward" else points[::-1]
    assert validate.schema_errors(world, draft=True) == []
    assert "repeated point" in "\n".join(validate.validate(world, draft=True))


def test_layout_repeated_vertex_fix_preserves_original_straight_format():
    corner = json.loads((ROOT / "worlds/hallway-corner/0.1.0/world.json").read_text())
    place(corner, "route-centreline")["points"] = [
        [-3, 0, 0],
        [0, 0, 0],
        [-1, 0, 0],
        [0, 0, 0],
        [0, 3, 0],
    ]
    assert "repeated point" in "\n".join(validate.validate(corner))
    straight = json.loads((ROOT / "worlds/hallway-open/0.1.0/world.json").read_text())
    place(straight, "passage-centreline")["points"] = [
        [-3, 0, 0],
        [-1, 0, 0],
        [-2, 0, 0],
        [-1, 0, 0],
        [3, 0, 0],
    ]
    assert validate.validate(straight) == []
