# SPDX-License-Identifier: Apache-2.0
"""Validate every world description against the schema and its own geometry.

Unknown fields, geometry types and place types are reported as UNSUPPORTED
errors; they are never ignored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "world.schema.json").read_text())
EPS = 1e-9


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
            if missing or not extra:
                messages.append(f"INVALID {kind} place at {_label(error)}: missing {missing}")
        else:
            messages.append(f"INVALID {_label(error)}: {error.message}")
    return messages


def geometry_errors(world: dict) -> list[str]:
    errors = []
    d = world["dimensions"]
    half_w, half_l = d["clear_width"] / 2, d["length"] / 2
    if abs(d["exterior_width"] - (d["clear_width"] + 2 * d["wall_thickness"])) > EPS:
        errors.append("INVALID dimensions: exterior_width != clear_width + 2 * wall_thickness")
    names = [g["name"] for g in world["geometry"]] + [p["name"] for p in world["places"]]
    if len(names) != len(set(names)):
        errors.append("INVALID names: geometry and place names must be unique")
    for g in world["geometry"]:
        (cx, cy, cz), (sx, sy, sz) = g["centre"], g["size"]
        if abs(sx - d["length"]) > EPS or abs(cx) > EPS:
            errors.append(f"INVALID {g['name']}: must span x = ±length/2")
        if g["role"] == "floor":
            if abs(cz + sz / 2) > EPS or abs(sz - d["floor_thickness"]) > EPS:
                errors.append(f"INVALID {g['name']}: top must be z = 0, thickness floor_thickness")
            if abs(sy - d["exterior_width"]) > EPS or abs(cy) > EPS:
                errors.append(f"INVALID {g['name']}: must span the exterior width")
        else:
            inner = abs(cy) - sy / 2
            if abs(inner - half_w) > EPS or abs(sy - d["wall_thickness"]) > EPS:
                errors.append(f"INVALID {g['name']}: inner face must be |y| = clear_width/2")
            if abs(cz - sz / 2) > EPS or abs(sz - d["wall_height"]) > EPS:
                errors.append(f"INVALID {g['name']}: must rise from z = 0 to wall_height")
    places = {p["name"]: p for p in world["places"]}
    passage = places.get("passage")
    for p in world["places"]:
        if p["type"] == "pose" and passage:
            x, y, _ = p["position"]
            if not (
                passage["x"][0] <= x <= passage["x"][1] and passage["y"][0] <= y <= passage["y"][1]
            ):
                errors.append(f"INVALID {p['name']}: spawn outside passage")
        if p["type"] == "segment" and abs(abs(p["reference"][0]) - half_l) > EPS:
            errors.append(f"INVALID {p['name']}: must lie on an open end x = ±length/2")
    return errors


def validate(world: dict, path: Path | None = None) -> list[str]:
    errors = schema_errors(world)
    if path is not None and not errors:
        if path.parent.name != world["content_version"] or path.parent.parent.name != world["id"]:
            errors.append(f"INVALID {path}: must live at worlds/<id>/<content_version>/world.json")
    return errors or geometry_errors(world)


def world_files() -> list[Path]:
    return sorted((ROOT / "worlds").glob("*/*/world.json"))


def main() -> int:
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
