# SPDX-License-Identifier: Apache-2.0
"""Any layout of axis-aligned walls (robot-capability-specs #40, Part A step 2)."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import validate

HALLWAY = ROOT / "worlds" / "hallway-open" / "0.1.0"
FIXTURES = ROOT / "tests" / "fixtures" / "worlds"
# Copy of robot-capability-specs test/fixtures/worlds/l-shaped.world.json from PR #47 at
# 57ea03a88dab8174a9e8f22d97d8c242db2451fc. Replace with the released copy once specs releases.
SPECS_L = ROOT / "tests" / "fixtures" / "robot-capability-specs-l-shaped.world.json"
SPECS_L_SHA256 = "ceea5c9b25665b9874b39ebd1c259b8811e999d72b5a4219780f226b09450e40"
# Every file of hallway-open 0.1.0 as released (release.json at v1.1.8, the same bytes since
# v1.0.0), plus release.json itself. Released world versions are immutable; this must never change.
RELEASED = {
    "README.md": "b7e1f00ccfbba4523577eeb380cfdf977587715e568fce501de86a43b65f2bb2",
    "notes.md": "a77c0f00eb413595303a4d248e7fdca89be2c2937b1452c5fa33955d0f00cbac",
    "world-dark.svg": "d2648d57b4c17e6b6850cef552d671dc5e2504ec0001c654a9ad7e1b28138bf0",
    "world-light.svg": "cbe20f52ec5cc80c24a741e1093cf8bc6369f82aabc39698d2e300d60e3de48c",
    "world.json": "d60bb8aa6a72c8403fb6674cc9d803962c1484bc3e163527988e8c57ccec775c",
    "world.svg": "e988e2c1d7dabe909f74d7b3afdb953ac91be7066c499ff760daf5b6cf0d4072",
}
RELEASE_JSON_SHA256 = "ad7663f5aa853830d3910a43b32c183173095d6d5494b6983e69dd3e8371c135"


def load(path):
    return json.loads(Path(path).read_text())


@pytest.fixture
def l_world():
    return load(FIXTURES / "l-shaped.json")


def test_hallway_open_is_byte_identical_to_its_release():
    files = sorted(f.name for f in HALLWAY.iterdir() if f.name != "release.json")
    assert files == sorted(RELEASED)
    for name, digest in RELEASED.items():
        assert hashlib.sha256((HALLWAY / name).read_bytes()).hexdigest() == digest, name
    assert load(HALLWAY / "release.json")["files"] == RELEASED
    assert validate.sha256(HALLWAY / "release.json") == RELEASE_JSON_SHA256


def test_hallway_open_meets_the_layout_rules_with_its_route():
    world = load(HALLWAY / "world.json")
    assert world["format"] == "livingproof-world/0.1"
    assert validate.ROUTE[world["format"]] == "passage-centreline"
    assert validate.layout_errors(world) == []
    assert validate.route_length(world, "passage-centreline") == 5.5


def test_l_shaped_world_validates(l_world):
    assert l_world["format"] == "livingproof-world/0.2"
    assert validate.validate(l_world) == []
    assert validate.route_length(l_world, "route-centreline") == 5.5
    route = next(p for p in l_world["places"] if p["name"] == "route-centreline")
    assert len(route["points"]) == 3
    assert "length" not in l_world["dimensions"]


@pytest.mark.parametrize(
    "name, expected",
    [
        ("rotated-wall", "UNSUPPORTED field(s) ['yaw_deg'] at geometry/3"),
        ("missing-exit", "INVALID places: missing segment 'exit'"),
        ("short-route", "INVALID polyline place at places/3: points"),
        ("route-through-wall", "INVALID route-centreline: passes closer than clear_width/2"),
    ],
)
def test_negative_fixtures_fail(name, expected):
    errors = validate.validate(load(FIXTURES / "invalid" / f"{name}.json"))
    assert any(e.startswith(expected) for e in errors), errors


def test_negative_fixtures_differ_from_the_valid_one_only_where_named(l_world):
    for path in sorted((FIXTURES / "invalid").glob("*.json")):
        bad = load(path)
        assert bad["format"] == l_world["format"]
        assert bad["geometry"] != l_world["geometry"] or bad["places"] != l_world["places"]


def mutate(world, change):
    bad = copy.deepcopy(world)
    change(bad)
    return validate.validate(bad)


def place(world, name):
    return next(p for p in world["places"] if p["name"] == name)


@pytest.mark.parametrize(
    "change, expected",
    [
        (lambda w: w["geometry"][2].update(type="oriented-box"), "UNSUPPORTED type"),
        (lambda w: w["places"].remove(place(w, "entrance")), "missing segment 'entrance'"),
        (lambda w: w["places"].remove(place(w, "spawn-entrance")), "missing pose"),
        (lambda w: place(w, "route-centreline").update(name="passage-centreline"), "missing"),
        (lambda w: w["dimensions"].update(length=6.0), "INVALID dimensions"),
        (lambda w: w.update(format="livingproof-world/0.3"), "INVALID format"),
        (
            lambda w: w["geometry"][5].update(centre=[-0.825, 1.875, 1.25], size=[0.15, 2.25, 2.5]),
            "overlaps",
        ),
        (lambda w: place(w, "route-centreline")["points"].pop(), "must end at the exit"),
        (
            lambda w: place(w, "route-centreline")["points"].insert(1, [-3.0, 0.0, 0.0]),
            "repeated point",
        ),
        (lambda w: place(w, "spawn-entrance").update(position=[-2.5, 0.3, 0.0]), "must lie on"),
        (lambda w: place(w, "spawn-entrance").update(yaw_deg=90.0), "must face along"),
        (
            lambda w: place(w, "exit")["points"].__setitem__(1, [0.5, 3.0, 0.0]),
            "must span the clear width",
        ),
        (lambda w: w["geometry"][3]["size"].__setitem__(2, 2.0), "wall_height"),
        (lambda w: w["geometry"][3]["size"].__setitem__(0, 0.3), "wall_thickness"),
        (lambda w: w["places"].append({**place(w, "corner"), "name": "entrance"}), "unique"),
        (lambda w: w["frame"]["axes"].update(z="down"), "INVALID frame/axes/z"),
        (lambda w: w["frame"].update(pose="yaw in radians"), "INVALID frame/pose"),
    ],
)
def test_layout_rules_reject_bad_worlds(l_world, change, expected):
    errors = mutate(l_world, change)
    assert any(expected in e for e in errors), errors


def test_straight_hallway_checks_still_apply_to_format_0_1():
    world = load(HALLWAY / "world.json")
    errors = mutate(world, lambda w: w["dimensions"].pop("length"))
    assert any("length" in e for e in errors), errors
    errors = mutate(world, lambda w: w["places"][1]["reference"].__setitem__(0, 2.5))
    assert "INVALID exit: must lie on an open end x = ±length/2" in errors


def test_l_shaped_fixture_matches_the_specs_fixture(l_world):
    assert hashlib.sha256(SPECS_L.read_bytes()).hexdigest() == SPECS_L_SHA256
    specs = load(SPECS_L)
    for key in ("id", "content_version", "units", "dimensions", "geometry", "places", "tolerances"):
        assert l_world[key] == specs[key], key


def test_format_0_2_yaw_is_counterclockwise_from_x(l_world):
    # The facing rule reads yaw in degrees about +z from +x: 0 faces +x along the first leg.
    turned = copy.deepcopy(l_world)
    place(turned, "spawn-entrance")["yaw_deg"] = 360.0
    assert validate.validate(turned) == []
    place(turned, "spawn-entrance")["yaw_deg"] = -90.0
    assert any("must face along" in e for e in validate.validate(turned))
