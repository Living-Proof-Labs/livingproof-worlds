<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Open hallway fixture, revision 0.2.0

Copyright 2026 Living Proof Labs contributors. [CC BY 4.0](../../LICENSES/CC-BY-4.0.txt).

Document revision 0.2.0 versions this specification text. It is separate from
the fixture content version (`hallway-open` / `0.1.0`), which versions the world
data.

This document applies the [world contract](README.md) to one fixture:
`hallway-open`. It is a straight hallway with a floor and two side walls, open at
both ends, with no doors, rooms, end walls, or ceiling. It is engine-neutral:
the same declaration is meant to be loaded by MuJoCo and Gazebo consumers.

The world data for this fixture will live in a future
[Living-Proof-Labs/livingproof-worlds](https://github.com/Living-Proof-Labs/livingproof-worlds)
repository. This catalog holds only the specification and its examples.

## Scope

- There is no robot, controller, or navigation goal in this revision. The
  collision probe is a plain sphere.
- Equivalent geometry does not imply identical physics. Consumers must agree on
  dimensions, placements, and collision boundaries; contact forces, trajectories,
  timing, and rendered pixels may differ.
- "G1 walks from the entrance to the exit" is a later story. It will reuse the
  named places below but is not specified here.

## Canonical dimensions

All values are metres.

| Fixture / content version | Clear width | Length | Wall height | Wall thickness | Exterior width |
| --- | ---: | ---: | ---: | ---: | ---: |
| `hallway-open` / `0.1.0` | 1.50 m | 6.00 m | 2.50 m | 0.15 m | 1.80 m |

Clear width is the distance between the inner side-wall faces. Length is the
extent of the floor and both side walls along `+x`. Wall height is measured from
the floor top surface. The floor covers `x = [-3.00, 3.00]`, `y = [-0.90, 0.90]` and is 0.10 m
thick, with its top surface at `z = 0` and its underside at `z = -0.10`.

## Frame

The frame is right-handed and metre-based. The origin is the centre of the floor
top surface; `+x` runs along the hallway from entrance to exit, `+y` across it,
and `+z` upward. Inner side-wall faces are at `y = ±0.75`. The hallway ends are
the open planes `x = -3.00` and `x = 3.00`. A pose is position `(x, y, z)` plus
yaw in degrees, positive about `+z`.

## Named places

All places are in the world frame above, at floor level (`z = 0`) unless stated.

| Name | Type | Definition |
| --- | --- | --- |
| `entrance` | segment | From `(-3.00, -0.75, 0)` to `(-3.00, 0.75, 0)`; reference point `(-3.00, 0, 0)` |
| `exit` | segment | From `(3.00, -0.75, 0)` to `(3.00, 0.75, 0)`; reference point `(3.00, 0, 0)` |
| `passage` | region | `x = [-3.00, 3.00]`, `y = [-0.50, 0.50]` (0.25 m clearance from each side wall) |
| `passage-centreline` | polyline | `(-3.00, 0, 0)` → `(3.00, 0, 0)` |
| `spawn-entrance` | pose | `(-2.50, 0, 0)`, yaw 0° (facing the exit) |
| `spawn-centre` | pose | `(0, 0, 0)`, yaw 0° |
| `spawn-exit` | pose | `(2.50, 0, 0)`, yaw 180° (facing the entrance) |

Every spawn pose lies inside `passage` and on `passage-centreline`. A
floor-spawned entity records its ground-contact point at `z = 0`. Reset restores
the geometry, frame, and initial world state and removes transient entities.

## Conformance expectations

Measured clear width, length, wall height, wall thickness, floor thickness, origin, and every
named place must agree with the canonical values within 0.01 m. Frame axes and
spawn yaws must agree within 0.5 degrees.

Collision evidence uses a 0.10 m-radius non-robot sphere with gravity and
contacts enabled:

1. **Floor:** release it from rest at `spawn-centre` with its centre at
   `z = 0.75 m`. It settles on the floor; penetration below the floor top
   surface may not exceed 0.01 m.
2. **Side walls:** from `spawn-centre`, drive it normally (no teleporting, at
   most 0.25 m/s) toward `+y` and then `-y`. The sphere's surface must not pass
   an inner wall face by more than 0.01 m.
3. **Open ends:** from `spawn-centre`, drive it along `passage-centreline` to
   `x = ±2.80`. It contacts nothing but the floor, showing that no end wall or
   door exists.

Retained evidence records gravity/contact settings, drive method, sampling
rate, and measurement method.

## Cross-engine comparison

A verifier produces one comparison record per fixture version listing, for
each measured quantity (dimensions, named places, collision boundaries), the
canonical value, each engine's measured value, each engine's deviation, and the
MuJoCo-minus-Gazebo difference. The comparison passes only when every engine is
within tolerance of the canonical value; the pairwise difference is reported,
not used to hide a deviation.

## Reviewer evidence

Each engine run retains at least an overhead screenshot and a view from
`spawn-entrance` toward `exit`, machine-readable geometry/place/collision/reset
results, and the test results. Every record names the exact fixture identifier
and content version, the world-contract revision, the catalog version and
commit, and the consumer (engine and adapter) version and commit.

## User stories and BDD traceability

Stories follow the [world contract](README.md#user-stories-and-bdd-traceability)
format and personas. Each expected outcome is the acceptance criterion; each BDD
scenario names its scenario in [hallway examples](hallways.feature).

| Story | Expected outcome | BDD scenario |
| --- | --- | --- |
| As an integrator, I want to select a named, versioned hallway without changing simulator code, so that MuJoCo and Gazebo consumers load the same declared fixture. | Selecting `hallway-open` at `0.1.0` is configuration only; each consumer loads it without code changes; an unknown identifier or version is reported, not substituted. | `An integrator selects the open hallway by name and version` |
| As a scenario author, I want the entrance, exit, and passage declared in one world frame, so that a scenario has unambiguous places and poses. | Each consumer reports every named place in the world frame within 0.01 m and 0.5 degrees of the canonical table. | `A scenario author uses the declared hallway places` |
| As a verifier, I want to compare MuJoCo and Gazebo against the same declaration, so that I can show they loaded equivalent dimensions, placements, and collision boundaries. | Both engines pass the dimension, named-place, floor, side-wall, and open-end checks, and a cross-engine comparison lists each quantity's canonical value, measured values, and difference. | `A verifier compares MuJoCo and Gazebo hallway evidence` |
| As a reviewer, I want screenshots, test results, and exact versions from both engines, so that I can inspect what was evaluated. | The record shows the required screenshots and test results for each engine and identifies the fixture, world contract, catalog, and adapter versions. | `A reviewer inspects retained hallway results from both engines` |
| As a verifier, I want an unsupported hallway feature to fail clearly, so that no consumer silently ignores part of the fixture. | A consumer that cannot load a declared feature returns `UNSUPPORTED` naming the fixture, version, and feature, and never reports a pass with it ignored. | `A consumer meets an unsupported hallway feature` |
