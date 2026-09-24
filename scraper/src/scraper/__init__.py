import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from scraper.autoscout import AutoScoutError, AutoScoutScraper
from scraper.clients import Client, ScraperAPIHttpClient, ZenRowsHttpClient

CLIENTS = {
    "scraperapi": ("SCRAPERAPI_KEY", ScraperAPIHttpClient),
    "zenrows": ("ZENROWS_API_KEY", ZenRowsHttpClient),
}


def make_client(name: str) -> Client:
    env_var, client_class = CLIENTS[name]
    api_key = os.environ.get(env_var)
    if not api_key:
        sys.exit(f"{env_var} is not set (copy .env.example to .env)")
    return client_class(api_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape new AutoScout24 offers.")
    parser.add_argument(
        "--client",
        choices=CLIENTS,
        default="scraperapi",
        help="scraping API to route requests through (default: scraperapi)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    scraper = AutoScoutScraper(make_client(args.client))
    try:
        result = scraper.scrape_new()
        print(
            f"Stopped ({result.stop_reason}) after {result.pages} page(s): "
            f"{len(result.offers)} new offer(s), stop date "
            f"{result.stop_date.strftime('%d-%m-%Y')}"
        )
    except AutoScoutError as e:
        sys.exit(f"Scrape failed: {e}")
