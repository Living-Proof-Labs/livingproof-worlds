# SPDX-License-Identifier: Apache-2.0
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import render  # noqa: E402
import validate  # noqa: E402

SOURCE = ROOT / "worlds" / "hallway-open" / "0.1.0"


@pytest.fixture
def world_dir(tmp_path, monkeypatch):
    directory = tmp_path / "worlds" / "hallway-open" / "0.1.0"
    shutil.copytree(SOURCE, directory)
    monkeypatch.setattr(render, "ROOT", tmp_path)
    return directory


def test_committed_docs_are_current():
    assert render.check(render.world_dirs()) == []


def test_render_is_deterministic():
    first = render.outputs(SOURCE)
    assert render.outputs(SOURCE) == first
    assert first["world.svg"] == (SOURCE / "world.svg").read_text()


def test_svg_shows_required_elements():
    svg = (SOURCE / "world.svg").read_text()
    for needle in [
        'class="wall"',
        'class="floor"',
        'class="entrance"',
        'class="exit"',
        'class="passage"',
        'class="centre"',
        'class="arrow"',
        "spawn-exit",
        "length 6.00 m",
        "clear 1.50 m",
        "hallway-open 0.1.0",
    ]:
        assert needle in svg, needle
    assert svg.count('class="spawn"') == 3


def test_readme_has_every_section_and_generated_tables():
    text = (SOURCE / "README.md").read_text()
    assert render.readme_section_errors(text) == []
    assert "| Floor thickness | 0.10 m |" in text
    assert "| `spawn-exit` | pose | (2.50, 0.00, 0.00), yaw 180.0° |" in text
    assert "![Top-down diagram of hallway-open 0.1.0](world.svg)" in text
    assert "robot-capability-specs/blob/v1.3.0/specs/worlds/hallways.md" in text


def test_missing_readme_fails_check(world_dir):
    (world_dir / "README.md").unlink()
    assert "worlds/hallway-open/0.1.0: missing README.md" in render.check([world_dir])


def test_stale_svg_fails_check(world_dir):
    edit = json.loads((world_dir / "world.json").read_text())
    edit["places"][4]["yaw_deg"] = 10.0
    (world_dir / "world.json").write_text(json.dumps(edit))
    errors = render.check([world_dir])
    assert (
        "worlds/hallway-open/0.1.0/world.svg: out of date with world.json; run task render"
        in errors
    )
    assert (
        "worlds/hallway-open/0.1.0/README.md: out of date with world.json; run task render"
        in errors
    )


def test_hand_edited_svg_fails_check(world_dir):
    svg = world_dir / "world.svg"
    svg.write_text(svg.read_text().replace("length 6.00 m", "length 6.50 m"))
    assert any("world.svg: out of date" in e for e in render.check([world_dir]))


def test_missing_svg_fails_check(world_dir):
    (world_dir / "world.svg").unlink()
    assert "worlds/hallway-open/0.1.0: missing world.svg; run task render" in render.check(
        [world_dir]
    )


def test_missing_readme_section_fails_check(world_dir):
    readme = world_dir / "README.md"
    readme.write_text(readme.read_text().replace("## Simulator support", "## Engines"))
    errors = render.check([world_dir])
    assert "worlds/hallway-open/0.1.0/README.md: missing section 'Simulator support'" in errors


def test_missing_notes_section_fails_check(world_dir):
    notes = world_dir / "notes.md"
    notes.write_text(notes.read_text().replace("## Changelog", "## History"))
    assert any("missing section(s) ['Changelog']" in e for e in render.check([world_dir]))


def test_manifest_must_cover_generated_files(world_dir):
    manifest = json.loads((world_dir / "release.json").read_text())
    del manifest["files"]["world.svg"]
    (world_dir / "release.json").write_text(json.dumps(manifest))
    path = world_dir / "world.json"
    errors = validate.validate(json.loads(path.read_text()), path)
    assert "INVALID release.json: world.svg is not listed" in errors


def test_render_rewrites_outputs_and_manifest(world_dir, monkeypatch):
    (world_dir / "world.svg").write_text("stale")
    monkeypatch.setattr(render, "world_dirs", lambda: [world_dir])
    assert render.main([]) == 0
    assert render.check([world_dir]) == []
    path = world_dir / "world.json"
    assert validate.validate(json.loads(path.read_text()), path) == []
