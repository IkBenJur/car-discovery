from typing import Any, Protocol

import requests
from scraperapi_sdk import ScraperAPIClient, ScraperAPIException
from zenrows import ZenRowsClient


class ClientError(Exception):
    """A request failed; `status_code` is None for network-level failures."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class Client(Protocol):
    def get(self, url: str, params: dict | None = None) -> Any:
        """Fetch `url` and return its body (str, bytes or parsed JSON).
        Raises ClientError when the request fails."""
        ...


class ScraperAPIHttpClient:
    def __init__(self, api_key: str):
        self._client = ScraperAPIClient(api_key)

    def get(self, url: str, params: dict | None = None) -> Any:
        try:
            return self._client.get(url=url, params=params)
        except ScraperAPIException as e:
            response = getattr(e.original_exception, "response", None)
            status = getattr(response, "status_code", None)
            raise ClientError(f"GET {url} failed", status) from e


class ZenRowsHttpClient:
    def __init__(self, api_key: str, timeout: float = 55):
        # The scraper does its own retries with backoff.
        self._client = ZenRowsClient(api_key, retries=0)
        self._timeout = timeout

    def get(self, url: str, params: dict | None = None) -> str:
        try:
            response = self._client.fetch(url, params=params, timeout=self._timeout)
        except requests.RequestException as e:
            raise ClientError(f"GET {url} failed", None) from e
        # ZenRows returns error responses instead of raising.
        if not response.ok:
            raise ClientError(f"GET {url} failed", response.status_code)
        return response.text
