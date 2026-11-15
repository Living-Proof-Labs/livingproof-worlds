# SPDX-License-Identifier: Apache-2.0
"""hallway-corner 0.1.0, the corner world (robot-capability-specs #40, Part B step 10)."""

import copy
import itertools
import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import render
import validate
from test_render import text_collisions

CORNER = ROOT / "worlds" / "hallway-corner" / "0.1.0"
HALLWAY = ROOT / "worlds" / "hallway-open" / "0.1.0"
L_FIXTURE = ROOT / "tests" / "fixtures" / "worlds" / "l-shaped.json"
SPECS_L = ROOT / "tests" / "fixtures" / "robot-capability-specs-l-shaped.world.json"


def load(path):
    return json.loads(Path(path).read_text())


@pytest.fixture
def world():
    return load(CORNER / "world.json")


def places(world):
    return {p["name"]: p for p in world["places"]}


def test_it_validates_with_its_manifest_and_lives_at_its_versioned_path(world):
    assert world["format"] == "livingproof-world/0.2"
    assert (world["id"], world["content_version"]) == ("hallway-corner", "0.1.0")
    assert validate.validate(world, CORNER / "world.json") == []


def test_same_clear_width_walls_and_floor_as_hallway_open(world):
    hallway = load(HALLWAY / "world.json")["dimensions"]
    for key in ("clear_width", "wall_height", "wall_thickness", "floor_thickness"):
        assert world["dimensions"][key] == hallway[key], key
    assert world["dimensions"]["clear_width"] == 1.5
    assert world["tolerances"] == load(HALLWAY / "world.json")["tolerances"]


def test_named_places_are_exactly_the_ones_issue_40_names(world):
    kinds = {name: p["type"] for name, p in places(world).items()}
    assert kinds == {
        "entrance": "segment",
        "spawn-entrance": "pose",
        "corner": "region",
        "exit": "segment",
        "route-centreline": "polyline",
    }


def test_two_hallways_meet_at_a_right_angle_and_the_route_runs_down_the_middle(world):
    route = places(world)["route-centreline"]["points"]
    assert len(route) == 3
    (ax, ay, _), (bx, by, _), (cx, cy, _) = route
    first, second = (bx - ax, by - ay), (cx - bx, cy - by)
    assert first[0] * second[0] + first[1] * second[1] == 0  # a right angle
    assert first[0] * second[1] - first[1] * second[0] > 0  # turning left (counterclockwise)
    # Each leg is centred between its hallway's inner wall faces.
    hw = world["dimensions"]["clear_width"] / 2
    walls = [g for g in world["geometry"] if g["role"] == "wall"]
    for a, b in itertools.pairwise(route):
        gaps = [validate._leg_to_box(a, b, w) for w in walls]
        assert min(gaps) == pytest.approx(hw), (a, b)


def test_corner_is_the_square_where_the_two_hallways_meet(world):
    p = places(world)
    corner, route = p["corner"], p["route-centreline"]["points"]
    hw = world["dimensions"]["clear_width"] / 2
    vx, vy, _ = route[1]
    assert corner["x"] == [vx - hw, vx + hw]
    assert corner["y"] == [vy - hw, vy + hw]
    # Its outer sides are the inner faces of the two outer walls.
    walls = {g["name"]: g for g in world["geometry"]}
    outer_first, outer_second = walls["wall-outer-first"], walls["wall-outer-second"]
    assert outer_first["centre"][1] + outer_first["size"][1] / 2 == pytest.approx(corner["y"][0])
    assert outer_second["centre"][0] - outer_second["size"][0] / 2 == pytest.approx(corner["x"][1])


def test_every_wall_is_an_axis_aligned_box_and_the_walls_are_closed(world):
    for g in world["geometry"]:
        assert set(g) == {"name", "type", "role", "centre", "size"}
        assert g["type"] == "box"
    # A probe point just outside the clear width, anywhere along the route, is inside a
    # wall: no gap at the corner where two walls meet.
    walls = [g for g in world["geometry"] if g["role"] == "wall"]
    hw = world["dimensions"]["clear_width"] / 2
    t = world["dimensions"]["wall_thickness"]
    probes = [(x / 10, -hw - t / 2) for x in range(-30, 9)]  # outer wall, first hallway
    probes += [(hw + t / 2, y / 10) for y in range(-9, 31)]  # outer wall, second hallway
    probes += [(x / 10, hw + t / 2) for x in range(-30, -8)]  # inner wall, first hallway
    probes += [(-hw - t / 2, y / 10) for y in range(9, 31)]  # inner wall, second hallway
    probes += [(-hw - t / 2, hw + t / 2)]  # the inside corner itself
    for point in probes:
        assert min(validate._point_to_box(point, w) for w in walls) < 1e-9, point


def test_route_length_from_spawn_matches_hallway_open(world):
    # The turn is the only change: the scenario's route_length is the same 5.5 m.
    assert validate.route_length(world, "route-centreline") == 5.5
    assert validate.route_length(load(HALLWAY / "world.json"), "passage-centreline") == 5.5
    assert render._route_length(places(world)["route-centreline"]) == 6.0


def test_entrance_and_exit_are_the_open_ends(world):
    p = places(world)
    route = p["route-centreline"]["points"]
    assert p["entrance"]["reference"] == route[0]
    assert p["exit"]["reference"] == route[-1]
    floors = [g for g in world["geometry"] if g["role"] == "floor"]
    # Both ends lie on a floor edge, so nothing closes the hallway beyond them.
    for name in ("entrance", "exit"):
        x, y, _ = p[name]["reference"]
        assert any(
            min(abs(x - (g["centre"][0] + s * g["size"][0] / 2)) for s in (-1, 1)) < 1e-9
            or min(abs(y - (g["centre"][1] + s * g["size"][1] / 2)) for s in (-1, 1)) < 1e-9
            for g in floors
        ), name


def test_geometry_is_the_reviewed_l_shaped_test_world(world):
    # The layout contract was reviewed on this exact geometry (worlds #13, specs #47).
    for fixture in (load(L_FIXTURE), load(SPECS_L)):
        for key in ("units", "dimensions", "geometry", "places", "tolerances"):
            assert world[key] == fixture[key], key


def test_specification_pins_a_released_world_contract(world):
    spec = world["specification"]
    assert spec["repository"] == "Living-Proof-Labs/robot-capability-specs"
    assert spec["path"] == "specs/worlds/README.md"
    assert (spec["tag"], spec["commit"]) == ("v2.2.2", "2ea6d302ef1ef4614f62ccd189545981cd0cb07e")
    assert spec["document_revision"] == spec["world_contract_revision"] == "0.3.0"


@pytest.mark.parametrize(
    "change, expected",
    [
        (lambda w: places(w)["route-centreline"]["points"][1].__setitem__(0, 0.3), "closer"),
        (
            lambda w: w["geometry"][5].update(centre=[-0.825, 1.875, 1.25], size=[0.15, 2.25, 2.5]),
            "overlaps",
        ),
        (lambda w: places(w)["spawn-entrance"].update(yaw_deg=90.0), "must face along"),
        (lambda w: w["dimensions"].update(length=6.0), "INVALID dimensions"),
    ],
)
def test_breaking_the_corner_fails_validation(world, change, expected):
    bad = copy.deepcopy(world)
    change(bad)
    assert any(expected in e for e in validate.validate(bad)), validate.validate(bad)


def test_plan_drawing_has_no_text_collisions_and_stays_in_view(world):
    lay = render.layout(world)
    assert text_collisions(lay["boxes"]) == []
    for kind, name, x0, y0, x1, y1 in lay["boxes"]:
        if kind == "text":
            assert 0 <= x0 and x1 <= render.VIEW_W and 0 <= y0 and y1 <= lay["height"], name
    walls = [b for b in lay["boxes"] if b[0] == "wall"]
    assert sorted(b[1] for b in walls) == sorted(
        g["name"] for g in world["geometry"] if g["role"] == "wall"
    )


def test_svg_shows_the_corner_route_and_ends(world):
    svg = (CORNER / "world.svg").read_text()
    for needle in [
        'class="wall"',
        'class="floor"',
        'class="entrance"',
        'class="exit"',
        'class="passage"',
        'class="centre"',
        'class="yaw"',
        ">IN<",
        ">OUT<",
        ">corner<",
        ">route-centreline<",
        "1.50 m clear",
        "route-centreline: 6.00 m from entrance to exit",
        "hallway-corner 0.1.0",
    ]:
        assert needle in svg, needle
    assert len(re.findall(r'<rect class="floor"', svg)) == 2
    assert len(re.findall(r'<rect class="wall" x="[\d.]+"', svg)) == 1 + 4  # legend + walls
    assert re.search(r'<polyline class="centre" points="[^"]+ [^"]+ [^"]+"/>', svg)
    assert "--amber:#b45309" in svg and "@media (prefers-color-scheme: dark)" in svg
    for text in re.findall(r"<text[^>]*>([^<]*)</text>", svg):
        assert len(text) <= 90, text


def test_plan_is_drawn_to_the_hallway_scale_and_the_exit_is_up(world):
    lay = render.layout(world)
    walls = {b[1]: b for b in lay["boxes"] if b[0] == "wall"}
    first = walls["wall-outer-first"]
    assert first[4] - first[2] == pytest.approx(3.9 * render.PLAN_MAX_SCALE)
    bars = {b[1]: b for b in lay["boxes"] if b[0] == "bar"}
    assert bars["exit"][3] < bars["entrance"][3]  # +y is up the page
    assert math.isclose(bars["entrance"][4] - bars["entrance"][2], 6)  # vertical bar


def test_readme_describes_the_corner_from_world_json(world):
    text = (CORNER / "README.md").read_text()
    assert render.readme_section_errors(text) == []
    assert "| Route length (`route-centreline`, entrance to exit) | 6.00 m |" in text
    assert "Length (floor and walls along +x)" not in text and "Exterior width" not in text
    assert "| `corner` | region | x = [-0.75, 0.75], y = [-0.75, 0.75] |" in text
    assert (
        "| `route-centreline` | polyline | (-3.00, 0.00, 0.00) → (0.00, 0.00, 0.00) → "
        "(0.00, 3.00, 0.00) |"
    ) in text
    assert "named region (`corner`)" in text and "the route `route-centreline`" in text
    assert "robot-capability-specs/blob/v2.2.2/specs/worlds/README.md" in text
    assert f'alt="{render.describe(world)}"' in text
    assert "Region corner from x = -0.75 to 0.75 m" in render.describe(world)


def test_catalog_index_and_manual_list_the_corner():
    readme = (ROOT / "README.md").read_text()
    assert "[`hallway-corner`](worlds/hallway-corner/0.1.0/world.json) | `0.1.0`" in readme
    nav = (ROOT / "tools" / "manual" / "mkdocs.yml").read_text()
    assert "worlds/hallway-corner/0.1.0/index.md" in nav
    assert "../worlds/hallway-corner/0.1.0/README.md" in (ROOT / "docs" / "manual.md").read_text()
