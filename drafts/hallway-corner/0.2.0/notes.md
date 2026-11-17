<!-- SPDX-License-Identifier: Apache-2.0 -->
# Corner hallway 0.2.0 — unreleased candidate

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

Format 0.3 and content 0.2.0 require specs contract 0.4.0 / layout 0.2.
The specs change must merge, verify and release first. The specification declares
`status: unreleased`, deliberately without a tag or commit. The production schema
rejects it. This file is excluded from `worlds/`, generated catalog documentation
and release manifests. Draft validation requires an explicit option.

Before this worlds PR is ready, replace the pending specification with the actual
published tag and resolved commit, move the candidate into
`worlds/hallway-corner/0.2.0/`, generate its release manifest, and check the generated README and SVGs. Run all checks again. Do not regenerate any 0.1.0 files.
Never label an older specs release as containing the new contract. Downstream
selection belongs to verification manifests after the world release.

## Authoring and verification

Use existing segment, pose, polyline and region primitives. Read the
[reusable simple worlds guidance](https://docs.livingprooflabs.com/collaboration-guidelines/docs/developer-interface.html#reusable-simple-worlds).
Tests compare physical geometry, route endpoints and equal travel distance, and
reject missing/inconsistent references, headings and placement. These are static
contract checks. Engine execution and robot behavior are unrun; no robot PASS
is claimed.
