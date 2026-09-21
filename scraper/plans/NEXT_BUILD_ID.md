# Next.js `buildId` problem (AutoScout24)

AutoScout24 is a Next.js app. Its JSON endpoints live under

```
https://www.autoscout24.com/_next/data/<buildId>/<route>.json
```

e.g.

- list:  `/_next/data/<buildId>/lst.json?<search params>`
- offer: `/_next/data/<buildId>/details/<slug>.json`
  (`<slug>` is the listing `url` from the list JSON with `/offers/` removed;
  the real Next.js route is `/details/[...slug]`)

## The problem

`<buildId>` (e.g. `as24-search-funnel_main-20260921184940`) changes on every
AutoScout24 deploy. A hardcoded ID will stop working (404 / redirect / HTML)
without warning, so the URLs in `src/scraper/__init__.py` are only valid for
the day they were captured.

## Where to get the current buildId

Any normal HTML page contains it in the `__NEXT_DATA__` script:

```html
<script id="__NEXT_DATA__" type="application/json">{"props":..., "buildId":"as24-search-funnel_main-...", "page":"/details/[...slug]", ...}</script>
```

It also appears in asset paths (`/_next/static/<buildId>/_buildManifest.js`).

## Planned implementation (not done yet)

1. Fetch a cheap HTML page (e.g. the homepage or a list page) and extract
   `buildId` from `__NEXT_DATA__`.
2. Cache it in memory for the run.
3. Build data URLs from it.
4. If a data request fails (404, non-JSON, redirect), refetch the `buildId`
   once and retry.
5. Fallback: if the `_next/data` route keeps failing, parse
   `props.pageProps` out of the HTML `__NEXT_DATA__` block, which holds the
   same data (e.g. `listingDetails` for offers) but is ~500 KB per page.
