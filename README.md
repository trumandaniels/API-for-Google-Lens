# API for Google Lens

Developer-facing repository for the Google Lens scraping API coding challenge.

## Goal

Build a small, reviewable API that satisfies the Google Lens scraping challenge prompt. Local agents maintain an ignored challenge acceptance checklist under `docs/challenge/SPEC.md`; the public submission should keep the root README focused on developer setup, usage, approach, and examples. The implementation should prioritize clear contracts, typed boundaries, useful tests, and simple operational instructions over speculative framework code.

## Current Structure

- `app/main.py`: FastAPI application factory.
- `app/api.py`: `GET /google-lens` and health route definitions.
- `app/models.py`: parsed boundary types such as `ImageUrl`.
- `app/errors.py`: domain errors and HTTP status mapping.
- `app/lens/direct.py`: direct Google request client. No browser fallback.
- `app/lens/classifier.py`: upstream HTML classification.
- `app/lens/service.py`: direct request orchestration and error decisions.
- `app/throttling.py`: in-process concurrency limiter.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run Locally

```bash
uvicorn app.main:app --reload
```

Example request:

```bash
curl "http://127.0.0.1:8000/google-lens?imageUrl=https://example.com/image.jpg"
```

The endpoint is scaffolded around the final contract, but the live Google Lens
Exact Match request parameters still need to be verified against upstream Google
responses before this should be treated as a working challenge submission.

## Test

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

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

FastAPI application scaffolding has been added. The current implementation is
direct-request only and intentionally does not include Playwright, Selenium, or a
browser automation fallback.

