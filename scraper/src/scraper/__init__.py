import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from scraperapi_sdk import ScraperAPIClient, ScraperAPIException

# Hello-world target: a public JSON endpoint. Replace with the real
# server API endpoints (not the HTML pages) once we know them.
BASE_URL = "https://www.autoscout24.com/"
OFFER_LIST_URL = "_next/data/as24-search-funnel_main-20260921184940/lst.json?cy=NL&damaged_listing=exclude&desc=1&powertype=kw&sort=age&ustate=N%2CU&atype=C&search_id=163cuvuu3hl&source=listpage_pagination&utm_campaign=EN_as24_crm_web-push_system_last-search&utm_medium=web-push&utm_source=as24_crm&page=1"
OFFER_URL = "_next/data/as24-search-funnel_main-20260921184940/details/bmw-x5-4-4i-executive-gasoline-green-cat_ma13mo16406-1a4d45bf-6522-4958-8323-a2ad75efc533.json"

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "test-files" / "auto-scout" / "offer_dump.json"


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("SCRAPERAPI_KEY")
    if not api_key:
        sys.exit("SCRAPERAPI_KEY is not set (copy .env.example to .env)")

    client = ScraperAPIClient(api_key)
    try:
        result = client.get(url=BASE_URL + OFFER_URL)
    except ScraperAPIException as e:
        sys.exit(f"Request failed: {e}")

    # JSON endpoints come back as text; parse when possible.
    try:
        result = json.loads(result)
    except (TypeError, ValueError):
        pass
    dump = json.dumps(result, indent=2) if not isinstance(result, str) else result
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(dump)
    print(f"Wrote {OUTPUT_PATH}")
