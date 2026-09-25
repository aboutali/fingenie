"""Tiingo — clean, reliable EOD history for equities/ETFs (backstops yfinance)."""

from __future__ import annotations

from ..errors import DataNotFound
from ..models import AssetClass, CanonicalSymbol, Capability, DataType, OHLCVBar, Quote
from ..utils import iso, now_utc, parse_dt, range_to_start, to_decimal, today
from .base import BaseHTTPAdapter


class TiingoAdapter(BaseHTTPAdapter):
    name = "tiingo"
    needs_key = True
    base_url = "https://api.tiingo.com"

    def __init__(self, *, api_key: str, **kw) -> None:
        super().__init__(**kw)
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._api_key}", "Content-Type": "application/json"}

    def capabilities(self) -> set[Capability]:
        return {
            (AssetClass.EQUITY, DataType.HISTORY),
            (AssetClass.ETF, DataType.HISTORY),
            (AssetClass.EQUITY, DataType.QUOTE),
            (AssetClass.ETF, DataType.QUOTE),
        }

    def _ticker(self, sym: CanonicalSymbol) -> str:
        return sym.symbol.replace(".", "-").lower()

    def get_history(
        self,
        sym: CanonicalSymbol,
        *,
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
    ) -> list[OHLCVBar]:
        ticker = self._ticker(sym)
        start = start or iso(range_to_start("1y"))
        end = end or iso(today())
        rows = self._json_or_raise(
            self._get(
                f"/tiingo/daily/{ticker}/prices",
                params={"startDate": start, "endDate": end},
                headers=self._headers(),
            ),
            self.name,
        )
        if not isinstance(rows, list) or not rows:
            raise DataNotFound(f"tiingo: no history for {ticker}")
        return [
            OHLCVBar(
                symbol=sym.symbol,
                ts=parse_dt(r["date"]),
                open=to_decimal(r.get("open")),
                high=to_decimal(r.get("high")),
                low=to_decimal(r.get("low")),
                close=to_decimal(r.get("close")),
                volume=to_decimal(r.get("volume")),
                source=self.name,
            )
            for r in rows
        ]

    def get_quote(self, sym: CanonicalSymbol) -> Quote:
        ticker = self._ticker(sym)
        rows = self._json_or_raise(
            self._get(f"/iex/{ticker}", headers=self._headers()), self.name
        )
        if not isinstance(rows, list) or not rows:
            raise DataNotFound(f"tiingo: no quote for {ticker}")
        r = rows[0]
        price = to_decimal(r.get("last") or r.get("tngoLast") or r.get("prevClose"))
        if price is None:
            raise DataNotFound(f"tiingo: no price for {ticker}")
        ts = parse_dt(r["timestamp"]) if r.get("timestamp") else now_utc()
        prev = to_decimal(r.get("prevClose"))
        return Quote(
            symbol=sym.symbol,
            asset_class=sym.asset_class,
            price=price,
            currency="USD",
            ts=ts,
            source=self.name,
            prev_close=prev,
            day_open=to_decimal(r.get("open")),
            day_high=to_decimal(r.get("high")),
            day_low=to_decimal(r.get("low")),
            volume=to_decimal(r.get("volume")),
        )
