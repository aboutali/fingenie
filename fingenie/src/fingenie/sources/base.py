"""Source-adapter base classes.

``BaseAdapter`` defines the capability-keyed interface the router dispatches to.
Adapters override only the methods for capabilities they advertise.

``BaseHTTPAdapter`` adds the one shared HTTP path: every request goes through
the rate governor (acquire-or-raise) and a tenacity retry that fires only on
transient failures (timeouts, connection errors, 5xx, 429). Per-source code is
then just "build the request" + "parse the payload".
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ..errors import DataNotFound, SourceError, TransientError
from ..models import CanonicalSymbol, Capability, FXRate, OHLCVBar, Quote
from ..ratelimit import RateExhausted, RateGovernor


class BaseAdapter:
    """Interface every source implements. Methods raise ``NotImplementedError``
    unless the subclass advertises (and overrides) the matching capability."""

    name: str = "base"
    needs_key: bool = False

    def capabilities(self) -> set[Capability]:
        raise NotImplementedError

    def get_quote(self, sym: CanonicalSymbol) -> Quote:
        raise NotImplementedError(f"{self.name} does not provide quotes")

    def get_history(
        self,
        sym: CanonicalSymbol,
        *,
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
    ) -> list[OHLCVBar]:
        raise NotImplementedError(f"{self.name} does not provide history")

    def get_fx(self, base: str, quote: str) -> FXRate:
        raise NotImplementedError(f"{self.name} does not provide fx")


def _is_transient_status(status: int) -> bool:
    return status == 429 or 500 <= status < 600


class BaseHTTPAdapter(BaseAdapter):
    """Adapter backed by an httpx client, the rate governor and retry."""

    base_url: str = ""

    def __init__(
        self,
        *,
        governor: RateGovernor,
        client: httpx.Client | None = None,
        user_agent: str = "fingenie/0.1",
        timeout: float = 15.0,
    ) -> None:
        self._governor = governor
        self._user_agent = user_agent
        self._client = client or httpx.Client(
            timeout=timeout, headers={"User-Agent": user_agent}
        )

    # -- the single shared request method -------------------------------------
    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        # Rate budget is checked once per logical request (before retries).
        self._governor.acquire(self.name)

        @retry(
            retry=retry_if_exception_type(TransientError),
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=8.0),
            reraise=True,
        )
        def _do() -> httpx.Response:
            try:
                resp = self._client.request(
                    method, url, params=params, json=json, headers=headers
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise TransientError(f"{self.name}: {exc!r}") from exc
            if _is_transient_status(resp.status_code):
                raise TransientError(f"{self.name}: HTTP {resp.status_code}")
            return resp

        return _do()

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return self._request("GET", self._url(path), params=params, headers=headers)

    def _post(
        self,
        path: str,
        *,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return self._request("POST", self._url(path), json=json, headers=headers)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    @staticmethod
    def _json_or_raise(resp: httpx.Response, source: str) -> Any:
        if resp.status_code == 404:
            raise DataNotFound(f"{source}: not found (404)")
        if resp.status_code >= 400:
            raise SourceError(f"{source}: HTTP {resp.status_code} {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(f"{source}: invalid JSON ({exc})") from exc

    def close(self) -> None:
        self._client.close()


__all__ = [
    "BaseAdapter",
    "BaseHTTPAdapter",
    "RateExhausted",
    "SourceError",
    "TransientError",
    "DataNotFound",
]
