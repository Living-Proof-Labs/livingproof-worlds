# Agent instructions

<!-- renovate: guidelines -->
[collaboration-guidelines v7.7.0](https://github.com/Living-Proof-Labs/collaboration-guidelines/blob/v7.7.0/AGENTS.md)
applies, with its procedures, to every change in this repository.
Local additions: worlds are engine-neutral static descriptions only. No engine
conversion, simulator adapters, robots or controllers here; those live in the
simulator repositories. A world supports only what its specification in
robot-capability-specs requires; unknown features must fail validation, never be
ignored. Released world versions are immutable: change a world by adding a new
content version directory. Original repository content is Apache-2.0.
Substantive changes stay in a draft PR until independent review.
Do not enable new registry/security permissions or alter organization settings.
