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
        result = scraper.scrape_new()
        print(
            f"Stopped ({result.stop_reason}) after {result.pages} page(s): "
            f"{len(result.offers)} new offer(s), stop date "
            f"{result.stop_date.strftime('%d-%m-%Y')}"
        )
    except AutoScoutError as e:
        sys.exit(f"Scrape failed: {e}")
