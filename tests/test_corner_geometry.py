# SPDX-License-Identifier: Apache-2.0
"""hallway-corner 0.1.0 measured from its boxes, not from its declared dimensions.

The declared ``dimensions`` and the validator's layout rules are checked elsewhere. These
tests read the wall and floor boxes themselves: the clear width all along each hallway,
the right angle, the floor under every walkable point and under every wall, the open
ends, the corner square's sides, and room to turn at the corner.
"""

import itertools
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import validate

CORNER = ROOT / "worlds" / "hallway-corner" / "0.1.0" / "world.json"
HALLWAY = ROOT / "worlds" / "hallway-open" / "0.1.0" / "world.json"
EPS = 1e-9
STEP = 0.05


def load(path):
    return json.loads(Path(path).read_text())


@pytest.fixture
def world():
    return load(CORNER)


def bounds(box):
    return [(c - s / 2, c + s / 2) for c, s in zip(box["centre"], box["size"], strict=True)]


def boxes(world, role):
    return [g for g in world["geometry"] if g["role"] == role]


def places(world):
    return {p["name"]: p for p in world["places"]}


def inside(point, box, margin=EPS):
    (x0, x1), (y0, y1), _ = bounds(box)
    return x0 - margin <= point[0] <= x1 + margin and y0 - margin <= point[1] <= y1 + margin


def strictly_inside(point, box):
    (x0, x1), (y0, y1), _ = bounds(box)
    return x0 + EPS < point[0] < x1 - EPS and y0 + EPS < point[1] < y1 - EPS


def frange(a, b, step=STEP):
    n = round((b - a) / step)
    return [a + (b - a) * i / n for i in range(n + 1)]


def fine(a, b, step=0.01):
    """Both ends, and points every ``step`` offset by half a step, so a seam on the grid
    cannot hide a gap wider than ``step`` (the world's 0.01 m distance tolerance)."""
    n = round((b - a) / step)
    return [a, b] + [a + step * (i + 0.5) for i in range(n)]


def clear_area(world):
    """Sample points of the walkable area: each hallway between its inner wall faces."""
    hw = world["dimensions"]["clear_width"] / 2
    (ax, ay, _), (vx, vy, _), (bx, by, _) = places(world)["route-centreline"]["points"]
    first = [(x, y) for x in fine(ax, vx + hw) for y in fine(ay - hw, ay + hw, 0.05)]
    first += [(x, y) for x in fine(ax, vx + hw, 0.05) for y in fine(ay - hw, ay + hw)]
    second = [(x, y) for x in fine(bx - hw, bx + hw) for y in fine(vy + hw, by, 0.05)]
    second += [(x, y) for x in fine(bx - hw, bx + hw, 0.05) for y in fine(vy + hw, by)]
    return first + second


def faces_across(world, along, at, side):
    """Nearest wall face on ``side`` (+1/-1) of the centreline, across a hallway.

    ``along`` is 0 for a hallway along x (faces are y values), 1 for one along y.
    """
    across = 1 - along
    found = []
    for w in boxes(world, "wall"):
        b = bounds(w)
        if b[along][0] - EPS <= at <= b[along][1] + EPS:
            face = b[across][0] if side > 0 else b[across][1]
            if (face > 0) == (side > 0):
                found.append(face)
    if not found:
        return None
    return min(found) if side > 0 else max(found)


def test_first_hallway_is_clear_width_between_wall_faces_all_along(world):
    cw = world["dimensions"]["clear_width"]
    (ax, _, _), (vx, _, _), _ = places(world)["route-centreline"]["points"]
    for x in frange(ax, vx - cw / 2):
        left, right = faces_across(world, 0, x, +1), faces_across(world, 0, x, -1)
        assert left is not None and right is not None, x
        assert left - right == pytest.approx(cw, abs=EPS), x
        assert left == pytest.approx(cw / 2, abs=EPS) and right == pytest.approx(-cw / 2, abs=EPS)


def test_second_hallway_is_clear_width_between_wall_faces_all_along(world):
    cw = world["dimensions"]["clear_width"]
    _, (_, vy, _), (_, by, _) = places(world)["route-centreline"]["points"]
    for y in frange(vy + cw / 2, by):
        outer, inner = faces_across(world, 1, y, +1), faces_across(world, 1, y, -1)
        assert outer is not None and inner is not None, y
        assert outer - inner == pytest.approx(cw, abs=EPS), y


def test_walls_meet_at_a_right_angle_along_the_route_legs(world):
    """Two walls run along each leg, and the legs are perpendicular (a 90 degree corner)."""
    route = places(world)["route-centreline"]["points"]
    legs = [(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(route)]
    assert len(legs) == 2
    long_axes = []
    for w in boxes(world, "wall"):
        sx, sy, _ = w["size"]
        assert sx != sy, w["name"]
        long_axes.append(0 if sx > sy else 1)
    assert sorted(long_axes) == [0, 0, 1, 1]
    for leg, axis in zip(legs, (0, 1), strict=True):
        assert leg[1 - axis] == 0 and leg[axis] != 0, leg
    angle = math.degrees(math.atan2(legs[1][1], legs[1][0]) - math.atan2(legs[0][1], legs[0][0]))
    assert angle == pytest.approx(90.0, abs=world["tolerances"]["angle_deg"])


def test_every_wall_stands_on_floor_and_rises_to_wall_height(world):
    d = world["dimensions"]
    floors = boxes(world, "floor")
    for w in boxes(world, "wall"):
        (x0, x1), (y0, y1), (z0, z1) = bounds(w)
        assert z0 == pytest.approx(0.0, abs=EPS) and z1 == pytest.approx(d["wall_height"], abs=EPS)
        footprint = [(x, y) for x in fine(x0, x1) for y in fine(y0, y1)]
        bare = [p for p in footprint if not any(inside(p, f) for f in floors)]
        assert bare == [], (w["name"], bare[:3])
    for f in floors:
        _, _, (z0, z1) = bounds(f)
        assert z1 == pytest.approx(0.0, abs=EPS)
        assert z1 - z0 == pytest.approx(d["floor_thickness"], abs=EPS)


def test_floor_covers_every_walkable_point_with_no_gap_at_the_seam(world):
    floors = boxes(world, "floor")
    bare = [p for p in clear_area(world) if not any(inside(p, f) for f in floors)]
    assert bare == [], bare[:5]


def test_no_wall_stands_in_the_walkable_area(world):
    walls = boxes(world, "wall")
    blocked = [p for p in clear_area(world) if any(strictly_inside(p, w) for w in walls)]
    assert blocked == [], blocked[:5]


def test_entrance_and_exit_are_open_and_nothing_lies_beyond_them(world):
    p = places(world)
    (ex, _, _), _ = p["entrance"]["points"]
    (_, oy, _), _ = p["exit"]["points"]
    for g in world["geometry"]:
        (x0, _), (_, y1), _ = bounds(g)
        assert x0 >= ex - EPS, g["name"]  # nothing before the entrance line
        assert y1 <= oy + EPS, g["name"]  # nothing past the exit line
    walls = boxes(world, "wall")
    for name in ("entrance", "exit"):
        a, b = p[name]["points"]
        for t in frange(0.0, 1.0, 0.02)[1:-1]:
            point = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            assert not any(strictly_inside(point, w) for w in walls), (name, point)


def test_corner_square_is_walled_on_its_outer_sides_and_open_on_its_inner_sides(world):
    corner = places(world)["corner"]
    (x0, x1), (y0, y1) = corner["x"], corner["y"]
    walls, floors = boxes(world, "wall"), boxes(world, "floor")
    delta = 0.01

    def wall_at(pt):
        return any(strictly_inside(pt, w) for w in walls)

    def open_floor(pt):
        return not wall_at(pt) and any(inside(pt, f) for f in floors)

    inner_x = [x0 + (x1 - x0) * i / 10 for i in range(1, 10)]
    inner_y = [y0 + (y1 - y0) * i / 10 for i in range(1, 10)]
    assert all(wall_at((x, y0 - delta)) for x in inner_x)  # outer side of the first hallway
    assert all(wall_at((x1 + delta, y)) for y in inner_y)  # outer side of the second hallway
    assert all(open_floor((x0 - delta, y)) for y in inner_y)  # back into the first hallway
    assert all(open_floor((x, y1 + delta)) for x in inner_x)  # on into the second hallway
    assert wall_at((x0 - delta, y1 + delta))  # the inside corner is a wall


def test_a_robot_can_turn_in_place_at_the_corner(world):
    """Nothing is nearer the route's turn point than half the clear width, so a footprint
    whose half-diagonal plus wall clearance is under 0.75 m can turn on the spot there."""
    hw = world["dimensions"]["clear_width"] / 2
    vertex = places(world)["route-centreline"]["points"][1]
    gaps = {w["name"]: validate._point_to_box(vertex, w) for w in boxes(world, "wall")}
    assert min(gaps.values()) == pytest.approx(hw, abs=EPS), gaps
    # The inside corner, the nearest inner-wall point, is across the corner square's diagonal.
    inner = min(gaps["wall-inner-first"], gaps["wall-inner-second"])
    assert inner == pytest.approx(hw * math.sqrt(2), abs=EPS)


def test_spawn_has_hallway_open_surroundings_and_the_runs_decision_2_states(world):
    """The spawn sits mid-hallway like hallway-open's, with 1.75 m to the corner square
    and 2.25 m from the corner square to the exit."""
    p, ho = places(world), places(load(HALLWAY))
    spawn, open_spawn = p["spawn-entrance"], ho["spawn-entrance"]
    for pose, w in ((spawn, world), (open_spawn, load(HALLWAY))):
        x, y, _ = pose["position"]
        cw = w["dimensions"]["clear_width"]
        along = 0  # both spawns face +x
        assert pose["yaw_deg"] == 0.0
        assert faces_across(w, along, x, +1) - y == pytest.approx(cw / 2, abs=EPS)
        assert y - faces_across(w, along, x, -1) == pytest.approx(cw / 2, abs=EPS)
    assert spawn["position"][0] - p["entrance"]["reference"][0] == pytest.approx(
        open_spawn["position"][0] - ho["entrance"]["reference"][0], abs=EPS
    )
    assert p["corner"]["x"][0] - spawn["position"][0] == pytest.approx(1.75, abs=EPS)
    assert p["exit"]["reference"][1] - p["corner"]["y"][1] == pytest.approx(2.25, abs=EPS)


def test_units_frame_and_boxes_are_plain(world):
    assert world["units"] == "m"
    assert world["frame"]["handedness"] == "right" and world["frame"]["axes"]["z"] == "up"
    for g in world["geometry"]:
        assert set(g) == {"name", "type", "role", "centre", "size"}  # no rotation field
        assert g["type"] == "box" and all(s > 0 for s in g["size"])
