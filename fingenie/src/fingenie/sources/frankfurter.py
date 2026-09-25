"""Frankfurter (ECB) — no-key daily FX reference rates. The rock-solid FX backbone."""

from __future__ import annotations

from datetime import UTC, datetime, time

from ..errors import DataNotFound
from ..models import AssetClass, CanonicalSymbol, Capability, DataType, FXRate, OHLCVBar
from ..utils import iso, parse_date, range_to_start, to_decimal, today
from .base import BaseHTTPAdapter


class FrankfurterAdapter(BaseHTTPAdapter):
    name = "frankfurter"
    needs_key = False
    base_url = "https://api.frankfurter.dev/v1"

    def capabilities(self) -> set[Capability]:
        return {(AssetClass.FX, DataType.FX_RATE), (AssetClass.FX, DataType.HISTORY)}

    def get_fx(self, base: str, quote: str) -> FXRate:
        data = self._json_or_raise(
            self._get("/latest", params={"base": base, "symbols": quote}), self.name
        )
        rates = data.get("rates") or {}
        rate = to_decimal(rates.get(quote))
        if rate is None:
            raise DataNotFound(f"frankfurter: no rate for {base}/{quote}")
        return FXRate(
            base=base, quote=quote, rate=rate, ts=parse_date(data["date"]), source=self.name
        )

    def get_history(
        self,
        sym: CanonicalSymbol,
        *,
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
    ) -> list[OHLCVBar]:
        base, quote = sym.base, sym.quote
        start = start or iso(range_to_start("1y"))
        end = end or iso(today())
        data = self._json_or_raise(
            self._get(f"/{start}..{end}", params={"base": base, "symbols": quote}), self.name
        )
        rows = data.get("rates") or {}
        bars: list[OHLCVBar] = []
        for day, by_ccy in sorted(rows.items()):
            rate = to_decimal(by_ccy.get(quote))
            if rate is None:
                continue
            ts = datetime.combine(parse_date(day), time(), tzinfo=UTC)
            bars.append(OHLCVBar(symbol=sym.symbol, ts=ts, close=rate, source=self.name))
        if not bars:
            raise DataNotFound(f"frankfurter: no history for {sym.symbol}")
        return bars
