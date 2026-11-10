# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import validate

WORLD_PATH = ROOT / "worlds" / "hallway-open" / "0.1.0" / "world.json"
SPEC = ROOT / "tests" / "fixtures" / "robot-capability-specs-v1.3.0-hallways.md"
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
    assert world["specification"]["tag"] in SPEC.name
    assert world["specification"]["commit"] == "ad53368c11b322b787f6b71023bbe87dec839c0b"
    assert world["specification"]["document_revision"] == "0.2.0"


def spec_dimension_deviations(world, text):
    row = next(line for line in text.splitlines() if line.startswith("| `hallway-open` / `"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[0] == f"`{world['id']}` / `{world['content_version']}`"
    spec = dict(
        zip(
            ["clear_width", "length", "wall_height", "wall_thickness", "exterior_width"],
            (num(c)[0] for c in cells[1:]),
        )
    )
    spec["floor_thickness"] = float(re.search(r"is (\d+\.\d+) m\s+thick", text).group(1))
    tol = world["tolerances"]["distance_m"]
    return [k for k, v in spec.items() if abs(world["dimensions"][k] - v) > tol + 1e-9]


def test_dimensions_within_tolerance_of_spec_canonical_table(world):
    text = SPEC.read_text()
    assert spec_dimension_deviations(world, text) == []
    tol = world["tolerances"]
    assert "within 0.01 m" in text and tol["distance_m"] == 0.01
    assert "0.5 degrees" in text and tol["angle_deg"] == 0.5


def test_dimension_beyond_tolerance_is_reported(world):
    bad = copy.deepcopy(world)
    bad["dimensions"]["clear_width"] = 1.52
    bad["dimensions"]["floor_thickness"] = 0.105
    assert spec_dimension_deviations(bad, SPEC.read_text()) == ["clear_width"]


def test_named_places_match_spec_table(world):
    text = SPEC.read_text()
    rows = re.findall(r"^\| `([a-z-]+)` \| (\w+) \| (.+) \|$", text, re.MULTILINE)
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


def test_overlapping_walls_are_rejected(world):
    bad = copy.deepcopy(world)
    bad["geometry"].append({**bad["geometry"][1], "name": "wall-extra"})
    assert "INVALID wall-left overlaps wall-extra" in validate.geometry_errors(bad)


def test_walls_resting_on_floor_do_not_count_as_overlap(world):
    assert not any("overlaps" in e for e in validate.geometry_errors(world))


def test_spawn_clearance_from_walls_is_enforced(world):
    bad = copy.deepcopy(world)
    passage = next(p for p in bad["places"] if p["name"] == "passage")
    passage["y"] = [-0.7, 0.7]
    bad["places"][5]["position"][1] = 0.6
    assert "INVALID spawn-centre: spawn closer than 0.25 m to a wall" in validate.geometry_errors(
        bad
    )


def test_entrance_and_exit_must_be_at_open_ends(world):
    bad = copy.deepcopy(world)
    bad["places"][1]["reference"][0] = 2.5
    assert "INVALID exit: must lie on an open end x = ±length/2" in validate.geometry_errors(bad)


@pytest.fixture
def release(tmp_path):
    directory = tmp_path / "hallway-open" / "0.1.0"
    shutil.copytree(WORLD_PATH.parent, directory)
    return directory


def edit_json(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


def errors_for(directory):
    path = directory / "world.json"
    return validate.validate(json.loads(path.read_text()), path)


def test_release_manifest_checksum_is_recomputed(release):
    manifest = json.loads((release / "release.json").read_text())
    assert manifest["id"] == "hallway-open" and manifest["content_version"] == "0.1.0"
    assert manifest["files"]["world.json"] == validate.sha256(release / "world.json")
    assert errors_for(release) == []


def test_missing_manifest_is_rejected(release):
    (release / "release.json").unlink()
    assert errors_for(release) == ["INVALID 0.1.0: missing release.json"]


def test_changed_content_fails_checksum(release):
    edit_json(release / "world.json", lambda w: w.update(title="Changed"))
    assert "INVALID release.json: checksum mismatch for world.json" in errors_for(release)


def test_unlisted_file_is_rejected(release):
    (release / "extra.txt").write_text("x")
    assert "INVALID release.json: extra.txt is not listed" in errors_for(release)


def test_listed_missing_file_is_rejected(release):
    edit_json(release / "release.json", lambda m: m["files"].update({"mesh.obj": "0" * 64}))
    assert "INVALID release.json: listed file mesh.obj is missing" in errors_for(release)


def test_manifest_version_must_match_world(release):
    edit_json(release / "release.json", lambda m: m.update(content_version="0.1.1"))
    assert "INVALID release.json: id/content_version does not match world.json" in errors_for(
        release
    )


def test_manifest_without_version_is_rejected(release):
    edit_json(release / "release.json", lambda m: m.pop("content_version"))
    assert any("'content_version' is a required property" in e for e in errors_for(release))


def test_manifest_with_unknown_field_is_rejected(release):
    edit_json(release / "release.json", lambda m: m.update(signed=True))
    assert any("release.json" in e and "signed" in e for e in errors_for(release))


def add_asset(release, **overrides):
    (release / "texture.png").write_bytes(b"png")
    asset = {
        "path": "texture.png",
        "source": "https://example.org/texture.png",
        "license": "CC0-1.0",
        "sha256": hashlib.sha256(b"png").hexdigest(),
    }
    asset.update(overrides)
    asset = {k: v for k, v in asset.items() if v is not None}
    edit_json(release / "world.json", lambda w: w["provenance"]["assets"].append(asset))
    validate.write_manifest(release)


def test_declared_asset_with_licence_source_and_checksum_passes(release):
    add_asset(release)
    assert errors_for(release) == []


@pytest.mark.parametrize("field", ["license", "source", "sha256"])
def test_asset_missing_provenance_field_is_rejected(release, field):
    add_asset(release, **{field: None})
    assert any(f"'{field}' is a required property" in e for e in errors_for(release))


@pytest.mark.parametrize("field", ["license", "source"])
def test_asset_with_empty_provenance_field_is_rejected(release, field):
    add_asset(release, **{field: ""})
    assert any("provenance/assets/0" in e for e in errors_for(release))


def test_asset_checksum_mismatch_is_rejected(release):
    add_asset(release, sha256="1" * 64)
    assert "INVALID asset texture.png: checksum mismatch" in errors_for(release)


def test_declared_asset_file_missing_is_rejected(release):
    add_asset(release)
    (release / "texture.png").unlink()
    validate.write_manifest(release)
    assert "INVALID asset texture.png: file is missing" in errors_for(release)


def test_unknown_role_is_rejected_by_schema_and_geometry(world):
    bad = copy.deepcopy(world)
    bad["geometry"][1]["role"] = "ceiling"
    assert "UNSUPPORTED role 'ceiling' for wall-left" in validate.geometry_errors(bad)
    assert any("geometry/1/role" in e for e in validate.validate(bad))


@pytest.mark.parametrize(
    "change, expected",
    [
        (lambda e: e["points"][1].__setitem__(1, 0.5), "endpoints must span y = ±clear_width/2"),
        (lambda e: e["points"][0].__setitem__(1, -0.9), "endpoints must span y = ±clear_width/2"),
        (lambda e: e["points"][0].__setitem__(0, -2.9), "endpoints must lie at x = -3.0, z = 0"),
        (lambda e: e["points"][1].__setitem__(2, 0.1), "endpoints must lie at x = -3.0, z = 0"),
        (lambda e: e["reference"].__setitem__(1, 0.2), "reference must be the segment midpoint"),
    ],
)
def test_entrance_endpoints_are_enforced(world, change, expected):
    bad = copy.deepcopy(world)
    change(bad["places"][0])
    assert f"INVALID entrance: {expected}" in validate.geometry_errors(bad)


def test_exit_endpoints_are_enforced(world):
    bad = copy.deepcopy(world)
    bad["places"][1]["points"] = [[3.0, -0.75, 0.0], [3.0, 0.6, 0.0]]
    assert "INVALID exit: endpoints must span y = ±clear_width/2" in validate.geometry_errors(bad)
