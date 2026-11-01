# SPDX-License-Identifier: Apache-2.0
"""Render each world's top-down SVG and README from world.json.

    python tools/render.py           # regenerate world.svg, README.md and release.json
    python tools/render.py --check   # fail if any generated file is missing or stale

Output is deterministic: fixed number formatting, no timestamps, stable ordering.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

ROOT = validate.ROOT
TEMPLATE = ROOT / "tools" / "templates" / "world-README.md"
SPEC_URL = "https://github.com/{repository}/blob/{tag}/{path}"
REQUIRED_SECTIONS = [
    "Purpose",
    "Diagram",
    "Dimensions",
    "Named places",
    "Frame and tolerances",
    "Version and changelog",
    "Provenance and licence",
    "Simulator support",
]
NOTE_SECTIONS = ["Purpose", "Changelog", "Simulator support"]
VIEW_W = 800


def f(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}"
    return text[1:] if text.startswith("-") and float(text) == 0 else text


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


PAD = 16
SIDE_L = 64  # room for the IN tag and the axis glyph
SIDE_R = 160  # room for OUT and the clear-width dimension
FS_LABEL, FS_DIM, FS_TITLE, FS_TAG = 12, 13, 18, 12
TEXT_FONT = "'DM Sans', system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
TITLE_FONT = "'Instrument Serif', Georgia, 'Times New Roman', serif"
CHAR_W = 0.6  # conservative average glyph width in em, used for layout and overlap tests

# Colour roles: "text" roles need 4.5:1, "line" roles 3:1 against the theme background.
PALETTE = {
    # Art's palette (review of PR #2). spawn is not in Art's list and is kept from 50a07ad.
    "light": {
        "bg": "#ffffff",
        "text": "#0f172a",
        "muted": "#475569",
        "wall": "#475569",
        "floor": "#f1f5f9",
        "dim": "#475569",
        "teal": "#0f766e",
        "amber": "#b45309",
        "spawn": "#1d4ed8",
    },
    "dark": {
        "bg": "#0d1117",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
        "wall": "#64748b",
        "floor": "#1e293b",
        "dim": "#94a3b8",
        "teal": "#2dd4bf",
        "amber": "#fbbf24",
        "spawn": "#60a5fa",
    },
}
TEXT_ROLES = ["text", "muted", "teal", "amber", "spawn"]
LINE_ROLES = ["wall", "dim", "teal", "amber", "spawn"]
# The floor is a background fill, not text or a line, so neither 4.5:1 nor 3:1 applies to it
# against the page. The wall edges carry the boundary, so walls must reach 3:1 against the floor.
FILL_ROLES = ["floor"]


def _vars(theme: str) -> str:
    return ";".join(f"--{k}:{v}" for k, v in PALETTE[theme].items())


def _style(mode: str) -> str:
    rules = (
        "text{font-family:" + TEXT_FONT + ";fill:var(--text);font-size:" + f"{FS_LABEL}px" + "}"
        ".title{font-family:" + TITLE_FONT + ";font-size:" + f"{FS_TITLE}px" + "}"
        ".muted{fill:var(--muted)}.dimtext{font-size:" + f"{FS_DIM}px" + ";fill:var(--muted)}"
        ".wall{fill:var(--wall)}.floor{fill:var(--floor)}"
        ".passage{fill:var(--teal);fill-opacity:.10;stroke:var(--teal);stroke-dasharray:6 4}"
        ".centre{stroke:var(--teal);stroke-width:1.5;stroke-dasharray:2 4;fill:none}"
        ".entrance{fill:var(--teal)}.exit{stroke:var(--amber);stroke-width:6;stroke-dasharray:10 6}"
        ".tag-in{fill:var(--teal);font-weight:700}.tag-out{fill:var(--amber);font-weight:700}"
        ".spawn{fill:var(--spawn)}.yaw{fill:var(--spawn);stroke:var(--bg);stroke-width:3;"
        "paint-order:stroke;stroke-linejoin:round}"
        ".leader{stroke:var(--muted);stroke-width:1;fill:none}"
        ".dim{stroke:var(--dim);stroke-width:1;fill:none}"
        ".axis{stroke:var(--text);stroke-width:1.5;fill:none}.axishead{fill:var(--text)}"
    )
    if mode == "auto":
        theme = (
            ":root{" + _vars("light") + "}"
            "@media (prefers-color-scheme: dark){:root{" + _vars("dark") + "}}"
        )
    else:
        theme = ":root{" + _vars(mode) + "}"
    return "<style>" + theme + rules + "</style>"


def text_width(text: str, size: float) -> float:
    return len(text) * size * CHAR_W


def describe(world: dict) -> str:
    """Plain-language description shared by the SVG <desc> and the README alt text."""
    d = world["dimensions"]
    places = {p["name"]: p for p in world["places"]}
    parts = [
        f"Top-down diagram of {world['id']} {world['content_version']}: a "
        f"{f(d['length'])} m long hallway, {f(d['clear_width'])} m clear between two "
        f"{f(d['wall_thickness'])} m walls, open at both ends."
    ]
    if "entrance" in places and "exit" in places:
        parts.append(
            f"Entrance (IN) at x = {f(places['entrance']['reference'][0])}, "
            f"exit (OUT) at x = {f(places['exit']['reference'][0])}."
        )
    if "passage" in places:
        pa = places["passage"]
        parts.append(
            f"Passage from y = {f(pa['y'][0])} to {f(pa['y'][1])} m around the centreline."
        )
    spawns = [p for p in world["places"] if p["type"] == "pose"]
    if spawns:
        parts.append(
            "Spawns: "
            + "; ".join(
                f"{p['name']} at ({f(p['position'][0])}, {f(p['position'][1])}) "
                f"yaw {f(p['yaw_deg'], 0)}°"
                for p in spawns
            )
            + "."
        )
    return " ".join(parts)


def layout(world: dict) -> dict:
    """Compute every element position. Returns SVG body parts and a box model for tests."""
    d = world["dimensions"]
    floor = next(g for g in world["geometry"] if g["role"] == "floor")
    xmin = floor["centre"][0] - floor["size"][0] / 2
    xmax = floor["centre"][0] + floor["size"][0] / 2
    ymin = floor["centre"][1] - floor["size"][1] / 2
    ymax = floor["centre"][1] + floor["size"][1] / 2
    scale = (VIEW_W - SIDE_L - SIDE_R) / (xmax - xmin)
    places = {p["name"]: p for p in world["places"]}
    spawns = [p for p in world["places"] if p["type"] == "pose"]
    above = spawns[0::2]
    below = spawns[1::2]
    boxes = []  # (kind, name, x0, y0, x1, y1)
    body = []

    def tbox(name, x, y, text, size, anchor="start"):
        w = text_width(text, size)
        x0 = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
        boxes.append(("text", name, x0, y - size * 0.8, x0 + w, y + size * 0.25))
        return x0, w

    # Title and legend rows.
    y = PAD + FS_TITLE
    title = f"{world['title']} · {world['id']} {world['content_version']} · top view"
    tbox("title", PAD, y, title, FS_TITLE)
    body.append(f'<text class="title" x="{PAD}" y="{f(y, 1)}">{esc(title)}</text>')
    y += 26
    lx = PAD
    legend = [
        ("wall", '<rect class="wall" x="{x}" y="{y0}" width="16" height="8"/>'),
        ("passage", '<rect class="passage" x="{x}" y="{y0}" width="16" height="8"/>'),
        ("centreline", '<line class="centre" x1="{x}" y1="{ym}" x2="{x16}" y2="{ym}"/>'),
        ("IN entrance", '<rect class="entrance" x="{x6}" y="{y0}" width="5" height="10"/>'),
        ("OUT exit", '<line class="exit" x1="{x8}" y1="{y0}" x2="{x8}" y2="{y10}"/>'),
        ("spawn + yaw", '<circle class="spawn" cx="{x8}" cy="{ym}" r="4"/>'),
    ]
    for label, shape in legend:
        body.append(
            shape.format(
                x=f(lx, 1),
                x6=f(lx + 6, 1),
                x8=f(lx + 8, 1),
                x16=f(lx + 16, 1),
                y0=f(y - 9, 1),
                ym=f(y - 4, 1),
                y10=f(y + 1, 1),
            )
        )
        tbox("legend " + label, lx + 22, y, label, FS_LABEL)
        body.append(f'<text x="{f(lx + 22, 1)}" y="{f(y, 1)}">{esc(label)}</text>')
        lx += 22 + text_width(label, FS_LABEL) + 18
    y += 14

    def spawn_label(p):
        return f"{p['name']} ({f(p['position'][0])}, {f(p['position'][1])}) · yaw {f(p['yaw_deg'], 0)}°"

    label_row_above = y + FS_LABEL + 4 if above else y
    top = label_row_above + (14 if above else 8)

    def px(x):
        return SIDE_L + (x - xmin) * scale

    def py(v):
        return top + (ymax - v) * scale

    bottom = py(ymin)
    label_row_below = bottom + 14 + FS_LABEL if below else bottom

    # Floor outline and walls.
    body.append(
        f'<rect class="floor" x="{f(px(xmin), 1)}" y="{f(py(ymax), 1)}" '
        f'width="{f((xmax - xmin) * scale, 1)}" height="{f((ymax - ymin) * scale, 1)}"/>'
    )
    for g in world["geometry"]:
        if g["role"] != "wall":
            continue
        (cx, cy, _), (sx, sy, _) = g["centre"], g["size"]
        x0, y0 = px(cx - sx / 2), py(cy + sy / 2)
        w, h = sx * scale, sy * scale
        boxes.append(("wall", g["name"], x0, y0, x0 + w, y0 + h))
        body.append(
            f'<rect class="wall" x="{f(x0, 1)}" y="{f(y0, 1)}" width="{f(w, 1)}" height="{f(h, 1)}"/>'
        )
    if "passage" in places:
        pa = places["passage"]
        body.append(
            f'<rect class="passage" x="{f(px(pa["x"][0]), 1)}" y="{f(py(pa["y"][1]), 1)}" '
            f'width="{f((pa["x"][1] - pa["x"][0]) * scale, 1)}" '
            f'height="{f((pa["y"][1] - pa["y"][0]) * scale, 1)}"/>'
        )
    if "passage-centreline" in places:
        pts = " ".join(
            f"{f(px(x), 1)},{f(py(v), 1)}" for x, v, _ in places["passage-centreline"]["points"]
        )
        body.append(f'<polyline class="centre" points="{pts}"/>')
    # Entrance: solid teal bar + IN. Exit: dashed amber bar + OUT.
    for name, tag in (("entrance", "IN"), ("exit", "OUT")):
        if name not in places:
            continue
        (x0, y0, _), (x1, y1, _) = places[name]["points"]
        bx = px(x0)
        ya, yb = py(max(y0, y1)), py(min(y0, y1))
        boxes.append(("bar", name, bx - 3, ya, bx + 3, yb))
        if name == "entrance":
            body.append(
                f'<rect class="entrance" x="{f(bx - 3, 1)}" y="{f(ya, 1)}" width="6" '
                f'height="{f(yb - ya, 1)}"/>'
            )
            tx, anchor, cls = bx - 10, "end", "tag-in"
        else:
            body.append(
                f'<line class="exit" x1="{f(bx, 1)}" y1="{f(ya, 1)}" x2="{f(bx, 1)}" y2="{f(yb, 1)}"/>'
            )
            tx, anchor, cls = bx + 10, "start", "tag-out"
        ty = py(0) + FS_TAG * 0.35
        tbox(f"tag {tag}", tx, ty, tag, FS_TAG, anchor)
        body.append(
            f'<text class="{cls}" x="{f(tx, 1)}" y="{f(ty, 1)}" text-anchor="{anchor}">{tag}</text>'
        )
    # Spawns: filled yaw arrows with a halo, labels outside the walls with leader lines.
    for p in spawns:
        x, v, _ = p["position"]
        sx, sy = px(x), py(v)
        yaw = math.radians(p["yaw_deg"])
        ux, uy = math.cos(yaw), -math.sin(yaw)  # SVG y points down
        tip = (sx + 30 * ux, sy + 30 * uy)
        base = (sx + 6 * ux, sy + 6 * uy)
        nx, ny = -uy, ux
        shaft = 3
        head = 9
        neck = (sx + 20 * ux, sy + 20 * uy)
        pts = [
            (base[0] + shaft * nx, base[1] + shaft * ny),
            (neck[0] + shaft * nx, neck[1] + shaft * ny),
            (neck[0] + head * nx, neck[1] + head * ny),
            tip,
            (neck[0] - head * nx, neck[1] - head * ny),
            (neck[0] - shaft * nx, neck[1] - shaft * ny),
            (base[0] - shaft * nx, base[1] - shaft * ny),
        ]
        body.append(
            '<polygon class="yaw" points="'
            + " ".join(f"{f(a, 1)},{f(b, 1)}" for a, b in pts)
            + '"/>'
        )
        body.append(f'<circle class="spawn" cx="{f(sx, 1)}" cy="{f(sy, 1)}" r="6"/>')
        label = spawn_label(p)
        ly = label_row_above if p in above else label_row_below
        w = text_width(label, FS_LABEL)
        lx = min(max(sx - w / 2, PAD), VIEW_W - PAD - w)
        tbox("spawn " + p["name"], lx, ly, label, FS_LABEL)
        edge = ly + 4 if p in above else ly - FS_LABEL
        body.append(
            f'<line class="leader" x1="{f(sx, 1)}" y1="{f(sy, 1)}" x2="{f(sx, 1)}" y2="{f(edge, 1)}"/>'
        )
        body.append(f'<text x="{f(lx, 1)}" y="{f(ly, 1)}">{esc(label)}</text>')
    # Dimensions: muted lines with ticks.
    yd = label_row_below + 22
    x0, x1 = px(xmin), px(xmax)
    body.append(
        f'<line class="dim" x1="{f(x0, 1)}" y1="{f(yd, 1)}" x2="{f(x1, 1)}" y2="{f(yd, 1)}"/>'
    )
    for x in (x0, x1):
        body.append(
            f'<line class="dim" x1="{f(x, 1)}" y1="{f(yd - 5, 1)}" x2="{f(x, 1)}" y2="{f(yd + 5, 1)}"/>'
        )
    length_text = f"{f(d['length'])} m length"
    ty = yd + 6 + FS_DIM
    tbox("dim length", (x0 + x1) / 2, ty, length_text, FS_DIM, "middle")
    body.append(
        f'<text class="dimtext" x="{f((x0 + x1) / 2, 1)}" y="{f(ty, 1)}" '
        f'text-anchor="middle">{length_text}</text>'
    )
    hw = d["clear_width"] / 2
    xd = px(xmax) + 40
    body.append(
        f'<line class="dim" x1="{f(xd, 1)}" y1="{f(py(hw), 1)}" x2="{f(xd, 1)}" y2="{f(py(-hw), 1)}"/>'
    )
    for v in (hw, -hw):
        body.append(
            f'<line class="dim" x1="{f(xd - 5, 1)}" y1="{f(py(v), 1)}" x2="{f(xd + 5, 1)}" y2="{f(py(v), 1)}"/>'
        )
    clear_text = f"{f(d['clear_width'])} m clear"
    cy = py(0) + FS_DIM * 0.35
    tbox("dim clear", xd + 8, cy, clear_text, FS_DIM)
    body.append(f'<text class="dimtext" x="{f(xd + 8, 1)}" y="{f(cy, 1)}">{clear_text}</text>')
    # Axis glyph in the bottom-left corner, beside the length dimension.
    ax, ay = PAD + 4, ty
    body.append(
        f'<line class="axis" x1="{f(ax, 1)}" y1="{f(ay, 1)}" x2="{f(ax + 22, 1)}" y2="{f(ay, 1)}"/>'
    )
    body.append(
        f'<line class="axis" x1="{f(ax, 1)}" y1="{f(ay, 1)}" x2="{f(ax, 1)}" y2="{f(ay - 22, 1)}"/>'
    )
    body.append(
        f'<polygon class="axishead" points="{f(ax + 28, 1)},{f(ay, 1)} {f(ax + 21, 1)},{f(ay - 4, 1)} '
        f'{f(ax + 21, 1)},{f(ay + 4, 1)}"/>'
    )
    body.append(
        f'<polygon class="axishead" points="{f(ax, 1)},{f(ay - 28, 1)} {f(ax - 4, 1)},{f(ay - 21, 1)} '
        f'{f(ax + 4, 1)},{f(ay - 21, 1)}"/>'
    )
    tbox("axis x", ax + 31, ay + 4, "+x", FS_LABEL)
    tbox("axis y", ax + 7, ay - 24, "+y", FS_LABEL)
    body.append(f'<text x="{f(ax + 31, 1)}" y="{f(ay + 4, 1)}">+x</text>')
    body.append(f'<text x="{f(ax + 7, 1)}" y="{f(ay - 24, 1)}">+y</text>')
    height = math.ceil(ty + PAD)
    return {"body": body, "boxes": boxes, "height": height}


def render_svg(world: dict, mode: str = "auto") -> str:
    lay = layout(world)
    sid = f"{world['id']}-{world['content_version'].replace('.', '-')}"
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {lay["height"]}" '
        f'width="{VIEW_W}" height="{lay["height"]}" role="img" '
        f'aria-labelledby="{sid}-title {sid}-desc">',
        f'<title id="{sid}-title">{esc(world["title"])}, {esc(world["id"])} '
        f"{esc(world['content_version'])}: top-down diagram</title>",
        f'<desc id="{sid}-desc">{esc(describe(world))}</desc>',
        _style(mode),
        *lay["body"],
        "</svg>",
    ]
    return "\n".join(out) + "\n"


def contrast(a: str, b: str) -> float:
    def lum(hex_colour):
        rgb = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def coords(p: dict) -> str:
    def pt(v):
        return "(" + ", ".join(f(c) for c in v) + ")"

    if p["type"] == "segment":
        return f"{pt(p['points'][0])} to {pt(p['points'][1])}; reference {pt(p['reference'])}"
    if p["type"] == "region":
        return f"x = [{f(p['x'][0])}, {f(p['x'][1])}], y = [{f(p['y'][0])}, {f(p['y'][1])}]"
    if p["type"] == "polyline":
        return " → ".join(pt(v) for v in p["points"])
    return f"{pt(p['position'])}, yaw {f(p['yaw_deg'], 1)}°"


def read_notes(directory: Path) -> dict[str, str]:
    path = directory / "notes.md"
    if not path.is_file():
        raise SystemExit(f"{path.relative_to(ROOT)}: missing (hand-written README sections)")
    parts = re.split(r"^## (.+)$", path.read_text(), flags=re.M)
    notes = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}
    missing = [s for s in NOTE_SECTIONS if not notes.get(s)]
    if missing:
        raise SystemExit(f"{path.relative_to(ROOT)}: missing section(s) {missing}")
    return notes


def render_readme(world: dict, notes: dict[str, str]) -> str:
    d = world["dimensions"]
    spec = world["specification"]
    rows = [
        ("Clear width (between inner wall faces)", d["clear_width"]),
        ("Length (floor and walls along +x)", d["length"]),
        ("Wall height (from floor top)", d["wall_height"]),
        ("Wall thickness", d["wall_thickness"]),
        ("Exterior width", d["exterior_width"]),
        ("Floor thickness", d["floor_thickness"]),
    ]
    dims = "\n".join(f"| {label} | {f(v)} m |" for label, v in rows)
    places = "\n".join(f"| `{p['name']}` | {p['type']} | {coords(p)} |" for p in world["places"])
    assets = world["provenance"]["assets"]
    asset_text = (
        "\n".join(f"- `{a['path']}`: {a['source']} ({a['license']})" for a in assets)
        if assets
        else "No third-party assets."
    )
    frame = world["frame"]
    return Template(TEMPLATE.read_text()).substitute(
        id=world["id"],
        version=world["content_version"],
        title=world["title"],
        description=world["description"],
        spec_url=SPEC_URL.format(**spec),
        spec_repo=spec["repository"],
        spec_tag=spec["tag"],
        spec_commit=spec["commit"],
        document_revision=spec["document_revision"],
        contract_revision=spec["world_contract_revision"],
        purpose=notes["Purpose"],
        dimensions=dims,
        places=places,
        origin=frame["origin"],
        axis_x=frame["axes"]["x"],
        axis_y=frame["axes"]["y"],
        axis_z=frame["axes"]["z"],
        pose=frame["pose"],
        tol_distance=f(world["tolerances"]["distance_m"]),
        tol_angle=f(world["tolerances"]["angle_deg"], 1),
        changelog=notes["Changelog"],
        authors=", ".join(world["provenance"]["authors"]),
        method=world["provenance"]["method"],
        assets=asset_text,
        license=world["license"],
        simulators=notes["Simulator support"],
        alt=describe(world).replace('"', "&quot;"),
        wall_thickness=f(d["wall_thickness"]),
        wall_height=f(d["wall_height"]),
        floor_thickness=f(d["floor_thickness"]),
    )


def readme_section_errors(text: str) -> list[str]:
    present = set(re.findall(r"^## (.+)$", text, flags=re.M))
    return [f"missing section '{s}'" for s in REQUIRED_SECTIONS if s not in present]


def outputs(directory: Path) -> dict[str, str]:
    world = json.loads((directory / "world.json").read_text())
    return {
        "world.svg": render_svg(world, "auto"),
        "world-light.svg": render_svg(world, "light"),
        "world-dark.svg": render_svg(world, "dark"),
        "README.md": render_readme(world, read_notes(directory)),
    }


def check(directories: list[Path]) -> list[str]:
    errors = []
    for directory in directories:
        rel = directory.relative_to(ROOT)
        readme = directory / "README.md"
        if not readme.is_file():
            errors.append(f"{rel}: missing README.md")
        else:
            errors += [f"{rel}/README.md: {e}" for e in readme_section_errors(readme.read_text())]
        try:
            expected = outputs(directory)
        except SystemExit as exc:
            errors.append(str(exc))
            continue
        for name, text in expected.items():
            path = directory / name
            if path.is_file() and path.read_text() != text:
                errors.append(f"{rel}/{name}: out of date with world.json; run task render")
            elif not path.is_file() and name != "README.md":
                errors.append(f"{rel}: missing {name}; run task render")
    return errors


def world_dirs() -> list[Path]:
    return [p.parent for p in validate.world_files()]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--check"]:
        errors = check(world_dirs())
        for e in errors:
            print(e, file=sys.stderr)
        print(f"render check: {'FAIL' if errors else 'OK'} ({len(world_dirs())} world(s))")
        return 1 if errors else 0
    for directory in world_dirs():
        for name, text in outputs(directory).items():
            (directory / name).write_text(text)
        validate.write_manifest(directory)
        print(f"rendered {directory.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
