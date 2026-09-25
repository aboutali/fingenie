"""Finnhub — real-time US equity/ETF quotes (best free quote source)."""

from __future__ import annotations

from ..errors import DataNotFound
from ..models import AssetClass, CanonicalSymbol, Capability, DataType, Quote
from ..utils import now_utc, secs_to_dt, to_decimal
from .base import BaseHTTPAdapter


class FinnhubAdapter(BaseHTTPAdapter):
    name = "finnhub"
    needs_key = True
    base_url = "https://finnhub.io/api/v1"

    def __init__(self, *, api_key: str, **kw) -> None:
        super().__init__(**kw)
        self._api_key = api_key

    def capabilities(self) -> set[Capability]:
        return {(AssetClass.EQUITY, DataType.QUOTE), (AssetClass.ETF, DataType.QUOTE)}

    def get_quote(self, sym: CanonicalSymbol) -> Quote:
        symbol = sym.symbol.replace(".", "-")
        data = self._json_or_raise(
            self._get("/quote", params={"symbol": symbol, "token": self._api_key}), self.name
        )
        price = to_decimal(data.get("c"))
        prev = to_decimal(data.get("pc"))
        # Finnhub returns all-zeros for unknown symbols rather than an error.
        if not price or (price == 0 and (prev or 0) == 0):
            raise DataNotFound(f"finnhub: no quote for {symbol}")
        ts = secs_to_dt(data["t"]) if data.get("t") else now_utc()
        return Quote(
            symbol=sym.symbol,
            asset_class=sym.asset_class,
            price=price,
            currency="USD",
            ts=ts,
            source=self.name,
            prev_close=prev,
            change=to_decimal(data.get("d")),
            change_pct=float(data["dp"]) if data.get("dp") is not None else None,
            day_open=to_decimal(data.get("o")),
            day_high=to_decimal(data.get("h")),
            day_low=to_decimal(data.get("l")),
        )
