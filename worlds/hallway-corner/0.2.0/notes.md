<!-- SPDX-License-Identifier: Apache-2.0 -->
# Corner hallway 0.2.0

One physical fixture serves both traversal scenarios. Its six floor/wall boxes
and dimensions are exactly those of hallway-corner 0.1.0: 1.5 m clear width,
2.5 m wall height, 0.15 m wall thickness and 0.1 m floor thickness. Nothing is
mirrored. Released directories and historical evidence remain unchanged.

| Traversal | From | Inward spawn | Ordered route | Finish | Travel |
| --- | --- | --- | --- | --- | --- |
| forward | end-west | spawn-west at (-2.5, 0, 0), yaw 0° | route-forward: (-3, 0) → (0, 0) → (0, 3) | end-north | 5.5 m |
| reverse | end-north | spawn-north at (0, 2.5, 0), yaw -90° | route-reverse: (0, 3) → (0, 0) → (-3, 0) | end-west | 5.5 m |

Both complete routes are 6 m. Travel starts 0.5 m inward. Scenarios select the
matching start, route and finish together. No scenarios are created or renamed.

## Dependency and migration

Format 0.3 and content 0.2.0 use specs contract 0.4.0 / layout 0.2,
published in [robot-capability-specs v2.4.0](https://github.com/Living-Proof-Labs/robot-capability-specs/releases/tag/v2.4.0).
The tag resolves to `9723f8ba450921068739f72b8ad868f2c544df98`.
World content and specs releases are separate; select a published worlds catalog
release containing this content revision.
Checksums for every content file are recorded in [release.json](release.json).

Consumers must explicitly support world format 0.3 and select one traversal's
start, route and finish together. Existing 0.1.0 content remains available with
its historical names and bytes. Do not reinterpret historical evidence using
this new content version. Downstream selection belongs to verification manifests
after the world release; no downstream pins or scenarios change here.

## Authoring and verification

Use existing segment, pose, polyline and region primitives. Read the
[reusable simple worlds guidance](https://docs.livingprooflabs.com/collaboration-guidelines/docs/developer-interface.html#reusable-simple-worlds).
Tests compare physical geometry, route endpoints and equal travel distance, and
reject missing/inconsistent references, headings and placement. These are static
contract checks. Engine execution and robot behavior are unrun; no robot PASS
is claimed.
