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

Do not add Playwright, Selenium, or a browser automation fallback. The intended
submission path is direct-request only.

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

## Project Structure

- `app/main.py`: FastAPI application factory.
- `app/api.py`: `/google-lens` and `/healthz` route definitions.
- `app/models.py`: parsed boundary types such as `ImageUrl`.
- `app/errors.py`: domain errors and HTTP status mapping.
- `app/throttling.py`: in-process concurrency limiter.
- `app/lens/direct.py`: direct Google request client. No browser fallback.
- `app/lens/classifier.py`: upstream HTML classification.
- `app/lens/service.py`: fetch, classify, and error orchestration.
- `tests/`: unit tests for parsing, classification, error mapping, and local
  harness behavior.

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

Run repository harness checks:

```bash
python3 scripts/run_harness.py
```

Run individual repository checks:

```bash
python3 scripts/lint_index.py
python3 scripts/lint_exec_plans.py
python3 scripts/lint_readmes.py
```

Syntax-check the app and tests:

```bash
python3 -m compileall -q app tests
```

## Configuration

The API reads these optional environment variables:

- `GOOGLE_BASE_URL`: upstream Google Search base URL. Defaults to
  `https://www.google.com/search`.
- `REQUEST_TIMEOUT_SECONDS`: upstream timeout. Defaults to `30.0`.
- `MAX_CONCURRENCY`: intended upstream concurrency limit. Defaults to `4`.
- `USER_AGENT`: user agent sent upstream.
- `PROXY_URL`: optional proxy URL for outbound Google requests.

Note: process-wide concurrency enforcement still needs to be completed. The
current scaffold includes the limiter type, but request lifetime management must
be tightened before claiming a hosted max concurrency.

## Approach

This project intentionally avoids browser automation in the runtime path. The
challenge scores direct reverse-engineering higher than browser automation, so
the core implementation should directly reproduce the Google Lens Exact Match
request, classify the returned HTML, and only return successful Exact Match
pages to the caller.

Manual browser/devtools inspection is acceptable as a research method, but
browser automation should not be shipped as a fallback.
