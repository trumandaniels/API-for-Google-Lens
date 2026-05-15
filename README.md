# API for Google Lens

Developer-facing repository for the Google Lens scraping API coding challenge.

## Goal

Build a small, reviewable API that satisfies the Google Lens scraping challenge prompt. Local agents maintain an ignored challenge acceptance checklist under `docs/challenge/SPEC.md`; the public submission should keep the root README focused on developer setup, usage, approach, and examples. The implementation should prioritize clear contracts, typed boundaries, useful tests, and simple operational instructions over speculative framework code.

## Engineering Standard

- Keep the public API surface small and direct.
- Use typed arguments and explicit return values where the language supports them.
- Document public modules, functions, classes, commands, and API routes with concise Google-style documentation.
- Include example usage for public entry points.
- Add tests for expected behavior, boundary parsing, and meaningful failure cases.
- Avoid broad generic schemas, wrapper envelopes, adapter layers, or extension points unless the challenge actually needs them.

## Local AI Workspace Boundary

This repository may contain local-only agent workspace files such as `AGENTS.md`, `PLAN.md`, `docs/`, `scripts/`, `tests/`, and `.runtime/`. Those files are ignored by Git and are not part of the public challenge submission unless intentionally promoted later.

The root `README.md` is the only non-AI README. Nested READMEs are local AI guidance and remain behind the `.gitignore` boundary.

## Status

Application code has not been added yet. The current workspace contains local planning and harness scaffolding for building the challenge implementation.

