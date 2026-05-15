# API for Google Lens

FastAPI service for the Google Lens scraping coding challenge.

The target API accepts an image URL, performs a direct Google Lens / Google
Search Exact Match request, and returns the raw HTML for the Exact Match results
page.

## Status

The project currently has the FastAPI scaffold, typed request parsing, error
mapping, response classification scaffolding, and dependency metadata.

The live Google Lens Exact Match request has not been verified yet. This is not
ready for challenge submission until `app/lens/direct.py` is proven against real
Google Lens traffic and the classifier is hardened with real response samples.

## Next Step

Implement and verify the direct Exact Match request in `app/lens/direct.py`.

Recommended sequence:

1. Install the project dependencies.
2. Run the local tests to confirm the scaffold is healthy.
3. Start the FastAPI server and verify `/healthz`.
4. Use a browser or devtools capture to inspect the Google Lens image-URL flow.
5. Replace the placeholder request builder in `app/lens/direct.py` with the
   verified direct Exact Match request.
6. Save sanitized live response samples under `.runtime/`.
7. Add fixture tests for valid Exact Match HTML, CAPTCHA/bot-block pages, Google
   error pages, and unknown responses.
8. Re-run tests and verify `GET /google-lens?imageUrl=...` returns raw Exact
   Match HTML for live sample URLs.

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
    Search --> Classifier["HTML classifier"]
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
# Edit .env with local credentials, then:
set -a
source .env
set +a
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

Until the direct Google Lens request is verified, `/google-lens` may return a
non-2xx response for live URLs because the current upstream request builder is
only a placeholder.

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

Use [.env.example](.env.example) as the local template. The application reads
process environment variables and does not load `.env` files by itself; source
`.env` before starting `uvicorn` or configure these variables in the deployment
environment.

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

MrScraper's public Residential Proxy documentation uses
`proxy.mrscraper.com:10000` and username modifiers such as
`-country-us`, `-mobile-country-us`, and `-sessid-lens1`. Do not commit proxy
credentials or saved live HTML that includes account-specific request metadata.
At the time this README was updated, MrScraper's public billing page listed
Residential Proxies on Standard plans and above, not on the Free plan; if a
reviewer provides different challenge-specific free credentials, these
environment variables are the intended integration point.

Note: process-wide concurrency enforcement still needs to be completed. The
current scaffold includes the limiter type, but request lifetime management must
be tightened before claiming a hosted max concurrency.

## Approach

The current implementation is structured around a direct Google Lens request.
It submits the image URL to Google Lens, follows the resulting Google Search /
Lens page, classifies the returned HTML, and only returns successful Exact Match
pages to the caller.
