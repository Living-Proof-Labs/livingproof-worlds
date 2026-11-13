# SPDX-License-Identifier: Apache-2.0
"""Validate every world description against the schema and its own geometry.

Unknown fields, geometry types and place types are reported as UNSUPPORTED
errors; they are never ignored.

Every world must meet the layout rules of robot-capability-specs world contract
0.3.0 ("Any layout"): axis-aligned box floors and walls that do not overlap,
``entrance`` and ``exit`` segments across the clear width, a route polyline from
the entrance to the exit that stays at least half the clear width from every
wall, and ``spawn-entrance`` on the route facing along it. A
``livingproof-world/0.1`` world is also a straight hallway along x, with the
stricter checks that held before 0.2 existed.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "world.schema.json").read_text())
RELEASE_SCHEMA = json.loads((ROOT / "schema" / "release.schema.json").read_text())
MANIFEST = "release.json"
EPS = 1e-9
SPAWN_CLEARANCE = 0.25
STRAIGHT = "livingproof-world/0.1"
# The route polyline each format names. hallway-open 0.1.0 predates route-centreline.
ROUTE = {STRAIGHT: "passage-centreline", "livingproof-world/0.2": "route-centreline"}
REQUIRED_PLACES = {"entrance": "segment", "exit": "segment", "spawn-entrance": "pose"}


def _label(error) -> str:
    return "/".join(str(p) for p in error.absolute_path) or "<root>"


def schema_errors(world: dict) -> list[str]:
    validator = Draft202012Validator(SCHEMA)
    messages = []
    for error in sorted(validator.iter_errors(world), key=lambda e: list(e.absolute_path)):
        if error.validator == "additionalProperties":
            extra = sorted(set(error.instance) - set(error.schema.get("properties", {})))
            messages.append(f"UNSUPPORTED field(s) {extra} at {_label(error)}")
        elif (
            error.validator in ("enum", "const")
            and error.absolute_path
            and (error.absolute_path[-1] == "type")
        ):
            messages.append(f"UNSUPPORTED type {error.instance!r} at {_label(error)}")
        elif error.validator == "oneOf":
            kind = error.instance.get("type") if isinstance(error.instance, dict) else None
            branch = next(
                (b for b in error.schema["oneOf"] if b["properties"]["type"]["const"] == kind),
                None,
            )
            if branch is None:
                continue  # the enum error on "type" already reports it as UNSUPPORTED
            extra = sorted(set(error.instance) - set(branch["properties"]))
            missing = sorted(set(branch["required"]) - set(error.instance))
            if extra:
                messages.append(f"UNSUPPORTED field(s) {extra} at {_label(error)}")
            if missing:
                messages.append(f"INVALID {kind} place at {_label(error)}: missing {missing}")
            elif not extra:
                index = error.schema["oneOf"].index(branch)
                inner = [e for e in error.context if e.relative_schema_path[0] == index]
                detail = inner[0].message if inner else "does not match its type"
                where = "/".join(str(p) for p in inner[0].relative_path) if inner else ""
                messages.append(f"INVALID {kind} place at {_label(error)}: {where} {detail}")
        else:
            messages.append(f"INVALID {_label(error)}: {error.message}")
    return messages


def geometry_errors(world: dict) -> list[str]:
    names = [g["name"] for g in world["geometry"]] + [p["name"] for p in world["places"]]
    if len(names) != len(set(names)):
        return ["INVALID names: geometry and place names must be unique"]
    errors = straight_hallway_errors(world) if world["format"] == STRAIGHT else []
    return errors + [e for e in layout_errors(world) if e not in errors]


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _nearest_on_leg(p, a, b) -> tuple[float, float]:
    """Floor-plane distance from p to leg a-b, and the fraction along a-b of the nearest point."""
    ab = (b[0] - a[0], b[1] - a[1])
    t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / (ab[0] ** 2 + ab[1] ** 2)
    t = max(0.0, min(1.0, t))
    return _dist(p, (a[0] + t * ab[0], a[1] + t * ab[1])), t


def _point_to_box(p, box) -> float:
    dx = max(abs(p[0] - box["centre"][0]) - box["size"][0] / 2, 0.0)
    dy = max(abs(p[1] - box["centre"][1]) - box["size"][1] / 2, 0.0)
    return math.hypot(dx, dy)


def _legs_cross(a, b, c, d) -> bool:
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    return cross(c, d, a) * cross(c, d, b) < 0 and cross(a, b, c) * cross(a, b, d) < 0


def _leg_to_box(a, b, box) -> float:
    """Floor-plane distance from leg a-b to the footprint of an axis-aligned box."""
    (cx, cy, _), (sx, sy, _) = box["centre"], box["size"]
    hx, hy = sx / 2, sy / 2
    corners = [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]
    if _point_to_box(a, box) == 0 or _point_to_box(b, box) == 0:
        return 0.0
    if any(_legs_cross(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4)):
        return 0.0
    return min(
        _point_to_box(a, box),
        _point_to_box(b, box),
        *(_nearest_on_leg(c, a, b)[0] for c in corners),
    )


def route_station(route: dict, point) -> tuple[float, float, float]:
    """(distance to the route, distance along it to the nearest point, route length)."""
    best, walked = (math.inf, 0.0), 0.0
    for a, b in itertools.pairwise(route["points"]):
        dist, t = _nearest_on_leg(point, a, b)
        if dist < best[0] - EPS:
            best = (dist, walked + t * _dist(a, b))
        walked += _dist(a, b)
    return best[0], best[1], walked


def route_length(world: dict, start: str = "spawn-entrance") -> float:
    """Distance along the route from the point nearest ``start`` to the route's end."""
    places = {p["name"]: p for p in world["places"]}
    _, station, length = route_station(places[ROUTE[world["format"]]], places[start]["position"])
    return length - station


def layout_errors(world: dict) -> list[str]:
    """Rules for any layout of axis-aligned walls (specs world contract 0.3.0)."""
    errors = []
    d = world["dimensions"]
    tol, ang_tol = world["tolerances"]["distance_m"], world["tolerances"]["angle_deg"]
    half_w = d["clear_width"] / 2
    walls = [g for g in world["geometry"] if g["role"] == "wall"]
    for g in world["geometry"]:
        (_, _, cz), (sx, sy, sz) = g["centre"], g["size"]
        if g["role"] == "floor":
            if abs(cz + sz / 2) > EPS or abs(sz - d["floor_thickness"]) > EPS:
                errors.append(f"INVALID {g['name']}: top must be z = 0, thickness floor_thickness")
        elif g["role"] == "wall":
            if abs(cz - sz / 2) > EPS or abs(sz - d["wall_height"]) > EPS:
                errors.append(f"INVALID {g['name']}: must rise from z = 0 to wall_height")
            if abs(min(sx, sy) - d["wall_thickness"]) > EPS:
                errors.append(f"INVALID {g['name']}: must be wall_thickness thick")
        else:
            errors.append(f"UNSUPPORTED role {g['role']!r} for {g['name']}")
    errors += _overlap_errors(world["geometry"])
    places = {p["name"]: p for p in world["places"]}
    route_name = ROUTE[world["format"]]
    required = {**REQUIRED_PLACES, route_name: "polyline"}
    for name, kind in required.items():
        if name not in places:
            errors.append(f"INVALID places: missing {kind} {name!r}")
        elif places[name]["type"] != kind:
            errors.append(f"INVALID {name}: must be a {kind}")
    if errors:
        return errors
    for name in ("entrance", "exit"):
        (x0, y0, z0), (x1, y1, z1) = places[name]["points"]
        ref = places[name]["reference"]
        if abs(z0) > EPS or abs(z1) > EPS or abs(ref[2]) > EPS:
            errors.append(f"INVALID {name}: must lie on the floor, z = 0")
        if abs(_dist((x0, y0), (x1, y1)) - d["clear_width"]) > EPS:
            errors.append(f"INVALID {name}: must span the clear width")
        if _dist(ref, ((x0 + x1) / 2, (y0 + y1) / 2)) > EPS:
            errors.append(f"INVALID {name}: reference must be the segment midpoint")
    route = places[route_name]
    points = route["points"]
    legs = list(itertools.pairwise(points))
    if any(abs(pt[2]) > EPS for pt in points):
        errors.append(f"INVALID {route_name}: must lie on the floor, z = 0")
    if any(_dist(a, b) <= EPS for a, b in legs):
        errors.append(f"INVALID {route_name}: repeated point")
        return errors
    if _dist(points[0], places["entrance"]["reference"]) > tol:
        errors.append(f"INVALID {route_name}: must start at the entrance reference point")
    if _dist(points[-1], places["exit"]["reference"]) > tol:
        errors.append(f"INVALID {route_name}: must end at the exit reference point")
    for w in walls:
        if any(_leg_to_box(a, b, w) < half_w - tol for a, b in legs):
            errors.append(f"INVALID {route_name}: passes closer than clear_width/2 to {w['name']}")
    for p in world["places"]:
        if p["type"] == "pose":
            gap = min((_point_to_box(p["position"], w) for w in walls), default=math.inf)
            if gap < SPAWN_CLEARANCE - EPS:
                errors.append(f"INVALID {p['name']}: spawn closer than 0.25 m to a wall")
    spawn = places["spawn-entrance"]
    dist, station, _ = route_station(route, spawn["position"])
    if dist > tol:
        errors.append(f"INVALID spawn-entrance: must lie on {route_name}")
    else:
        walked = 0.0
        for a, b in legs:
            if station <= walked + _dist(a, b) + EPS:
                heading = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                diff = abs((spawn["yaw_deg"] - heading + 180) % 360 - 180)
                if diff > ang_tol:
                    errors.append(f"INVALID spawn-entrance: must face along {route_name}")
                break
            walked += _dist(a, b)
    return errors


def _overlap_errors(boxes: list[dict]) -> list[str]:
    errors = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            overlap = [
                min(ca + sa / 2, cb + sb / 2) - max(ca - sa / 2, cb - sb / 2)
                for ca, sa, cb, sb in zip(a["centre"], a["size"], b["centre"], b["size"])
            ]
            if all(o > EPS for o in overlap):
                errors.append(f"INVALID {a['name']} overlaps {b['name']}")
    return errors


def straight_hallway_errors(world: dict) -> list[str]:
    """Checks for a livingproof-world/0.1 straight hallway along x, unchanged from v1.1.8."""
    errors = []
    d = world["dimensions"]
    half_w, half_l = d["clear_width"] / 2, d["length"] / 2
    if abs(d["exterior_width"] - (d["clear_width"] + 2 * d["wall_thickness"])) > EPS:
        errors.append("INVALID dimensions: exterior_width != clear_width + 2 * wall_thickness")
    for g in world["geometry"]:
        (cx, cy, cz), (sx, sy, sz) = g["centre"], g["size"]
        if abs(sx - d["length"]) > EPS or abs(cx) > EPS:
            errors.append(f"INVALID {g['name']}: must span x = ±length/2")
        if g["role"] == "floor":
            if abs(cz + sz / 2) > EPS or abs(sz - d["floor_thickness"]) > EPS:
                errors.append(f"INVALID {g['name']}: top must be z = 0, thickness floor_thickness")
            if abs(sy - d["exterior_width"]) > EPS or abs(cy) > EPS:
                errors.append(f"INVALID {g['name']}: must span the exterior width")
        elif g["role"] == "wall":
            inner = abs(cy) - sy / 2
            if abs(inner - half_w) > EPS or abs(sy - d["wall_thickness"]) > EPS:
                errors.append(f"INVALID {g['name']}: inner face must be |y| = clear_width/2")
            if abs(cz - sz / 2) > EPS or abs(sz - d["wall_height"]) > EPS:
                errors.append(f"INVALID {g['name']}: must rise from z = 0 to wall_height")
        else:
            errors.append(f"UNSUPPORTED role {g['role']!r} for {g['name']}")
    errors += _overlap_errors(world["geometry"])
    places = {p["name"]: p for p in world["places"]}
    passage = places.get("passage")
    for p in world["places"]:
        if p["type"] == "pose" and passage:
            x, y, _ = p["position"]
            if not (
                passage["x"][0] <= x <= passage["x"][1] and passage["y"][0] <= y <= passage["y"][1]
            ):
                errors.append(f"INVALID {p['name']}: spawn outside passage")
        if p["type"] == "pose" and half_w - abs(p["position"][1]) < SPAWN_CLEARANCE - EPS:
            errors.append(f"INVALID {p['name']}: spawn closer than 0.25 m to a wall")
        if p["type"] == "segment" and abs(abs(p["reference"][0]) - half_l) > EPS:
            errors.append(f"INVALID {p['name']}: must lie on an open end x = ±length/2")
        if p["type"] == "segment":
            (x0, y0, z0), (x1, y1, z1) = p["points"]
            rx = p["reference"][0]
            if abs(x0 - rx) > EPS or abs(x1 - rx) > EPS or abs(z0) > EPS or abs(z1) > EPS:
                errors.append(f"INVALID {p['name']}: endpoints must lie at x = {rx}, z = 0")
            if abs(min(y0, y1) + half_w) > EPS or abs(max(y0, y1) - half_w) > EPS:
                errors.append(f"INVALID {p['name']}: endpoints must span y = ±clear_width/2")
            if abs(p["reference"][1] - (y0 + y1) / 2) > EPS or abs(p["reference"][2]) > EPS:
                errors.append(f"INVALID {p['name']}: reference must be the segment midpoint")
    return errors


def validate(world: dict, path: Path | None = None) -> list[str]:
    errors = schema_errors(world)
    if (
        path is not None
        and not errors
        and (path.parent.name != world["content_version"] or path.parent.parent.name != world["id"])
    ):
        errors.append(f"INVALID {path}: must live at worlds/<id>/<content_version>/world.json")
    if errors:
        return errors
    errors = geometry_errors(world)
    if path is not None:
        errors += provenance_errors(world, path.parent)
    return errors


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance_errors(world: dict, directory: Path) -> list[str]:
    """Check the release manifest and every declared asset against files on disk."""
    errors = []
    manifest_path = directory / MANIFEST
    if not manifest_path.is_file():
        return [f"INVALID {directory.name}: missing {MANIFEST}"]
    manifest = json.loads(manifest_path.read_text())
    for error in Draft202012Validator(RELEASE_SCHEMA).iter_errors(manifest):
        errors.append(f"INVALID {MANIFEST} {_label(error)}: {error.message}")
    if errors:
        return errors
    if (manifest["id"], manifest["content_version"]) != (world["id"], world["content_version"]):
        errors.append(f"INVALID {MANIFEST}: id/content_version does not match world.json")
    on_disk = sorted(
        str(f.relative_to(directory))
        for f in directory.rglob("*")
        if f.is_file() and f.name != MANIFEST
    )
    for name in sorted(set(on_disk) - set(manifest["files"])):
        errors.append(f"INVALID {MANIFEST}: {name} is not listed")
    for name, digest in sorted(manifest["files"].items()):
        path = directory / name
        if not path.is_file():
            errors.append(f"INVALID {MANIFEST}: listed file {name} is missing")
        elif sha256(path) != digest:
            errors.append(f"INVALID {MANIFEST}: checksum mismatch for {name}")
    for asset in world["provenance"]["assets"]:
        path = directory / asset["path"]
        if not path.is_file():
            errors.append(f"INVALID asset {asset['path']}: file is missing")
        elif sha256(path) != asset["sha256"]:
            errors.append(f"INVALID asset {asset['path']}: checksum mismatch")
    return errors


def write_manifest(directory: Path) -> None:
    world = json.loads((directory / "world.json").read_text())
    files = {
        str(f.relative_to(directory)): sha256(f)
        for f in sorted(directory.rglob("*"))
        if f.is_file() and f.name != MANIFEST
    }
    manifest = {"id": world["id"], "content_version": world["content_version"], "files": files}
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")


def world_files() -> list[Path]:
    return sorted((ROOT / "worlds").glob("*/*/world.json"))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--write-manifest"]:
        for directory in argv[1:]:
            write_manifest(Path(directory))
        return 0
    failed = False
    for path in world_files():
        errors = validate(json.loads(path.read_text()), path)
        rel = path.relative_to(ROOT)
        for message in errors:
            print(f"{rel}: {message}", file=sys.stderr)
        print(f"{rel}: {'FAIL' if errors else 'OK'}")
        failed |= bool(errors)
    if not world_files():
        print("no worlds found", file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
