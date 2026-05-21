# Google Lens Exact Match API

I built this API around a specific Google Lens behavior: image URL search works
in the browser, but the Exact Match page only appears after Google creates a
Lens/Search session. The service takes a public image URL, follows that session
flow, and returns the raw Exact Match HTML.

Hosted API:
[`https://api-for-google-lens-production.up.railway.app`](https://api-for-google-lens-production.up.railway.app)

The Railway deployment uses my configured MrScraper credits by default. If that
account runs out, the API returns `402`; pass your own MrScraper token in
`X-MrScraper-Api-Key` and the same hosted endpoint will use it for that request.

## What Is Interesting Here

The useful part is the reverse-engineered Lens flow.

Google does not give you a stable Exact Match URL from the original image URL.
The service first submits the image to `lens.google.com/uploadbyurl`, then
parses the returned Search/Lens page for the generated Exact Match tab. That
tab carries `udm=48`, and it is tied to the session Google just created. Only
after fetching that generated URL does the API return HTML to the caller.

FastAPI handles the HTTP surface, Pydantic parses config, the Lens client builds the Google URLs,
MrScraper handles the Google-facing fetches and proxy rotation, and a lightweight classifier keeps CAPTCHA,
Google error, and ambiguous pages from being returned as successful responses.

## Measured Behavior

To preserve MrScraper credits, I ran a 10-minute load test against the hosted
Railway API instead of spending a full 1,000-request hour on every iteration.
The run used 167 image-search requests, concurrency 16, and an arrival pace of
16.7 requests per minute, then projected the same rate over an hour.

- Valid Exact Match responses: 167 / 167
- Error rate: 0.0%
- Bot blocks: 0
- Invalid `200` responses: 0
- Average latency: 27.95s
- p95 latency: 38.21s
- Max latency: 42.84s
- Observed-throughput hour estimate from the 10-minute run: 954 valid responses
- Planned one-hour projection at the target arrival rate: 1002 valid responses

The load target I optimized around is 1,000 requests over one hour, with at
least 300 valid Exact Match pages, average latency under 60 seconds, and error
rate under 10%.

Maximum supported hosted concurrency is `MAX_CONCURRENCY=16` per API process.

## API

Endpoint: `GET /google-lens?imageUrl=<public_image_url>`.

Example:

Set `HOST` to the hosted API above and `IMAGE` to any public image URL.

```bash
# health-check: curl --version
curl "$HOST/google-lens?imageUrl=$IMAGE"
```

Hosted Railway example with a caller-supplied MrScraper token:

```bash
HOST='https://api-for-google-lens-production.up.railway.app'
IMAGE='https://katespade.scene7.com/is/image/KateSpade/KP070_001?$desktopProductV5$'
MRSCRAPER_API_KEY='atk_your_mrscraper_api_key'

# health-check: curl --version
curl \
  -H "X-MrScraper-Api-Key: $MRSCRAPER_API_KEY" \
  "$HOST/google-lens?imageUrl=$IMAGE"
```

Success:

The success response is `200 OK` with `Content-Type: text/html`. The body is
the raw Google Lens Exact Match HTML. If Google reaches the Exact Match tab but
shows its "No matches for your search" empty state, the API still returns that
HTML with `200`; it is the requested Exact Match page, just without result
cards.

## Viewing Retrieved HTML

To view the retrieved page directly, start the API and open the endpoint URL in
a browser. The API response is the page: `GET /google-lens` returns the
retrieved Exact Match HTML as `text/html`.

```text
http://127.0.0.1:8000/google-lens?imageUrl=<url-encoded-public-image-url>
```

For repeatable inspection, save the response under `.runtime/` and open the
saved HTML file. `curl --get --data-urlencode` handles image URLs that contain
characters like `?`, `&`, or `$`.

```bash
IMAGE='https://katespade.scene7.com/is/image/KateSpade/KP070_001?$desktopProductV5$'

# health-check: mkdir --help
mkdir -p .runtime/pages
# health-check: curl --version
curl --get \
  --fail-with-body \
  --show-error \
  --silent \
  --data-urlencode "imageUrl=$IMAGE" \
  --write-out "\nHTTP %{http_code} %{content_type} saved=%{filename_effective}\n" \
  http://127.0.0.1:8000/google-lens \
  -o .runtime/pages/latest-google-lens.html
```

Expected success output ends with HTTP 200 text/html; curl exits nonzero
for mapped API errors such as 402, 429, 502, or 504.

Opening the API URL in a browser is usually the most faithful view. A saved
Google HTML file can be useful for debugging, but some relative assets and
scripts may not hydrate from a local file.

Errors are mapped explicitly:

- `400`: `imageUrl` is empty, relative, hostless, or not `http`/`https`.
- `402`: the configured MrScraper account is out of credits.
- `429`: Google or the provider returned CAPTCHA, bot-check, or rate-limit HTML.
- `502`: upstream returned an error page or a page that is not Exact Match.
- `504`: provider or Google request timed out.

The hosted Railway endpoint may run out of the shared MrScraper credits during
review. When that happens, retry the same request with your own MrScraper API
key:

```bash
# health-check: curl --version
curl \
  -H "X-MrScraper-Api-Key: atk_your_mrscraper_api_key" \
  "$HOST/google-lens?imageUrl=$IMAGE"
```

## Request Flow

Request path: client to FastAPI, parse `imageUrl`, enter the concurrency
limiter, fetch `https://lens.google.com/uploadbyurl?url=<image>` through
MrScraper, extract the generated `udm=48` Exact Match URL, fetch that URL,
classify the HTML, and return the raw page.

Local HTTP probes against Google returned `403` pages, so live traffic goes
through MrScraper's API-token HTML fetch mode. The application code owns the URL
construction, pacing, response classification, and failure mapping.

## Provider And Anti-Bot Strategy

MrScraper is the Google-facing fetch layer. The app builds the target Google URL
and sends it to MrScraper like this:

Provider request shape: `GET https://api.mrscraper.com?token=<token>&html=true&super=true&url=<google_url>`.

The local side keeps a narrow set of controls:

- Browser-like headers with a stable desktop Chrome user agent.
- Process-wide concurrency capped by `MAX_CONCURRENCY`.
- Randomized local pacing from `REQUEST_DELAY_MIN_SECONDS` to
  `REQUEST_DELAY_MAX_SECONDS`.
- A shared `httpx.AsyncClient` for provider requests.
- HTML classification before success. CAPTCHA, Google sorry pages, Google
  errors, empty bodies, and ambiguous pages do not return `200`.

## Run Locally

Requirements:

- Python 3.12+
- `uv` for the preferred setup path, or `pip` for the standard-library setup
  path
- A MrScraper API token for live Lens requests

Install with `uv`:

```bash
# health-check: uv --version
uv venv --python 3.12 .venv
# health-check: test -f .venv/bin/activate
source .venv/bin/activate
# health-check: uv --version
uv pip install -e ".[dev]"
```

Install with `pip`:

```bash
# health-check: python3 --version
python3 -m venv .venv
# health-check: test -f .venv/bin/activate
source .venv/bin/activate
# health-check: python3 -m pip --version
python3 -m pip install -e ".[dev]"
```

Configure:

```bash
# health-check: test -f .env.example
cp .env.example .env
```

Set `MRSCRAPER_API_KEY` in `.env` or in the process environment.

Run:

```bash
# health-check: test -f .venv/bin/activate
source .venv/bin/activate
# health-check: python3 -c "import app.main; app.main.create_app()"
uvicorn app.main:app --reload
```

Run locally with diagnostic server logs:

```bash
# health-check: test -f .venv/bin/activate
source .venv/bin/activate
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

`LOG_LEVEL=DEBUG` affects server logs only. The public API response stays the
same, so provider details and internal traces are not returned to remote
callers.

Quick local request:

```bash
IMAGE='https://katespade.scene7.com/is/image/KateSpade/KP070_001?$desktopProductV5$'

# health-check: curl --version
curl 'http://127.0.0.1:8000/healthz'
# health-check: curl --version
curl "http://127.0.0.1:8000/google-lens?imageUrl=$IMAGE"
```

Equivalent single scrape through the measurement script:

```bash
# health-check: python3 scripts/measure_lens_api.py --help
python3 scripts/measure_lens_api.py \
  --base-url http://127.0.0.1:8000 \
  --image-url "$IMAGE" \
  --requests 1 \
  --concurrency 1 \
  --timeout-seconds 90 \
  --verbose
```

`--concurrency 1` means one request at a time. `--concurrency 0` is invalid
because every scrape needs at least one worker slot.

## Configuration

Copy `.env.example` to `.env` and set `MRSCRAPER_API_KEY`. The rest can stay on
the submitted defaults unless you are re-running load tests.

```dotenv
MRSCRAPER_API_KEY=atk_your_mrscraper_api_key
MRSCRAPER_API_URL=https://api.mrscraper.com

GOOGLE_BASE_URL=https://lens.google.com/uploadbyurl
REQUEST_TIMEOUT_SECONDS=60.0
LOG_LEVEL=INFO

MAX_CONCURRENCY=16
REQUEST_DELAY_MIN_SECONDS=0.0
REQUEST_DELAY_MAX_SECONDS=0.25

MRSCRAPER_BLOCK_RESOURCES=false
USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
```

The app parses these once at startup. Process environment variables override
matching `.env` values. Keep hosted production at `LOG_LEVEL=INFO` or higher;
use `LOG_LEVEL=DEBUG` locally when you need provider-hop and request lifecycle
diagnostics in the server logs.

## Verification

Local checks:

```bash
# health-check: python3 -m unittest --help
python3 -m unittest discover -s tests -p 'test_*.py'
# health-check: python3 -m compileall --help
python3 -m compileall -q app tests scripts
```

Small hosted measurement:

```bash
# health-check: python3 scripts/measure_lens_api.py --help
python3 scripts/measure_lens_api.py --base-url "$HOST" --image-url "$IMAGE" --requests 5 --concurrency 2 --min-valid-exact 1 --max-average-latency-seconds 60 --max-error-rate 0.5
```

167-request load estimate:

```bash
# health-check: python3 scripts/measure_lens_api.py --help
python3 scripts/measure_lens_api.py --base-url "$HOST" --image-url-file path/to/image-urls.txt --requests 167 --concurrency 16 --rate-per-minute 16.7 --randomize-image-urls --image-url-seed 20260516
```

Full one-hour profile:

```bash
# health-check: python3 scripts/measure_lens_api.py --help
python3 scripts/measure_lens_api.py --base-url "$HOST" --image-url-file path/to/image-urls.txt --requests 1000 --concurrency 16 --rate-per-minute 16.7 --randomize-image-urls --image-url-seed 20260516 --target challenge
```

Measurement artifacts are written under `.runtime/runs/lens-measure-*`.

## Optimization Notes

Most request time is provider-side Google Lens fetch time. The local wins came
from keeping enough upstream work in flight and rejecting bad Google pages
before they could count as successful API responses.

Selected runtime settings:

- `MAX_CONCURRENCY=16` per API process.
- `REQUEST_DELAY_MIN_SECONDS=0.0` and `REQUEST_DELAY_MAX_SECONDS=0.25`.
- Shared process-scoped `httpx.AsyncClient` for provider requests.
- `MRSCRAPER_BLOCK_RESOURCES=false`.
- No MrScraper `geoCode` override.

Experiment history:

| Experiment | Why I tried it | Code/config change | Result | Decision |
| --- | --- | --- | --- | --- |
| Baseline | Establish the first live read on the MrScraper API-token path. | `MAX_CONCURRENCY=4`, `REQUEST_DELAY_MIN_SECONDS=0.25`, `REQUEST_DELAY_MAX_SECONDS=1.5`. | 84 requests, 84 valid, 0% errors, 26.19s avg, 34.25s max. | Solid correctness baseline, but likely under-feeding the provider for the one-hour target. |
| Concurrency 8 | See whether more upstream slots improved throughput without hurting validity. | Raised the in-process limiter to 8 and reused one process-scoped `httpx.AsyncClient` instead of creating a client per fetch path. | 84 requests, 84 valid, 0% errors, 49.02s avg, 59.36s max. | Rejected. Validity held, but latency moved right up against the 60s target. |
| Concurrency 16 | Test whether a higher queue depth gave better observed hourly capacity. | Set `MAX_CONCURRENCY=16`; kept the shared client and the two-hop Lens/Exact Match flow unchanged. | 48 requests, 48 valid, 0% errors, 28.62s avg, 40.49s max. | Kept. Better throughput signal without sacrificing Exact Match validity. |
| Low jitter | Remove local waiting that was not buying reliability. | Changed jitter defaults from 0.25-1.5s to `REQUEST_DELAY_MIN_SECONDS=0.0` and `REQUEST_DELAY_MAX_SECONDS=0.25`. | 18 requests, 18 valid, 0% errors, 22.22s avg, 26.48s max. | Kept. This was the cleanest latency win. |
| Provider resource blocking | MrScraper exposes a resource-blocking hint; since this API returns HTML, blocking images/CSS/fonts looked plausible. | Added `MRSCRAPER_BLOCK_RESOURCES` and passed `blockResources=true` into the MrScraper API URL when enabled. | 18 requests, 18 valid, 0% errors, 49.26s avg, 76.13s max. | Rejected. It preserved validity but made the Lens flow slower. |
| HTTPX pool tuning | Check whether matching the HTTP pool exactly to the 16-slot limiter improved queueing. | Changed pool limits to `max_connections=16`, `max_keepalive_connections=16`, and a longer keepalive expiry for the trial. | 18 requests, 18 valid, 0% errors, 25.66s avg, 32.29s max. | Rejected. The default `max(MAX_CONCURRENCY * 2, 20)` connection policy was faster. |
| First-hop early cutoff | Saved Lens fixtures showed the `udm=48` link before the end of the first response, so streaming might avoid reading unnecessary HTML. | Tried streaming the Lens-entry response and stopping once the Exact Match link appeared, then fetching the extracted URL as usual. | 18 requests, 18 valid, 0% errors, 24.88s avg, 31.25s max. | Rejected. The cutoff fired, but the first provider hop had already taken most of the time. |
| Provider geo override | Test whether forcing US routing improved Google localization or provider scheduling. | Added `geoCode=US` to the MrScraper fetch parameters for the trial. | 18 requests, 6 valid, 66.7% errors, 32.14s avg, 51.65s max. | Rejected immediately. It broke validity. |

The most useful surprise was the early-cutoff result. I expected local HTML
reading to matter because the first Lens page can be large. In live runs, the
slow part had already happened before the Exact Match link arrived, and the
second `udm=48` fetch was usually much faster. That pushed the optimization
work toward concurrency and provider pacing instead of clever local parsing.
