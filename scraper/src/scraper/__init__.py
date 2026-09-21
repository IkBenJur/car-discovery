import json
import os
import sys

from dotenv import load_dotenv
from scraperapi_sdk import ScraperAPIClient, ScraperAPIException

# Hello-world target: a public JSON endpoint. Replace with the real
# server API endpoints (not the HTML pages) once we know them.
HELLO_URL = "https://httpbin.org/get"


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("SCRAPERAPI_KEY")
    if not api_key:
        sys.exit("SCRAPERAPI_KEY is not set (copy .env.example to .env)")

    client = ScraperAPIClient(api_key)
    try:
        result = client.get(url=HELLO_URL)
    except ScraperAPIException as e:
        sys.exit(f"Request failed: {e}")

    # JSON endpoints come back as text; parse when possible.
    try:
        result = json.loads(result)
    except (TypeError, ValueError):
        pass
    print(json.dumps(result, indent=2) if not isinstance(result, str) else result)
