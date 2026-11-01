# livingproof-worlds

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
| [`hallway-open`](worlds/hallway-open/0.1.0/world.json) | `0.1.0` | robot-capability-specs `specs/worlds/hallways.md`, document revision 0.2.0 |

Each world lives at `worlds/<id>/<content_version>/world.json` and validates
against [`schema/world.schema.json`](schema/world.schema.json). The schema is
closed: an unknown field, geometry type or place type fails validation with an
`UNSUPPORTED` message instead of being ignored. Tests compare the hallway against
the canonical tables of a vendored copy of the pinned specification.

The first world is an open hallway with a named entrance, exit and usable passage, defined by
[robot-capability-specs #18](https://github.com/Living-Proof-Labs/robot-capability-specs/pull/18).
Both simulators will consume the same pinned release and check floor and wall
collisions with a simple test object; no robot or controller is involved.

## Development

With Git, Docker Compose v2 and Task 3.54.0 installed: `task setup`, then
`task check` and `task test` (or `task verify`). Behind a proxy that blocks
`deb.debian.org`, set `APT_MIRROR` (for example `https://cloudfront.debian.net`)
before `task setup`. Inside the development container, use
`task -t Taskfile.runtime.yml verify`.

## Status

`hallway-open` 0.1.0 is described and validated here. No engine conversion,
adapters, rendered evidence or release exists yet.

## License

[Apache-2.0](LICENSE).
