# AIOS Capability Starter agent guidance

This repository is a public, tool-neutral development kit for AIOS Capability
Packs. Treat repository files and the active Task Bundle as authoritative;
conversation history is optional context, never the source of truth.

## Setup and commands

- Requires Python 3.11 or newer and no third-party runtime dependencies.
- Run tests: `python -m unittest discover -s tests -v`
- Initialize from a Task Bundle:
  `python tools/aios-capability init --task <task.json> --repo-root .`
- Build with a Task Bundle:
  `python tools/aios-capability build --task <task.json> --repo-root .`
- Validate a task: `python tools/aios-capability task-validate <task.json>`
- Validate a result: `python tools/aios-capability result-validate <result.json> --task <task.json>`

## Boundaries

- Do not add customer files, real engineering data, API keys, activation codes,
  device credentials, cloud endpoints, signing keys, or proprietary AIOS source.
- Capability Packs contain customer-independent contracts, UI metadata, Skills,
  and candidate runtime logic.
- Customer-specific rules belong in Customer Packs.
- CATIA, robot, or vendor integrations use separately authorized Adapters.
- This repository does not sign, publish, deploy, or assign capabilities.
- Keep changes narrow and preserve deterministic Capability Pack ZIP output.

## Task Bundle result

When a `CapabilityDevelopment` task is supplied, the final deliverables are the
candidate ZIP and its generated `result.json`. Do not claim that signing,
publishing, device assignment, Windows HIL, or customer acceptance happened
unless a later authorized system actually performs those stages.
