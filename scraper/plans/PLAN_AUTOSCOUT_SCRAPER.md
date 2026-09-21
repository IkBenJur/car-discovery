# AutoScoutScraper plan

## Scope
Add `scraper/src/scraper/autoscout.py` with a class `AutoScoutScraper`. It is synchronous and uses `scraperapi_sdk`. It has three operations, each of which writes a JSON dump, plus a tracker for offers already handled. Parsing is out of scope.

## Public API

```python
class AutoScoutScraper:
    def __init__(self, api_key: str, *,
                 output_dir: Path = "data/dumps",
                 state_path: Path = "data/parsed_offers.json",
                 request_params: dict | None = None,   # forwarded to ScraperAPI (country_code, premium, ...)
                 min_delay: float = 0.0,
                 max_retries: int = 3)

    def get_build_id(self, force: bool = False) -> str
    def get_listings(self, params: dict | None = None, page: int = 1) -> ListingsPage
    def get_offer(self, listing: dict, force: bool = False) -> OfferResult

    # tracker helpers
    def is_parsed(self, listing_id: str) -> bool
    def unparsed(self, listings: list[dict]) -> list[dict]
    def mark_parsed(self, listing_id: str, path: Path) -> None
```

## 1. `get_build_id`
- Fetch `https://www.autoscout24.com/` and read `buildId` from the `<script id="__NEXT_DATA__">` JSON.
- Cache the result on the instance. `force=True` refetches it.
- Fetch the list page as HTML (`/lst?<default params>`, no `.json`), not the homepage. The homepage did not yield a usable `buildId` in a live run.
- Raise `BuildIdNotFound` if the script tag or key is missing.
- See `scraper/plans/NEXT_BUILD_ID.md`.

## 2. `get_listings`
- URL: `_next/data/{buildId}/lst.json?{query}`.
- Default params: `cy=NL, damaged_listing=exclude, desc=1, powertype=kw, sort=age, ustate=N,U, atype=C`.
- The caller's dict is merged over the defaults, and `page` is set from the argument.
- The tracking params (`search_id`, `utm_*`, `source`) are dropped.
- One page per call. The caller loops using `numberOfPages` from the result.
- Dump: `{output_dir}/list/{UTC timestamp}_page{n}.json`. It holds the full response as received, pretty-printed.
- Return `ListingsPage(listings, number_of_pages, number_of_results, dump_path)`, read from `pageProps`.
- The real dump has 20 listings per page, 200 pages and about 271k results.

## 3. `get_offer`
- Input is a listing dict from the list dump.
- The tracking key is `listing["id"]`, a GUID. It also appears at the end of the slug.
- The slug is `listing["url"]` with the `/offers/` prefix removed.
- URL: `_next/data/{buildId}/details/{slug}.json`. This returns JSON, and `test-files/auto-scout/offer_dump.json` is a real example.
- Dump: `{output_dir}/offers/{id}.json`, the full response as received.
- If the offer is already parsed and `force=False`, skip it and return `OfferResult(skipped=True, path=...)`.
- After the dump is written successfully, call `mark_parsed`. A failed fetch is never marked.

## Tracker
- The state file is JSON: `{listing_id: {"parsed_at": ISO8601, "dump": relpath}}`.
- It is loaded in `__init__` and written atomically (temp file, then `os.replace`) on every mark.
- `unparsed()` filters a list by id.
- The file is small enough that no database is needed. If it grows, SQLite can replace it without changing the API.

## Request layer
All HTTP goes through one private method, `_get_json(path)`.
1. Sleep for the remainder of `min_delay` since the last request.
2. Call `client.get(url=..., **request_params)`.
3. Log one line per request: URL, duration, attempt number, status.
4. `json.loads` the body.

Failure handling:
- Retry with exponential backoff on transient `ScraperAPIException`s, up to `max_retries`.
- A 404, redirect, or non-JSON body means the buildId is probably stale. Refresh it once with `get_build_id(force=True)`, rebuild the URL, and retry.
- If that still fails, raise a typed error:
  - `AutoScoutError` (base)
  - `BuildIdNotFound`
  - `StaleBuildId`
  - `RequestFailed`
- Nothing swallows errors, and failed offers stay unmarked.

## Wiring and config
- Update `main()`:
  - Read `SCRAPERAPI_KEY`.
  - Fetch list page 1.
  - Pick the first unparsed listing.
  - Fetch that offer.
  - Print the dump paths.
- Remove the hardcoded URL constants in `__init__.py`.
- Add `data/` to `.gitignore`.
- Add `pytest` as a dev dependency.

## Tests (`scraper/tests/`)
Use a `FakeClient` that serves fixtures from `test-files/auto-scout/`. `list_dump.json` is the list response. `offer_dump.json` is the offer response.
1. **buildId:** parse a small HTML fixture, check caching, check `BuildIdNotFound`.
2. **URLs:** the list URL merges and drops params correctly, and the offer slug and URL are built correctly.
3. **Stale buildId:** the client returns HTML or a 404 first, then JSON. This checks a single refresh and retry.
4. **Tracker:** `mark_parsed`, persistence across instances, `unparsed`, `force=True`, and no mark after a failed fetch.
5. **Dumps:** files land at the expected paths and hold the full response.
6. **Retries:** backoff is used and gives up after `max_retries`.

## Build order
1. Exceptions, the tracker, and their tests.
2. The request layer, `get_build_id`, and their tests.
3. `get_listings` and `get_offer`, with tests.
4. `main()` demo, `.gitignore`, and updating the docs.
5. One live run with a real key. It checks the list-page buildId and the offer route end to end.

## Open items
- **Skip default:** confirm `get_offer` should skip parsed offers by default (the "helpers only" answer implied otherwise).
- **List-page buildId:** confirmed only by a live run (step 5).
- **Sold or removed offers:** out of scope. They currently raise `RequestFailed`.
