# livingproof-worlds

**Start here: documentation** — [manual source and preview instructions](docs/manual.md).
Publication is pending deployment and live verification.

Versioned, engine-neutral robot test worlds for Living Proof Labs simulators.

A world here describes static geometry, named places (such as an entrance, an
exit and the usable passage), the coordinate convention, spawn locations, and
the provenance and licence of every asset. Simulator projects such as
[livingproof-sim-mujoco](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco)
and [livingproof-sim-gazebo](https://github.com/Living-Proof-Labs/livingproof-sim-gazebo)
pin a released world version and translate it into their own engine; engine
conversion lives in those adapters, not here.

## Responsibilities

- [robot-capability-specs](https://github.com/Living-Proof-Labs/robot-capability-specs)
  defines what a world must demonstrate: user stories, scenarios, acceptance
  criteria and required evidence.
- This repository supplies the versioned world definitions that satisfy them.
- Simulator repositories load a pinned world, run it, and produce observations
  and rendered evidence.
- Robot adapters come later and use the same worlds without changing them.

This is deliberately not a universal scene language. A world supports only what
its specification requires, and engine-specific differences are documented.
Equivalent geometry does not imply identical physics.

## Worlds

| World | Content version | Specification |
| --- | --- | --- |
| [`hallway-open`](worlds/hallway-open/0.1.0/world.json) | `0.1.0` | robot-capability-specs v1.3.0 `specs/worlds/hallways.md`, document revision 0.2.0 |

Each world lives at `worlds/<id>/<content_version>/` as `world.json` plus a
`release.json` manifest. `task test` checks three layers, without running a simulator:

1. **Schema:** [`schema/world.schema.json`](schema/world.schema.json) is closed, so an
   unknown field, geometry type or place type fails with `UNSUPPORTED` instead
   of being ignored.
2. **Semantic geometry:** every world meets the layout rules of the
   robot-capability-specs world contract 0.3.0 ("Any layout"). Floors and walls are
   axis-aligned boxes that do not overlap. `entrance` and `exit` are segments across
   the clear width. A route polyline runs from the entrance to the exit at least half
   the clear width from every wall. `spawn-entrance` lies on the route, facing along it,
   and every spawn is at least 0.25 m from the walls. Format
   `livingproof-world/0.1` is a straight hallway along x, with route
   `passage-centreline`: its entrance and exit must also sit on the open ends, and its
   dimensions must be within 0.01 m of the canonical table in a vendored copy of the
   pinned spec. Format `livingproof-world/0.2` is any layout of axis-aligned walls,
   such as two hallways meeting at a corner, with route `route-centreline`. A
   synthetic L-shaped test world in `tests/fixtures/worlds/` shows it validates.
3. **Provenance:** every asset declares a licence, a source and a sha256, and
   `release.json` ([schema](schema/release.schema.json)) records the id, content
   version and the sha256 of every file, recomputed on each run. After an
   intended change in a new version directory, regenerate it with
   `python tools/validate.py --write-manifest worlds/<id>/<version>`.

The first world is an open hallway with a named entrance, exit and usable passage, defined by
[robot-capability-specs #18](https://github.com/Living-Proof-Labs/robot-capability-specs/pull/18).
Both simulators will consume the same pinned release and check floor and wall
collisions with a simple test object; no robot or controller is involved.

## Add a world

1. Make sure a spec in robot-capability-specs defines the world, then pin its tag
   and commit in `specification`.
2. Create `worlds/<id>/<content_version>/world.json` that validates against
   [`schema/world.schema.json`](schema/world.schema.json). Only add schema
   features that the spec needs; anything else must stay `UNSUPPORTED`.
3. Write `notes.md` beside it with the hand-written sections `## Purpose`,
   `## Changelog` and `## Simulator support`.
4. Run `task render`. It generates `world.svg` and `README.md` (from
   [`tools/templates/world-README.md`](tools/templates/world-README.md)) and
   rewrites `release.json` checksums. Commit all of them.
5. Add tests for the spec's canonical values in `tests/`, then run `task check`
   and `task test`. `task check` fails if a README or SVG is missing, stale or
   lacks a section, or if `release.json` doesn't cover every file.

Never edit a released version directory. Change a world by adding a new version.

## Development

With Git, Docker Compose v2 and Task 3.54.0 installed: `task setup`, then
`task check` and `task test` (or `task verify`). Behind a proxy that blocks
`deb.debian.org`, set `APT_MIRROR` (for example `https://cloudfront.debian.net`)
before `task setup`. Inside the development container, use
`task -t Taskfile.runtime.yml verify`.

## Status

`hallway-open` 0.1.0 is described and validated here and released in
[v1.1.0](https://github.com/Living-Proof-Labs/livingproof-worlds/releases/tag/v1.1.0).
Engine conversion lives in the simulators, not here: livingproof-sim-mujoco and
livingproof-sim-gazebo both pin v1.1.0. The MuJoCo hallway is used by the published
[robot verification reports](https://docs.livingprooflabs.com/livingproof-verification/);
Gazebo robot verification is not finished yet.

## License

[Apache-2.0](LICENSE).
