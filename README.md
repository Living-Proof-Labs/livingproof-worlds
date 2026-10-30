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

## Planned first world

An open hallway with a named entrance, exit and usable passage, defined by
[robot-capability-specs #18](https://github.com/Living-Proof-Labs/robot-capability-specs/pull/18).
Both simulators will consume the same pinned release and check floor and wall
collisions with a simple test object; no robot or controller is involved.

## Status

No world data yet. Repository tooling, CI and the first hallway release follow
the specification.

## License

[Apache-2.0](LICENSE).
