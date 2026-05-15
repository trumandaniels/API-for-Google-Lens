# API for Google Lens

FastAPI service for the Google Lens scraping coding challenge.

The target API accepts an image URL, performs a direct Google Lens / Google
Search Exact Match request, and returns the raw HTML for the Exact Match results
page.

## Table of Contents

- [Status](#status)
- [Endpoint](#endpoint)
- [Data Flow](#data-flow)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Setup](#setup)
- [Run](#run)
- [Test](#test)
- [Proxy Configuration](#proxy-configuration)
- [Approach](#approach)

## Status

The project currently has the FastAPI scaffold, typed request parsing, error
mapping, response classification, direct Google Lens request construction,
MrScraper HTML fetch wiring, local `.env` parsing, fixture coverage, and
dependency metadata.

The live MrScraper API-token path has been verified for Google Lens Exact Match:
the service submits a minimal Lens `uploadbyurl` request, receives the Google
Search Lens page, follows the Exact Match `udm=48` tab link, and returns the raw
Exact Match HTML. Direct non-provider Google traffic may still return Google
block pages from local or datacenter networks. The residential proxy path is
implemented but should be separately verified with working proxy credentials
before claiming it as a supported deployment mode.

## Endpoint

```text
GET /google-lens?imageUrl=<image_url>
```

Success response:

```text
200 OK
Content-Type: text/html

<raw Google Lens Exact Match HTML>
```

Expected failure responses include:

- `400` for malformed `imageUrl` input.
- `429` for CAPTCHA, bot-check, or Google block pages.
- `502` for upstream request failures or unrecognized Google result pages.
- `504` for upstream timeouts.

## Data Flow

```mermaid
flowchart TD
    Client["API client"] --> Route["GET /google-lens?imageUrl=..."]
    Route --> Parse["Parse imageUrl into ImageUrl"]
    Parse --> Service["GoogleLensService"]
    Service --> Limit["Concurrency limiter"]
    Limit --> Direct["DirectLensClient"]
    Direct --> Lens["lens.google.com/uploadbyurl"]
    Lens --> Search["Google Lens / Search udm=26 page"]
    Search --> Exact["Google Search Exact Match udm=48 page"]
    Exact --> Classifier["HTML classifier"]
    Classifier -->|Exact Match HTML| Success["200 text/html raw HTML"]
    Classifier -->|Malformed input| BadRequest["400"]
    Classifier -->|CAPTCHA or bot block| Blocked["429"]
    Classifier -->|Timeout| Timeout["504"]
    Classifier -->|Google error or unknown page| UpstreamError["502"]
```

## Project Structure

- `app/main.py`: FastAPI application factory.
- `app/api.py`: `/google-lens` and `/healthz` route definitions.
- `app/models.py`: parsed boundary types such as `ImageUrl`.
- `app/errors.py`: domain errors and HTTP status mapping.
- `app/throttling.py`: in-process concurrency limiter.
- `app/lens/direct.py`: direct Google request client.
- `app/lens/classifier.py`: upstream HTML classification.
- `app/lens/service.py`: fetch, classify, and error orchestration.
- `tests/`: unit tests for parsing, classification, and error mapping.

## Requirements

- Python 3.12+
- `uv` is recommended for dependency management
- Network access for dependency installation
- Network access for live Google Lens verification

Runtime dependencies are pinned in `pyproject.toml`.

## Setup

Recommended with `uv`:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Fallback with Python and `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

With local environment variables:

```bash
cp .env.example .env
# Edit .env with local credentials. The app loads .env automatically, and
# process environment variables override matching .env values.
uvicorn app.main:app --reload
```

Health check:

```bash
curl "http://127.0.0.1:8000/healthz"
```

Example API call:

```bash
curl 'http://127.0.0.1:8000/google-lens?imageUrl=https://i.ebayimg.com/00/s/MTYwMFgxNjAw/z/BVcAAOSwS-9m4zOb/$_57.JPG'
```

If Google or the configured provider returns CAPTCHA, bot-check, or Google error
HTML, `/google-lens` returns a non-2xx response rather than passing that page
through as a successful Exact Match result.

## Test

Run the full local unit suite:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Syntax-check the app and tests:

```bash
python3 -m compileall -q app tests
```

## Proxy Configuration

The API reads these optional environment variables:

- `GOOGLE_BASE_URL`: upstream Google Lens base URL. Defaults to
  `https://lens.google.com/uploadbyurl`.
- `REQUEST_TIMEOUT_SECONDS`: upstream timeout. Defaults to `30.0`.
- `MAX_CONCURRENCY`: intended upstream concurrency limit. Defaults to `4`.
- `USER_AGENT`: user agent sent upstream.
- `MRSCRAPER_API_KEY`: optional MrScraper Scraper API token. When present, the
  app asks MrScraper's HTML fetch endpoint to fetch the Google Lens URL with
  `token`, `html=true`, `super=true`, and `url`. This API-token mode takes
  precedence over residential proxy settings when both are configured.
- `MRSCRAPER_API_URL`: optional MrScraper Scraper API endpoint. Defaults to
  `https://api.mrscraper.com`.
- `PROXY_URL`: optional generic proxy URL for outbound Google requests. This
  takes precedence over provider-specific proxy settings.
- `MRSCRAPER_PROXY_USERNAME`: MrScraper Residential Proxy username.
- `MRSCRAPER_PROXY_PASSWORD`: MrScraper Residential Proxy password.
- `MRSCRAPER_PROXY_COUNTRY`: optional two-letter ISO country code such as `us`.
- `MRSCRAPER_PROXY_MOBILE`: optional true-like value (`true`, `yes`, `on`, or
  `1`) for a mobile proxy. Requires `MRSCRAPER_PROXY_COUNTRY`.
- `MRSCRAPER_PROXY_SESSION_ID`: optional static session identifier. Requires
  `MRSCRAPER_PROXY_COUNTRY`.
- `MRSCRAPER_PROXY_SESSION_MINUTES`: optional static session duration. Requires
  `MRSCRAPER_PROXY_SESSION_ID`.

Use [.env.example](.env.example) as the local template. The application loads a
repo-root `.env` file when present, then overlays process environment variables.
For deployment, prefer real process environment variables rather than copying
local `.env` files.

MrScraper Scraper API / Playground example:

```bash
export MRSCRAPER_API_KEY='atk_example'
```

Generic proxy example:

```bash
export PROXY_URL='http://username:password@proxy.example.com:8080'
```

MrScraper rotating US residential proxy example:

```bash
export MRSCRAPER_PROXY_USERNAME='user123'
export MRSCRAPER_PROXY_PASSWORD='pass456'
export MRSCRAPER_PROXY_COUNTRY='us'
```

MrScraper static-session example:

```bash
export MRSCRAPER_PROXY_USERNAME='user123'
export MRSCRAPER_PROXY_PASSWORD='pass456'
export MRSCRAPER_PROXY_COUNTRY='us'
export MRSCRAPER_PROXY_SESSION_ID='lens1'
export MRSCRAPER_PROXY_SESSION_MINUTES='20'
```

MrScraper has two relevant integration surfaces. The HTML fetch API uses an API
token query parameter plus render options such as `html=true`, `super=true`,
and `url=<target>`. The Residential Proxy product uses
`proxy.mrscraper.com:10000` and username modifiers such as
`-country-us`, `-mobile-country-us`, and `-sessid-lens1`. For an API token like
`atk_...`, use `MRSCRAPER_API_KEY` rather than the residential
`MRSCRAPER_PROXY_USERNAME` / `MRSCRAPER_PROXY_PASSWORD` variables. Do not commit
API keys, proxy credentials, or saved live HTML that includes account-specific
request metadata.

Note: process-wide concurrency enforcement still needs to be completed. The
current scaffold includes the limiter type, but request lifetime management must
be tightened before claiming a hosted max concurrency.

## Approach

The current implementation is structured around a direct Google Lens request.
It submits the image URL to Google Lens, follows the resulting Google Search /
Lens page, classifies the returned HTML, and only returns successful Exact Match
pages to the caller.
