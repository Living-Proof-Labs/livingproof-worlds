# SPDX-License-Identifier: Apache-2.0
import json
import re
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


WORLD = json.loads((SOURCE / "world.json").read_text())


def test_svg_shows_required_elements():
    svg = (SOURCE / "world.svg").read_text()
    for needle in [
        'class="wall"',
        'class="floor"',
        'class="entrance"',
        'class="exit"',
        'class="passage"',
        'class="centre"',
        'class="yaw"',
        'class="leader"',
        'class="axis"',
        ">IN<",
        ">OUT<",
        "yaw 180°",
        "6.00 m length",
        "1.50 m clear",
        "hallway-open 0.1.0",
    ]:
        assert needle in svg, needle
    assert len(re.findall(r'<circle class="spawn"[^>]*r="6"', svg)) == 3
    for legend in ["wall", "passage", "centreline", "IN entrance", "OUT exit", "spawn + yaw"]:
        assert f">{legend}<" in svg


def test_svg_theming_and_variants():
    auto = (SOURCE / "world.svg").read_text()
    assert "@media (prefers-color-scheme: dark)" in auto
    assert '<rect width="100%"' not in auto  # transparent background
    assert "--amber:#b45309" in auto and "--amber:#fbbf24" in auto
    light, dark = (SOURCE / "world-light.svg").read_text(), (SOURCE / "world-dark.svg").read_text()
    assert "--bg:#ffffff" in light and "prefers-color-scheme" not in light
    assert "--bg:#0d1117" in dark and "prefers-color-scheme" not in dark
    for svg in (auto, light, dark):
        assert "@import" not in svg and "url(" not in svg  # no external fonts
        assert "'DM Sans'" in svg and "'Instrument Serif', Georgia" in svg


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_palette_contrast(theme):
    pal = render.PALETTE[theme]
    for role in render.TEXT_ROLES:
        assert render.contrast(pal[role], pal["bg"]) >= 4.5, role
    for role in render.LINE_ROLES:
        assert render.contrast(pal[role], pal["bg"]) >= 3.0, role
    assert pal["bg"] == {"light": "#ffffff", "dark": "#0d1117"}[theme]


def test_contrast_helper_matches_wcag():
    assert round(render.contrast("#000000", "#ffffff"), 1) == 21.0
    assert round(render.contrast("#767676", "#ffffff"), 2) == 4.54


def test_sizes_and_viewbox():
    svg = (SOURCE / "world.svg").read_text()
    assert re.search(r'viewBox="0 0 800 \d+"', svg)
    assert render.FS_LABEL >= 12 and render.FS_TAG >= 12 and render.FS_DIM == 13
    assert 16 <= render.FS_TITLE <= 18
    sizes = [float(v) for v in re.findall(r"font-size:([\d.]+)px", svg)]
    assert sizes and min(sizes) >= 12


def overlaps(a, b):
    return a[2] > b[0] and b[2] > a[0] and a[3] > b[1] and b[3] > a[1]


def text_collisions(boxes):
    texts = [b for b in boxes if b[0] == "text"]
    solid = [b for b in boxes if b[0] in ("wall", "bar")]
    hits = []
    for i, a in enumerate(texts):
        hits += [(a[1], b[1]) for b in texts[i + 1 :] if overlaps(a[2:], b[2:])]
        hits += [(a[1], b[1]) for b in solid if overlaps(a[2:], b[2:])]
    return hits


def test_no_text_overlaps_text_walls_or_bars():
    lay = render.layout(WORLD)
    assert text_collisions(lay["boxes"]) == []
    for kind, name, x0, y0, x1, y1 in lay["boxes"]:
        if kind == "text":
            assert 0 <= x0 and x1 <= render.VIEW_W and 0 <= y0 and y1 <= lay["height"], name


def test_overlap_check_detects_a_collision():
    boxes = render.layout(WORLD)["boxes"]
    wall = next(b for b in boxes if b[0] == "wall")
    fake = ("text", "fake", wall[2] + 5, wall[3], wall[2] + 50, wall[5])
    assert ("fake", wall[1]) in text_collisions(boxes + [fake])


def test_spawn_labels_sit_outside_the_walls():
    boxes = render.layout(WORLD)["boxes"]
    walls = [b for b in boxes if b[0] == "wall"]
    top, bottom = min(w[3] for w in walls), max(w[5] for w in walls)
    for b in boxes:
        if b[1].startswith("spawn "):
            assert b[5] <= top or b[3] >= bottom, b[1]


def test_yaw_arrows_are_at_least_24px():
    svg = (SOURCE / "world.svg").read_text()
    for poly in re.findall(r'<polygon class="yaw" points="([^"]+)"', svg):
        pts = [tuple(map(float, p.split(","))) for p in poly.split()]
        xs = [p[0] for p in pts]
        assert max(xs) - min(xs) >= 24


def test_accessible_name_and_description():
    svg = (SOURCE / "world.svg").read_text()
    assert 'role="img"' in svg
    assert 'aria-labelledby="hallway-open-0-1-0-title hallway-open-0-1-0-desc"' in svg
    assert f'<desc id="hallway-open-0-1-0-desc">{render.esc(render.describe(WORLD))}</desc>' in svg
    assert "spawn-exit at (2.50, 0.00) yaw 180°" in render.describe(WORLD)


def test_no_footer_line_over_90_characters():
    svg = (SOURCE / "world.svg").read_text()
    for text in re.findall(r"<text[^>]*>([^<]*)</text>", svg):
        assert len(text) <= 90, text


def test_readme_has_every_section_and_generated_tables():
    text = (SOURCE / "README.md").read_text()
    assert render.readme_section_errors(text) == []
    assert "| Floor thickness | 0.10 m |" in text
    assert "| `spawn-exit` | pose | (2.50, 0.00, 0.00), yaw 180.0° |" in text
    assert '<source media="(prefers-color-scheme: dark)" srcset="world-dark.svg">' in text
    assert f'alt="{render.describe(WORLD)}"' in text
    assert "**How to read this diagram.**" in text
    assert "robot-capability-specs/blob/v1.3.0/specs/worlds/hallways.md" in text


def test_missing_readme_fails_check(world_dir):
    (world_dir / "README.md").unlink()
    assert "worlds/hallway-open/0.1.0: missing README.md" in render.check([world_dir])


def test_stale_svg_fails_check(world_dir):
    edit = json.loads((world_dir / "world.json").read_text())
    edit["places"][4]["yaw_deg"] = 10.0  # moves an arrow and changes the label
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
    svg.write_text(svg.read_text().replace("6.00 m length", "6.50 m length"))
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
