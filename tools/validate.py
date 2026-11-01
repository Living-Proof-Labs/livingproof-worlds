# SPDX-License-Identifier: Apache-2.0
"""Validate every world description against the schema and its own geometry.

Unknown fields, geometry types and place types are reported as UNSUPPORTED
errors; they are never ignored.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "world.schema.json").read_text())
RELEASE_SCHEMA = json.loads((ROOT / "schema" / "release.schema.json").read_text())
MANIFEST = "release.json"
EPS = 1e-9
SPAWN_CLEARANCE = 0.25


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
    boxes = world["geometry"]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            overlap = [
                min(ca + sa / 2, cb + sb / 2) - max(ca - sa / 2, cb - sb / 2)
                for ca, sa, cb, sb in zip(a["centre"], a["size"], b["centre"], b["size"])
            ]
            if all(o > EPS for o in overlap):
                errors.append(f"INVALID {a['name']} overlaps {b['name']}")
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
    return errors


def validate(world: dict, path: Path | None = None) -> list[str]:
    errors = schema_errors(world)
    if path is not None and not errors:
        if path.parent.name != world["content_version"] or path.parent.parent.name != world["id"]:
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
