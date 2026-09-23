import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scraperapi_sdk import ScraperAPIException

from scraper.autoscout import (
    AutoScoutScraper,
    BuildIdNotFound,
    RequestFailed,
    StaleBuildId,
)

FIXTURES = Path(__file__).resolve().parents[1] / "test-files" / "auto-scout"
LIST_JSON = (FIXTURES / "list_dump.json").read_text()
OFFER_JSON = (FIXTURES / "offer_dump.json").read_text()


def home_html(build_id: str) -> str:
    data = json.dumps({"buildId": build_id, "page": "/"})
    return f'<html><script id="__NEXT_DATA__" type="application/json">{data}</script></html>'


def is_html_page(url: str) -> bool:
    """The buildId page: https://www.autoscout24.com/lst?... (not /_next/data)."""
    return url.startswith("https://www.autoscout24.com/lst?")


def http_error(status: int) -> ScraperAPIException:
    original = Exception("boom")
    original.response = SimpleNamespace(status_code=status)
    return ScraperAPIException("failed", original)


class FakeClient:
    """Serves fixtures; `build_ids` is the sequence of list-page build IDs."""

    def __init__(self, build_ids=("b1",), current="b1"):
        self.build_ids = list(build_ids)
        self.current = current  # the buildId the "server" accepts
        self.calls: list[str] = []
        self.errors: list[Exception] = []  # popped before serving anything

    def get(self, url, params=None, headers=None):
        self.calls.append(url)
        if self.errors:
            raise self.errors.pop(0)
        if is_html_page(url):
            return home_html(self.build_ids.pop(0) if len(self.build_ids) > 1 else self.build_ids[0])
        if f"/_next/data/{self.current}/" not in url:
            raise http_error(404)
        return LIST_JSON if "/lst.json" in url else OFFER_JSON


@pytest.fixture
def listing():
    return json.loads(LIST_JSON)["pageProps"]["listings"][0]


def make(tmp_path, client, **kw):
    return AutoScoutScraper(
        "key",
        client=client,
        output_dir=tmp_path / "dumps",
        state_path=tmp_path / "state.json",
        sleep=lambda s: None,
        **kw,
    )


def test_build_id_parsed_and_cached(tmp_path):
    client = FakeClient()
    s = make(tmp_path, client)
    assert s.get_build_id() == "b1"
    assert s.get_build_id() == "b1"
    assert len(client.calls) == 1
    s.get_build_id(force=True)
    assert len(client.calls) == 2


def test_build_id_not_found(tmp_path):
    client = FakeClient()
    client.get = lambda url, params=None, headers=None: "<html></html>"
    with pytest.raises(BuildIdNotFound):
        make(tmp_path, client).get_build_id()


def test_list_url_merges_and_drops_params(tmp_path):
    client = FakeClient()
    s = make(tmp_path, client)
    s.get_listings(
        {"cy": "DE", "search_id": "x", "utm_source": "y", "source": "z"}, page_number=3
    )
    url = client.calls[-1]
    assert "/_next/data/b1/lst.json?" in url
    for expected in ("cy=DE", "powertype=kw", "ustate=N%2CU", "page=3"):
        assert expected in url
    for dropped in ("search_id", "utm_", "source="):
        assert dropped not in url


def test_get_listings_dump_and_result(tmp_path):
    s = make(tmp_path, FakeClient())
    page = s.get_listings(page_number=2)
    assert page.dump_path.parent == tmp_path / "dumps" / "list"
    assert page.dump_path.name.endswith("_page2.json")
    assert json.loads(page.dump_path.read_text()) == json.loads(LIST_JSON)
    assert len(page.listings) == 20
    assert page.number_of_pages == 200


def test_get_offer_url_dump_and_tracking(tmp_path, listing):
    client = FakeClient()
    s = make(tmp_path, client)
    assert not s.is_parsed(listing["id"])
    result = s.get_offer(listing)
    slug = listing["url"].removeprefix("/offers/")
    assert client.calls[-1].endswith(f"/_next/data/b1/details/{slug}.json")
    assert result.path == tmp_path / "dumps" / "offers" / f"{listing['id']}.json"
    assert json.loads(result.path.read_text()) == json.loads(OFFER_JSON)
    assert s.is_parsed(listing["id"])


def test_parsed_offer_skipped_unless_forced(tmp_path, listing):
    client = FakeClient()
    s = make(tmp_path, client)
    s.get_offer(listing)
    n = len(client.calls)
    again = s.get_offer(listing)
    assert again.skipped and again.path.exists()
    assert len(client.calls) == n
    assert not s.get_offer(listing, force=True).skipped
    assert len(client.calls) > n


def test_tracker_persists_and_filters(tmp_path, listing):
    s = make(tmp_path, FakeClient())
    listings = [listing, {**listing, "id": "other"}]
    s.get_offer(listing)
    assert s.unparsed(listings) == [listings[1]]
    s2 = make(tmp_path, FakeClient())
    assert s2.is_parsed(listing["id"])
    assert s2.unparsed(listings) == [listings[1]]


def test_stale_build_id_refreshes_once(tmp_path):
    client = FakeClient(build_ids=["old", "new"], current="new")
    s = make(tmp_path, client)
    page = s.get_listings()
    assert len(page.listings) == 20
    assert s.get_build_id() == "new"
    assert sum(is_html_page(u) for u in client.calls) == 2


def test_stale_build_id_gives_up(tmp_path):
    client = FakeClient(build_ids=["old"], current="never")
    with pytest.raises(StaleBuildId):
        make(tmp_path, client).get_listings()


def test_html_response_treated_as_stale(tmp_path):
    client = FakeClient(build_ids=["old", "new"], current="new")
    real_get = client.get

    def get(url, params=None, headers=None):
        if "/_next/data/old/" in url:
            return "<html>not json</html>"
        return real_get(url, params, headers)

    client.get = get
    assert len(make(tmp_path, client).get_listings().listings) == 20


def test_retries_with_backoff_then_succeeds(tmp_path):
    sleeps = []
    client = FakeClient()
    client.errors = [http_error(500), http_error(500)]
    s = make(tmp_path, client)
    s._sleep = sleeps.append
    assert s.get_build_id() == "b1"
    assert sleeps == [1, 2]


def test_gives_up_after_max_retries_and_does_not_mark(tmp_path, listing):
    client = FakeClient()
    s = make(tmp_path, client, max_retries=2)
    s.get_build_id()
    client.errors = [http_error(500), http_error(500)]
    with pytest.raises(RequestFailed):
        s.get_offer(listing)
    assert not s.is_parsed(listing["id"])
    assert not (tmp_path / "dumps" / "offers").exists()


def test_min_delay(tmp_path):
    sleeps = []
    s = make(tmp_path, FakeClient(), min_delay=5.0)
    s._sleep = sleeps.append
    s.get_build_id()
    s.get_listings()
    assert sleeps and all(0 < x <= 5.0 for x in sleeps)
