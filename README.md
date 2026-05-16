# Google Lens Exact Match API

FastAPI implementation of the Google Lens scraping challenge in
[`docs/challenge/`](docs/challenge/). The service accepts a public image URL,
drives the Google Lens Exact Match flow through MrScraper's API-token HTML
fetch mode, and returns the raw Exact Match results page HTML.

Hosted API:
[`https://api-for-google-lens-production.up.railway.app`](https://api-for-google-lens-production.up.railway.app)

## Challenge Requirements, Up Front

Source of truth: [`docs/challenge/SPEC.md`](docs/challenge/SPEC.md) extracted
from the challenge PDF in [`docs/challenge/`](docs/challenge/).

| Challenge requirement | Implementation status |
| --- | --- |
| `GET /google-lens?imageUrl=...` | Implemented in FastAPI with typed query parsing. |
| Return the full Exact Match page HTML | Implemented; successful responses are `text/html` raw Google Exact Match HTML. |
| Automate Lens URL search into Exact Match | Implemented as a two-hop Lens/Search flow: Lens `uploadbyurl`, then extracted `udm=48` Exact Match tab. |
| Use a reverse-engineered/direct request approach | Implemented without Playwright, Selenium, stealth browser code, or browser fallback. |
| Use MrScraper for Google-facing fetching | Implemented through MrScraper API-token HTML fetch mode with `html=true` and `super=true`. |
| Avoid returning CAPTCHA/error pages as success | Implemented with HTML classification before returning `200`. |
| Meaningful status codes | `400`, `402`, `429`, `502`, and `504` are explicitly mapped. |
| Local setup, run, and tests | Documented below; deterministic harness passes. |
| Hosted API link | Deployed on Railway; URL above. |
| Maximum supported concurrency | Current measured default is `MAX_CONCURRENCY=16` per API process. |
| Challenge scoring target | Latest hosted sample projected 954-1002 valid Exact Match responses/hour, 0% errors, 27.95s average latency. Full final one-hour run is still the last submission proof step. |

Scoring targets tracked from the prompt:

| Target | Challenge threshold | Latest hosted evidence |
| --- | ---: | ---: |
| Valid Exact Match responses/hour | At least 300 of 1,000 | 954 observed-throughput estimate; 1002 planned projection |
| Average latency | At most 60s | 27.95s |
| Error rate | At most 10% | 0.0% |
| Bot blocks in sample | Must not be returned as success | 0 |

Latest hosted measurement:
[`lens-measure-2026-05-16T20-13-03-139756Z`](.runtime/runs/lens-measure-2026-05-16T20-13-03-139756Z/report.md)
sent 167 requests at concurrency 16 and a challenge-rate arrival pace.

## API Contract

```text
GET /google-lens?imageUrl=<public_image_url>
```

Example:

```bash
curl 'https://api-for-google-lens-production.up.railway.app/google-lens?imageUrl=https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS-9m4zOb/$_57.JPG'
```

Success:

```text
200 OK
Content-Type: text/html

<raw Google Lens Exact Match HTML>
```

Error behavior:

| Status | Meaning |
| ---: | --- |
| `400` | `imageUrl` is empty, relative, hostless, or not `http`/`https`. |
| `402` | The configured MrScraper account is out of credits. |
| `429` | Google or the provider returned CAPTCHA, bot-check, or rate-limit HTML. |
| `502` | Upstream returned an error page or a page that is not Exact Match results. |
| `504` | Provider or Google request timed out. |

If the hosted server runs out of MrScraper credits, callers can retry with
their own MrScraper token:

```bash
curl \
  -H "X-MrScraper-Api-Key: atk_your_mrscraper_api_key" \
  'https://api-for-google-lens-production.up.railway.app/google-lens?imageUrl=https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS-9m4zOb/$_57.JPG'
```

## Architecture

The public route stays thin: parse the boundary, call the Lens service, return
classified Exact Match HTML, or map a domain error to HTTP.

```text
Client
  -> FastAPI /google-lens
  -> ImageUrl parser
  -> process-local cache
  -> concurrency limiter + small jitter
  -> MrScraper fetch: lens.google.com/uploadbyurl?url=<image>
  -> parse Google's session-specific Exact Match tab URL containing udm=48
  -> MrScraper fetch: extracted Exact Match URL
  -> HTML classifier
  -> raw Exact Match HTML response
```

Important files:

- [`app/api.py`](app/api.py): FastAPI routes and HTTP boundary.
- [`app/models.py`](app/models.py): parsed domain values such as `ImageUrl`.
- [`app/lens/direct.py`](app/lens/direct.py): MrScraper-backed Google Lens URL flow.
- [`app/lens/service.py`](app/lens/service.py): throttling, caching, classification, and domain errors.
- [`app/lens/classifier.py`](app/lens/classifier.py): Exact Match, CAPTCHA, and Google error detection.
- [`app/config.py`](app/config.py): typed environment parsing.
- [`scripts/measure_lens_api.py`](scripts/measure_lens_api.py): repeatable live scoring measurement.

## Why This Approach

The challenge rewards a direct/reverse-engineered request path over browser
automation. This implementation therefore does not ship Playwright, Selenium,
stealth drivers, local proxy pools, or CAPTCHA solving. It uses the smallest
reliable request flow found during live probing:

1. Submit the image URL to Google's Lens `uploadbyurl` endpoint through
   MrScraper.
2. Let Google create the session-bound Search/Lens result page.
3. Extract the Exact Match tab link containing `udm=48`.
4. Fetch that Exact Match URL through MrScraper.
5. Return the HTML only if classification confirms it is the Exact Match page.

Plain local or datacenter HTTP requests returned Google `403` pages during
live probes. The production path assumes MrScraper supplies Google-facing
rotation and anti-bot handling, while this API controls local burstiness,
timeouts, cache behavior, and failure classification.

## Local Setup

Requirements:

- Python 3.12+
- `uv` recommended, or `pip`
- MrScraper API token for live Lens requests

Install:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

Configure:

```bash
cp .env.example .env
```

Set `MRSCRAPER_API_KEY` in `.env` or in the process environment. Do not commit
real credentials.

Run:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Health check:

```bash
curl 'http://127.0.0.1:8000/healthz'
```

Local API call:

```bash
curl 'http://127.0.0.1:8000/google-lens?imageUrl=https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS-9m4zOb/$_57.JPG'
```

## Configuration

Runtime settings are parsed once into typed configuration at process startup.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MRSCRAPER_API_KEY` | Required | MrScraper Scraper API token. |
| `MRSCRAPER_API_URL` | `https://api.mrscraper.com` | MrScraper API endpoint. |
| `GOOGLE_BASE_URL` | `https://lens.google.com/uploadbyurl` | Google Lens entry URL. |
| `REQUEST_TIMEOUT_SECONDS` | `60.0` | Per provider-hop timeout. |
| `MAX_CONCURRENCY` | `16` | In-process upstream concurrency limit. |
| `REQUEST_DELAY_MIN_SECONDS` | `0.0` | Minimum local jitter before provider work. |
| `REQUEST_DELAY_MAX_SECONDS` | `0.25` | Maximum local jitter before provider work. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `512` | Successful Exact Match cache size. |
| `RESPONSE_CACHE_TTL_SECONDS` | `7200.0` | Successful Exact Match cache TTL. |
| `MRSCRAPER_BLOCK_RESOURCES` | `false` | Optional provider hint; disabled because live tests were slower. |
| `USER_AGENT` | Chrome/Linux UA | Browser-like upstream user agent. |

## Verification

Run deterministic local checks:

```bash
python3 scripts/run_harness.py
```

Equivalent direct checks:

```bash
python3 scripts/lint_index.py
python3 scripts/lint_exec_plans.py
python3 scripts/lint_readmes.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m compileall -q app tests scripts
```

Run a small live smoke measurement against the hosted API:

```bash
python3 scripts/measure_lens_api.py \
  --base-url https://api-for-google-lens-production.up.railway.app \
  --image-url 'https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS-9m4zOb/$_57.JPG' \
  --requests 5 \
  --concurrency 2 \
  --min-valid-exact 1 \
  --max-average-latency-seconds 60 \
  --max-error-rate 0.5
```

Run a credit-conscious challenge-rate estimate:

```bash
python3 scripts/measure_lens_api.py \
  --base-url https://api-for-google-lens-production.up.railway.app \
  --image-url-file .runtime/live-image-urls.txt \
  --requests 167 \
  --concurrency 16 \
  --rate-per-minute 16.7 \
  --randomize-image-urls \
  --image-url-seed 20260516
```

Run the full one-hour challenge profile before final submission:

```bash
python3 scripts/measure_lens_api.py \
  --base-url https://api-for-google-lens-production.up.railway.app \
  --image-url-file .runtime/live-image-urls.txt \
  --requests 1000 \
  --concurrency 16 \
  --rate-per-minute 16.7 \
  --randomize-image-urls \
  --image-url-seed 20260516 \
  --target challenge
```

Measurement artifacts are written under `.runtime/runs/lens-measure-*` with
`report.md`, `report.json`, `verdict.json`, and sampled response verdicts.

## Current Evidence

The latest hosted measurement used the deployed Railway API, 167 image-search
requests, concurrency 16, and a challenge-rate arrival pace of 16.7 requests
per minute.

| Metric | Result |
| --- | ---: |
| Valid Exact Match responses | 167 / 167 |
| Error rate | 0.0% |
| Bot blocks | 0 |
| Invalid `200` responses | 0 |
| Average latency | 27.95s |
| p95 latency | 38.21s |
| Max latency | 42.84s |
| Observed-throughput hour estimate | 954 valid responses |
| Planned projection | 1002 valid responses |

This is strong hosted evidence against the challenge thresholds, but it is not
presented as a replacement for the final 1,000-request one-hour run.

## Engineering Notes

- Boundary parsing follows "parse, don't validate": raw query strings and env
  vars become typed values before business logic sees them.
- The service rejects CAPTCHA, bot-check, Google error, and unknown pages
  instead of returning them as successful HTML.
- A process-scoped `httpx.AsyncClient` preserves connection pooling to the
  provider API.
- Successful Exact Match HTML is cached by normalized image URL, with duplicate
  in-flight cache misses coalesced.
- Provider-hop timing logs identify whether latency is coming from the Lens
  entry hop or the Exact Match hop without logging API tokens.
- Experiment history in the previous README informed the current defaults:
  `MAX_CONCURRENCY=16`, low jitter, no provider resource blocking, and no
  `geoCode` override.

## Repository Map

- [`docs/challenge/`](docs/challenge/): challenge PDF and extracted spec.
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md): common commands and live measurement notes.
- [`docs/INDEX.md`](docs/INDEX.md): repository file map.
- [`tests/`](tests/): deterministic coverage for parsing, configuration,
  classification, provider errors, cache behavior, and harness tooling.
- [`harness.json`](harness.json): routine local verification steps.
