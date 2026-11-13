<!-- SPDX-License-Identifier: Apache-2.0 -->

# Start here

Living Proof Labs worlds supplies versioned, engine-neutral static geometry for
simulator adapters. Start with the [open hallway guide](../worlds/hallway-open/0.1.0/README.md)
and its diagram, then read [using and adding worlds](../README.md).
This repository contains no robots, controllers, engine conversion or simulation.
Equivalent geometry does not establish equivalent physics or capability results.

## Contracts and related manuals

The [world schema](../schema/world.schema.json) and
[release manifest schema](../schema/release.schema.json) are the actual contracts.
The hallway guide records its specification tag, content version and provenance.
Released world directories are immutable. Existing source and diagram paths are
preserved by this manual build.

Use [Documentation home](https://docs.livingprooflabs.com/) to discover related
manuals, including capability specifications and the MuJoCo and Gazebo adapters.
[Verification reports](https://docs.livingprooflabs.com/livingproof-verification/)
contain simulator evidence; this manual does not reproduce or certify those runs.
Current manual, organization-home and source-directory links are navigation
exceptions only; executable dependencies and shared guidance remain pinned.

## Contribute, help and license

Follow the repository [agent instructions](../AGENTS.md) and
[collaboration-guidelines v7.8.2](https://github.com/Living-Proof-Labs/collaboration-guidelines/tree/v7.8.2),
resolved to `1470bd46deffd62d6badf568996225e56872258a`.
The documentation recipe and brand come from that same released revision.
This focused adoption does not upgrade the baseline tracked by Renovate PR #10.
Submit changes as draft pull requests and obtain independent review before merge.
[Help / report an issue](https://github.com/Living-Proof-Labs/livingproof-worlds/issues)
is the public support path. No dedicated security-reporting route was established
in this review; do not post sensitive reports to public issues.
Original repository content, including this manual tooling, is [Apache-2.0](../LICENSE).
Shared brand attribution and licensing remain in its pinned upstream source.

## Preview

The host needs Git, Docker Compose v2 and Task 3.54.0. Run:

```sh
task setup
task manual:verify
python3 -m http.server --directory artifacts/manual/html 8000
```

Inside the already prepared development container, use
`task -t Taskfile.runtime.yml manual:verify` instead of the host Docker wrapper.
The build fetches only the immutable, checksum-verified shared stylesheet;
dependency installation requires public package access. Review artifacts retain
HTML and individual test results for 14 days, separate from the durable manual.

## Verification

The manual build stages canonical Markdown, world JSON, schemas and diagrams;
it does not regenerate or modify released world content. Contributor commands
are generated using native Task list and summary output, without executing task
bodies. The Version and source page records the exact documentation commit,
dirty-preview status, source hashes and workflow run. This is development
documentation; historical rendered manuals are not maintained. Published source
tags remain available for older releases.

Manual checks cover local HTML links and fragments, shared branding on every
page, source identity, diagram availability and generated Task reference.
`task verify` separately checks world schemas, geometry, provenance, manifests
and generated world documentation. No software coverage is measured, and no
simulation is run by these documentation checks. There is no shipped library
API or public application CLI to invent a reference for.

## Publication and remaining acceptance

Expected URL: `https://docs.livingprooflabs.com/livingproof-worlds/`.
This is a deployment target, not a verified live-site claim.
The repository manual workflow builds and checks pull requests with read-only
permissions, then publishes only trusted main builds through a separate Pages
job. Deployment rejects a stale main revision while holding the deployment lock.
Only that job receives Pages and identity-token write permissions; it does not
check out or run project code.

Prerequisites are Pages configured for GitHub Actions and a `github-pages`
environment restricted to main. No settings are changed by this PR. The existing
Docker Compose development image is used as a local publication-tooling override;
a separately published tooling image is outside this bounded docs change.
Independent review and verification of the user-run preview path remain required.
After authorized merge and deployment, verify HTTPS, source/run identity,
README-to-manual navigation, nested links and reload, desktop/mobile/keyboard
navigation, search and opening a result, and root/source/help/license links.
Then replace the pending README link and ask the directory owner to add the
verified rendered destination. Artifact upload alone is not live acceptance.
