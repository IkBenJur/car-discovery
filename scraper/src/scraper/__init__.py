import logging
import os
import sys

from dotenv import load_dotenv

from scraper.autoscout import AutoScoutError, AutoScoutScraper


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    api_key = os.environ.get("SCRAPERAPI_KEY")
    if not api_key:
        sys.exit("SCRAPERAPI_KEY is not set (copy .env.example to .env)")

    scraper = AutoScoutScraper(api_key)
    try:
        page = scraper.get_listings(page=1)
        print(
            f"Wrote {page.dump_path} "
            f"({len(page.listings)} listings, {page.number_of_pages} pages)"
        )
        todo = scraper.unparsed(page.listings)
        if not todo:
            print("No unparsed offers on this page")
            return
        result = scraper.get_offer(todo[0])
        print(f"Wrote {result.path}")
    except AutoScoutError as e:
        sys.exit(f"Scrape failed: {e}")
