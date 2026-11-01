# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import validate  # noqa: E402

WORLD_PATH = ROOT / "worlds" / "hallway-open" / "0.1.0" / "world.json"
SPEC = ROOT / "tests" / "fixtures" / "robot-capability-specs-0ca62aa-hallways.md"
SPEC_SHA256 = "f495782baa945483e4b07feada060f6db706cde7f704bd271fffc293636e0e8f"


@pytest.fixture
def world():
    return json.loads(WORLD_PATH.read_text())


def num(text):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", text.replace("±", ""))]


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(validate.SCHEMA)


def test_every_world_validates():
    assert validate.world_files() == [WORLD_PATH]
    assert validate.main() == 0


def test_vendored_spec_is_the_pinned_revision(world):
    assert hashlib.sha256(SPEC.read_bytes()).hexdigest() == SPEC_SHA256
    text = SPEC.read_text()
    assert "Document revision 0.2.0" in text
    assert world["specification"]["commit"] in SPEC.name
    assert world["specification"]["document_revision"] == "0.2.0"


def test_dimensions_match_spec_canonical_table(world):
    text = SPEC.read_text()
    row = next(line for line in text.splitlines() if line.startswith("| `hallway-open` / `"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[0] == f"`{world['id']}` / `{world['content_version']}`"
    width, length, height, thickness, exterior = (num(c)[0] for c in cells[1:])
    d = world["dimensions"]
    assert (d["clear_width"], d["length"], d["wall_height"], d["wall_thickness"]) == (
        width,
        length,
        height,
        thickness,
    )
    assert d["exterior_width"] == exterior
    floor = re.search(r"is (\d+\.\d+) m\s+thick", text)
    assert d["floor_thickness"] == float(floor.group(1))
    tol = world["tolerances"]
    assert "within 0.01 m" in text and tol["distance_m"] == 0.01
    assert "0.5 degrees" in text and tol["angle_deg"] == 0.5


def test_named_places_match_spec_table(world):
    text = SPEC.read_text()
    rows = re.findall(r"^\| `([a-z-]+)` \| (\w+) \| (.+) \|$", text, re.M)
    spec = {name: (kind, num(re.sub(r" \([^)`]*\)", "", defn))) for name, kind, defn in rows}
    places = {p["name"]: p for p in world["places"]}
    assert set(places) == set(spec)
    for name, (kind, values) in spec.items():
        p = places[name]
        assert p["type"] == kind
        if kind == "segment":
            got = [*p["points"][0], *p["points"][1], *p["reference"]]
        elif kind == "region":
            got = [*p["x"], *p["y"]]
        elif kind == "polyline":
            got = [c for pt in p["points"] for c in pt]
        else:
            got = [*p["position"], p["yaw_deg"]]
        assert got == values, name


def test_floor_and_walls_match_frame(world):
    assert validate.geometry_errors(world) == []
    roles = sorted(g["role"] for g in world["geometry"])
    assert roles == ["floor", "wall", "wall"]


def test_provenance_and_licence(world):
    assert world["license"] == "Apache-2.0"
    assert world["provenance"]["authors"]
    assert world["provenance"]["assets"] == []


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda w: w.update(doors=[]), "UNSUPPORTED field(s) ['doors'] at <root>"),
        (
            lambda w: w["geometry"].append(
                {**w["geometry"][1], "name": "post", "type": "cylinder"}
            ),
            "UNSUPPORTED type 'cylinder' at geometry/3/type",
        ),
        (
            lambda w: w["geometry"][0].update(material="carpet"),
            "UNSUPPORTED field(s) ['material'] at geometry/0",
        ),
        (
            lambda w: w["places"].append({"name": "door", "type": "portal"}),
            "UNSUPPORTED type 'portal' at places/7/type",
        ),
        (
            lambda w: w["places"][4].update(height=1.0),
            "UNSUPPORTED field(s) ['height'] at places/4",
        ),
        (
            lambda w: w["dimensions"].update(ceiling_height=3.0),
            "UNSUPPORTED field(s) ['ceiling_height'] at dimensions",
        ),
        (
            lambda w: w["provenance"].update(notes="x"),
            "UNSUPPORTED field(s) ['notes'] at provenance",
        ),
    ],
)
def test_unknown_features_are_rejected_not_ignored(world, mutate, expected):
    bad = copy.deepcopy(world)
    mutate(bad)
    errors = validate.validate(bad)
    assert expected in errors, errors


def test_geometry_inconsistent_with_dimensions_is_rejected(world):
    bad = copy.deepcopy(world)
    bad["geometry"][1]["centre"][1] = 0.9
    assert any("wall-left" in e for e in validate.validate(bad))
    bad = copy.deepcopy(world)
    bad["places"][4]["position"][1] = 0.7
    assert "INVALID spawn-entrance: spawn outside passage" in validate.validate(bad)


def test_world_must_live_at_its_versioned_path(world, tmp_path):
    wrong = tmp_path / "hallway-open" / "0.2.0" / "world.json"
    assert any("must live at" in e for e in validate.validate(world, wrong))
