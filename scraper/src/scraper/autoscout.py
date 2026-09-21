import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from scraperapi_sdk import ScraperAPIClient, ScraperAPIException

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
# Tracking params that don't affect results.
DROPPED_PARAMS = {"search_id", "source"}
OFFER_PREFIX = "/offers/"

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


class _StaleRoute(Exception):
    """Internal: response suggests the buildId is outdated."""


def _status_code(exc: ScraperAPIException) -> int | None:
    response = getattr(exc.original_exception, "response", None)
    return getattr(response, "status_code", None)


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

    def mark(self, listing_id: str, dump: str) -> None:
        self._state[listing_id] = {
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "dump": dump,
        }
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._state, indent=2))
        os.replace(tmp, self.path)


class AutoScoutScraper:
    def __init__(
        self,
        api_key: str,
        *,
        output_dir: Path | str = "data/dumps",
        state_path: Path | str = "data/parsed_offers.json",
        request_params: dict | None = None,
        min_delay: float = 0.0,
        max_retries: int = 3,
        client: Any = None,
        sleep=time.sleep,
    ):
        self._client = client or ScraperAPIClient(api_key)
        self.output_dir = Path(output_dir)
        self.request_params = dict(request_params or {})
        self.min_delay = min_delay
        self.max_retries = max_retries
        self._sleep = sleep
        self._tracker = ParsedOfferTracker(Path(state_path))
        self._build_id: str | None = None
        self._last_request = 0.0

    # -- buildId ---------------------------------------------------------

    def get_build_id(self, force: bool = False) -> str:
        if self._build_id and not force:
            return self._build_id
        html = self._fetch(BASE_URL)
        if isinstance(html, (bytes, bytearray)):
            html = html.decode("utf-8", errors="replace")
        if not isinstance(html, str):
            raise BuildIdNotFound("Homepage did not return HTML")
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

    def get_listings(self, params: dict | None = None, page: int = 1) -> ListingsPage:
        query = {**DEFAULT_LIST_PARAMS, **(params or {})}
        for key in DROPPED_PARAMS:
            query.pop(key, None)
        query = {k: v for k, v in query.items() if not k.startswith("utm_")}
        query["page"] = page
        qs = urlencode(query)
        data = self._get_data_json(lambda b: f"_next/data/{b}/lst.json?{qs}")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.output_dir / "list" / f"{stamp}_page{page}.json"
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
            return OfferResult(
                listing_id, self.output_dir / recorded.get("dump", ""), skipped=True
            )

        slug = self._slug(listing)
        data = self._get_data_json(lambda b: f"_next/data/{b}/details/{slug}.json")

        path = self.output_dir / "offers" / f"{listing_id}.json"
        self._write_dump(path, data)
        self.mark_parsed(listing_id, path)
        return OfferResult(listing_id, path)

    @staticmethod
    def _slug(listing: dict) -> str:
        url = listing["url"]
        return url[len(OFFER_PREFIX):] if url.startswith(OFFER_PREFIX) else url.lstrip("/")

    # -- tracker helpers -------------------------------------------------

    def is_parsed(self, listing_id: str) -> bool:
        return self._tracker.is_parsed(listing_id)

    def unparsed(self, listings: list[dict]) -> list[dict]:
        return [l for l in listings if not self.is_parsed(l["id"])]

    def mark_parsed(self, listing_id: str, path: Path) -> None:
        try:
            recorded = str(Path(path).relative_to(self.output_dir))
        except ValueError:
            recorded = str(path)
        self._tracker.mark(listing_id, recorded)

    # -- request layer ---------------------------------------------------

    def _write_dump(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _get_data_json(self, build_path) -> dict:
        """Fetch a Next.js data route, refreshing the buildId once if stale."""
        for refreshed in (False, True):
            build_id = self.get_build_id(force=refreshed)
            try:
                return self._get_json(BASE_URL + build_path(build_id))
            except _StaleRoute:
                logger.warning("Data route failed with buildId %s", build_id)
        raise StaleBuildId("Data route failed even after refreshing the buildId")

    def _get_json(self, url: str) -> dict:
        body = self._fetch(url, stale_on_404=True)
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8", errors="replace")
        if isinstance(body, str):
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
            except ScraperAPIException as e:
                status = _status_code(e)
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
