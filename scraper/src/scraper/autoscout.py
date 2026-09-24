import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from scraper.clients import Client, ClientError

logger = logging.getLogger(__name__)

BASE_URL = "https://www.autoscout24.com/"
DEFAULT_LIST_PARAMS = {
    "cy": "NL",
    "damaged_listing": "exclude",
    "desc": "1",
    "powertype": "kw",
    "sort": "age",
    "ustate": "N,U",
    "atype": "C",
}
BUILD_ID_PAGE = "lst?" + urlencode(DEFAULT_LIST_PARAMS)
# Tracking params that don't affect results.
DROPPED_PARAMS = {"search_id", "source"}
OFFER_PREFIX = "/offers/"
# Offer dates are compared as calendar days in the market's timezone.
LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
# Only organic results follow the sort order; promoted ones may be moved up.
ORGANIC = "Organic"

_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


class AutoScoutError(Exception):
    """Base class for scraper errors."""


class BuildIdNotFound(AutoScoutError):
    """No buildId could be read from the page."""


class StaleBuildId(AutoScoutError):
    """The data route still failed after refreshing the buildId."""


class RequestFailed(AutoScoutError):
    """A request failed after all retries."""


@dataclass
class ListingsPage:
    listings: list[dict]
    number_of_pages: int
    number_of_results: int
    dump_path: Path


@dataclass
class OfferResult:
    listing_id: str
    path: Path
    skipped: bool = False
    created: datetime | None = None


@dataclass
class ScrapeResult:
    stop_date: date
    stop_reason: str  # "parsed", "date", "end" or "max_pages"
    pages: int
    offers: list[OfferResult]


def offer_created(data: dict) -> datetime | None:
    """The offer's createdTimestampWithOffset, from an offer dump."""
    details = data.get("pageProps", {}).get("listingDetails", {})
    raw = details.get("createdTimestampWithOffset")
    return _parse_timestamp(raw)


def local_date(timestamp: datetime) -> date:
    return timestamp.astimezone(LOCAL_TZ).date()


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Unparseable timestamp %r", raw)
        return None


class _StaleRoute(Exception):
    """Internal: response suggests the buildId is outdated."""


class ParsedOfferTracker:
    """JSON-file-backed record of offers whose dump has been written."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._state: dict[str, dict] = {}
        if self.path.exists():
            self._state = json.loads(self.path.read_text())

    def is_parsed(self, listing_id: str) -> bool:
        return listing_id in self._state

    def get(self, listing_id: str) -> dict | None:
        return self._state.get(listing_id)

    def ids(self) -> set[str]:
        return set(self._state)

    def created(self, listing_id: str) -> datetime | None:
        return _parse_timestamp((self._state.get(listing_id) or {}).get("created"))

    def newest_created(self) -> datetime | None:
        timestamps = [self.created(listing_id) for listing_id in self._state]
        return max((t for t in timestamps if t), default=None)

    def mark(self, listing_id: str, dump: str, created: datetime | None = None) -> None:
        self._state[listing_id] = {
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "dump": dump,
            "created": created.isoformat() if created else None,
        }
        self._save()

    def backfill_created(self, dump_dir: Path) -> None:
        """Fill in `created` for entries recorded before it was tracked."""
        changed = False
        for record in self._state.values():
            if "created" in record:
                continue
            dump = dump_dir / record.get("dump", "")
            try:
                created = offer_created(json.loads(dump.read_text()))
            except (OSError, ValueError):
                logger.warning("Cannot backfill created from %s", dump)
                continue
            record["created"] = created.isoformat() if created else None
            changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._state, indent=2))
        os.replace(tmp, self.path)


class AutoScoutScraper:
    def __init__(
        self,
        client: Client,
        *,
        output_dir: Path | str = "data/dumps",
        state_path: Path | str = "data/parsed_offers.json",
        request_params: dict | None = None,
        min_delay: float = 0.0,
        max_retries: int = 3,
        sleep=time.sleep,
    ):
        self._client = client
        self.output_dir = Path(output_dir)
        self.request_params = dict(request_params or {})
        self.min_delay = min_delay
        self.max_retries = max_retries
        self._sleep = sleep
        self._tracker = ParsedOfferTracker(Path(state_path))
        self._tracker.backfill_created(self.output_dir)
        self._build_id: str | None = None
        self._last_request = 0.0

    # -- buildId ---------------------------------------------------------

    def get_build_id(self, force: bool = False) -> str:
        if self._build_id and not force:
            return self._build_id
        # The list page (HTML, not the .json route) is served by the same
        # Next.js app as the data routes, so its buildId is the right one.
        html = self._fetch(BASE_URL + BUILD_ID_PAGE)

        should_parse_bytes_to_str = isinstance(html, (bytes, bytearray))
        if should_parse_bytes_to_str:
            html = html.decode("utf-8", errors="replace")

        is_not_string = not isinstance(html, str)
        if is_not_string:
            raise BuildIdNotFound("List page did not return HTML")

        match = _NEXT_DATA_RE.search(html)
        if not match:
            raise BuildIdNotFound("__NEXT_DATA__ script not found")

        try:
            build_id = json.loads(match.group(1))["buildId"]
        except (ValueError, KeyError, TypeError) as e:
            raise BuildIdNotFound("buildId missing from __NEXT_DATA__") from e

        self._build_id = build_id
        logger.info("buildId = %s", build_id)
        return build_id

    # -- listings --------------------------------------------------------

    def get_listings(self, params: dict | None = None, page_number: int = 1) -> ListingsPage:
        query = {**DEFAULT_LIST_PARAMS, **(params or {})}
        for key in DROPPED_PARAMS:
            query.pop(key, None)
        query = {k: v for k, v in query.items() if not k.startswith("utm_")}
        query["page"] = page_number
        query_string = urlencode(query)
        data = self._get_data_json(lambda build_id: f"_next/data/{build_id}/lst.json?{query_string}")

        time_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.output_dir / "list" / f"{time_stamp}_page{page_number}.json"
        self._write_dump(path, data)

        props = data.get("pageProps", {})
        return ListingsPage(
            listings=props.get("listings", []),
            number_of_pages=props.get("numberOfPages", 0),
            number_of_results=props.get("numberOfResults", 0),
            dump_path=path,
        )

    # -- offers ----------------------------------------------------------

    def get_offer(self, listing: dict, force: bool = False) -> OfferResult:
        listing_id = listing["id"]
        if not force and self.is_parsed(listing_id):
            recorded = self._tracker.get(listing_id) or {}

            # Create dump result when already parsed
            return OfferResult(
                listing_id,
                self.output_dir / recorded.get("dump", ""),
                skipped=True,
                created=self._tracker.created(listing_id),
            )

        slug = self._slug(listing)
        data = self._get_data_json(lambda build_id: f"_next/data/{build_id}/details/{slug}.json")

        path = self.output_dir / "offers" / f"{listing_id}.json"
        self._write_dump(path, data)
        created = offer_created(data)
        self.mark_parsed(listing_id, path, created)
        return OfferResult(listing_id, path, created=created)

    @staticmethod
    def _slug(listing: dict) -> str:
        url = listing["url"]
        return url[len(OFFER_PREFIX):] if url.startswith(OFFER_PREFIX) else url.lstrip("/")

    # -- scrape loop -----------------------------------------------------

    def stop_date(self, today: date | None = None) -> date:
        """Oldest day still scraped: the day of the newest parsed offer,
        or yesterday when nothing has been parsed yet."""
        newest = self._tracker.newest_created()
        if newest:
            return local_date(newest)
        today = today or datetime.now(LOCAL_TZ).date()
        return today - timedelta(days=1)

    def scrape_new(
        self,
        params: dict | None = None,
        *,
        max_pages: int | None = None,
        today: date | None = None,
    ) -> ScrapeResult:
        """Walk list pages newest-first, parsing offers until an organic
        listing parsed in a previous run shows up, or an organic offer is
        older than the stop date."""
        stop = self.stop_date(today)
        previously_parsed = self._tracker.ids()
        offers: list[OfferResult] = []
        logger.info("Scraping until a parsed offer or before %s", stop.strftime("%d-%m-%Y"))

        def done(reason: str, pages: int) -> ScrapeResult:
            logger.info("Stopped (%s) after %d page(s), %d new offer(s)", reason, pages, len(offers))
            return ScrapeResult(stop, reason, pages, offers)

        page_number = 1
        while True:
            page = self.get_listings(params, page_number)
            for listing in page.listings:
                organic = listing.get("searchResultType") == ORGANIC
                if organic and listing["id"] in previously_parsed:
                    return done("parsed", page_number)

                result = self.get_offer(listing)
                if not result.skipped:
                    offers.append(result)
                if not organic: # Non organic post can be bumped up. So dates might not allign with others.
                    continue
                if result.created is None:
                    logger.warning("No created timestamp for %s", result.listing_id)
                    continue
                if local_date(result.created) < stop:
                    return done("date", page_number)

            if not page.listings or page_number >= page.number_of_pages:
                return done("end", page_number)
            if max_pages and page_number >= max_pages:
                return done("max_pages", page_number)
            page_number += 1

    # -- tracker helpers -------------------------------------------------

    def is_parsed(self, listing_id: str) -> bool:
        return self._tracker.is_parsed(listing_id)

    def unparsed(self, listings: list[dict]) -> list[dict]:
        return [l for l in listings if not self.is_parsed(l["id"])]

    def mark_parsed(
        self, listing_id: str, path: Path, created: datetime | None = None
    ) -> None:
        try:
            recorded = str(Path(path).relative_to(self.output_dir))
        except ValueError:
            recorded = str(path)
        self._tracker.mark(listing_id, recorded, created)

    # -- request layer ---------------------------------------------------

    def _write_dump(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _get_data_json(self, build_path) -> dict:
        """Fetch a Next.js data route, refreshing the buildId once if stale."""
        build_id = self.get_build_id(force=False)
        try:
            return self._get_json(BASE_URL + build_path(build_id))
        except _StaleRoute:
            logger.warning("Data route failed with buildId %s", build_id)

        # Try again but this time with new build_id
        build_id = self.get_build_id(force=True)
        try:
            return self._get_json(BASE_URL + build_path(build_id))
        except _StaleRoute:
            logger.warning("Data route failed with buildId %s", build_id)

        # New build_id didn't help
        raise StaleBuildId("Data route failed even after refreshing the buildId")

    def _get_json(self, url: str) -> dict:
        body = self._fetch(url, stale_on_404=True)

        should_parse_bytes_to_str = isinstance(body, (bytes, bytearray))
        if should_parse_bytes_to_str:
            body = body.decode("utf-8", errors="replace")

        is_string = isinstance(body, str)
        if is_string:
            try:
                body = json.loads(body)
            except ValueError:
                raise _StaleRoute(url)

        if not isinstance(body, dict):
            raise _StaleRoute(url)

        return body

    def _fetch(self, url: str, stale_on_404: bool = False) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._respect_delay()
            started = time.monotonic()
            try:
                result = self._client.get(
                    url=url, params=dict(self.request_params) or None
                )
            except ClientError as e:
                status = e.status_code
                logger.info(
                    "GET %s attempt=%d status=%s %.2fs",
                    url, attempt, status, time.monotonic() - started,
                )
                if stale_on_404 and status in (404, 410):
                    raise _StaleRoute(url) from e
                last_error = e
                if attempt < self.max_retries:
                    self._sleep(2 ** (attempt - 1))
                continue
            logger.info(
                "GET %s attempt=%d status=200 %.2fs",
                url, attempt, time.monotonic() - started,
            )
            return result
        raise RequestFailed(
            f"{url} failed after {self.max_retries} attempts"
        ) from last_error

    def _respect_delay(self) -> None:
        if self.min_delay:
            wait = self.min_delay - (time.monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = time.monotonic()
