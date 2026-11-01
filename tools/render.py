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
SCALE = 100  # pixels per metre
MARGIN = 90


def f(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}"
    return "0.00"[: len(text)] if text.startswith("-") and float(text) == 0 else text


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(world: dict) -> str:
    d = world["dimensions"]
    floor = next(g for g in world["geometry"] if g["role"] == "floor")
    xmin = floor["centre"][0] - floor["size"][0] / 2
    xmax = floor["centre"][0] + floor["size"][0] / 2
    ymin = floor["centre"][1] - floor["size"][1] / 2
    ymax = floor["centre"][1] + floor["size"][1] / 2
    width = round((xmax - xmin) * SCALE + 2 * MARGIN + 60)
    height = round((ymax - ymin) * SCALE + 2 * MARGIN + 40)

    def px(x: float) -> str:
        return f((x - xmin) * SCALE + MARGIN, 1)

    def py(y: float) -> str:
        return f((ymax - y) * SCALE + MARGIN + 40, 1)

    def rect(x0, y0, x1, y1, cls):
        return (
            f'<rect class="{cls}" x="{px(x0)}" y="{py(y1)}" '
            f'width="{f((x1 - x0) * SCALE, 1)}" height="{f((y1 - y0) * SCALE, 1)}"/>'
        )

    places = {p["name"]: p for p in world["places"]}
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="13">',
        f"<title>{esc(world['id'])} {esc(world['content_version'])}: top-down view</title>",
        "<style>"
        ".floor{fill:#eef2f3;stroke:#9aa5a8}.wall{fill:#4b5563}"
        ".passage{fill:#0f766e;fill-opacity:.12;stroke:#0f766e;stroke-dasharray:6 4}"
        ".centre{stroke:#0f766e;stroke-width:1.5;stroke-dasharray:2 4}"
        ".entrance{stroke:#2563eb;stroke-width:4}.exit{stroke:#dc2626;stroke-width:4}"
        ".spawn{fill:#f59e0b;stroke:#78350f}.arrow{stroke:#78350f;stroke-width:2;fill:none}"
        ".dim{stroke:#111827;stroke-width:1}.label{fill:#111827}.small{font-size:11px}"
        "</style>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text class="label" x="{MARGIN}" y="28" font-size="16" font-weight="bold">'
        f"{esc(world['id'])} {esc(world['content_version'])} — top view, +x right, +y up, "
        f"metres</text>",
        rect(xmin, ymin, xmax, ymax, "floor"),
    ]
    for g in world["geometry"]:
        if g["role"] == "wall":
            (cx, cy, _), (sx, sy, _) = g["centre"], g["size"]
            out.append(rect(cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2, "wall"))
    if "passage" in places:
        p = places["passage"]
        out.append(rect(p["x"][0], p["y"][0], p["x"][1], p["y"][1], "passage"))
    if "passage-centreline" in places:
        pts = " ".join(f"{px(x)},{py(y)}" for x, y, _ in places["passage-centreline"]["points"])
        out.append(f'<polyline class="centre" points="{pts}" fill="none"/>')
    for name in ("entrance", "exit"):
        if name in places:
            (x0, y0, _), (x1, y1, _) = places[name]["points"]
            rx = places[name]["reference"][0]
            anchor = "start" if rx < 0 else "end"
            tx = px(rx)
            out.append(
                f'<line class="{name}" x1="{px(x0)}" y1="{py(y0)}" x2="{px(x1)}" y2="{py(y1)}"/>'
            )
            out.append(
                f'<text class="label" x="{tx}" y="{py(ymax + 0.12)}" text-anchor="{anchor}">'
                f"{name} (x = {f(rx)})</text>"
            )
    for p in world["places"]:
        if p["type"] != "pose":
            continue
        x, y, _ = p["position"]
        yaw = math.radians(p["yaw_deg"])
        ex, ey = x + 0.35 * math.cos(yaw), y + 0.35 * math.sin(yaw)
        hx, hy = ex - 0.1 * math.cos(yaw), ey - 0.1 * math.sin(yaw)
        nx, ny = -0.06 * math.sin(yaw), 0.06 * math.cos(yaw)
        out.append(f'<circle class="spawn" cx="{px(x)}" cy="{py(y)}" r="7"/>')
        out.append(f'<line class="arrow" x1="{px(x)}" y1="{py(y)}" x2="{px(ex)}" y2="{py(ey)}"/>')
        out.append(
            f'<polyline class="arrow" points="{px(hx + nx)},{py(hy + ny)} {px(ex)},{py(ey)} '
            f'{px(hx - nx)},{py(hy - ny)}"/>'
        )
        out.append(
            f'<text class="label small" x="{px(x)}" y="{py(y - 0.22)}" text-anchor="middle">'
            f"{esc(p['name'])} ({f(x)}, {f(y)}) {f(p['yaw_deg'], 0)}°</text>"
        )
    # Dimension lines: length below the floor, clear width to the right.
    yd = ymin - 0.35
    out.append(f'<line class="dim" x1="{px(xmin)}" y1="{py(yd)}" x2="{px(xmax)}" y2="{py(yd)}"/>')
    for x in (xmin, xmax):
        out.append(
            f'<line class="dim" x1="{px(x)}" y1="{py(yd - 0.08)}" x2="{px(x)}" y2="{py(yd + 0.08)}"/>'
        )
    out.append(
        f'<text class="label" x="{px((xmin + xmax) / 2)}" y="{py(yd - 0.22)}" '
        f'text-anchor="middle">length {f(d["length"])} m</text>'
    )
    xd = xmax + 0.35
    hw = d["clear_width"] / 2
    out.append(f'<line class="dim" x1="{px(xd)}" y1="{py(-hw)}" x2="{px(xd)}" y2="{py(hw)}"/>')
    for y in (-hw, hw):
        out.append(
            f'<line class="dim" x1="{px(xd - 0.08)}" y1="{py(y)}" x2="{px(xd + 0.08)}" y2="{py(y)}"/>'
        )
    out.append(
        f'<text class="label small" x="{px(xd + 0.12)}" y="{py(0)}" dominant-baseline="middle">'
        f"clear {f(d['clear_width'])} m</text>"
    )
    out.append(
        f'<text class="label small" x="{MARGIN}" y="{height - 12}">'
        f"walls {f(d['wall_thickness'])} m thick, {f(d['wall_height'])} m high; floor "
        f"{f(d['floor_thickness'])} m thick, top at z = 0. Spec "
        f"{esc(world['specification']['repository'])} {esc(world['specification']['tag'])}."
        "</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


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
    )


def readme_section_errors(text: str) -> list[str]:
    present = set(re.findall(r"^## (.+)$", text, flags=re.M))
    return [f"missing section '{s}'" for s in REQUIRED_SECTIONS if s not in present]


def outputs(directory: Path) -> dict[str, str]:
    world = json.loads((directory / "world.json").read_text())
    return {
        "world.svg": render_svg(world),
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
