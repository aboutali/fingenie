"""Twelve Data — unified multi-asset quotes/history/FX under one clean schema."""

from __future__ import annotations

from typing import Any

from ..errors import DataNotFound, SourceError, TransientError
from ..models import AssetClass, CanonicalSymbol, Capability, DataType, FXRate, OHLCVBar, Quote
from ..utils import now_utc, parse_dt, secs_to_dt, to_decimal, today
from .base import BaseHTTPAdapter

_INTERVAL = {"1d": "1day", "1wk": "1week", "1mo": "1month", "1h": "1h", "1m": "1min"}
_MARKET_ASSETS = [
    AssetClass.EQUITY,
    AssetClass.ETF,
    AssetClass.CRYPTO,
    AssetClass.FX,
    AssetClass.COMMODITY,
    AssetClass.INDEX,
]


class TwelveDataAdapter(BaseHTTPAdapter):
    name = "twelvedata"
    needs_key = True
    base_url = "https://api.twelvedata.com"

    def __init__(self, *, api_key: str, **kw) -> None:
        super().__init__(**kw)
        self._api_key = api_key

    def capabilities(self) -> set[Capability]:
        caps: set[Capability] = set()
        for ac in _MARKET_ASSETS:
            caps.add((ac, DataType.QUOTE))
            caps.add((ac, DataType.HISTORY))
        caps.add((AssetClass.FX, DataType.FX_RATE))
        return caps

    def _resolve(self, sym: CanonicalSymbol) -> str:
        from ..symbols import SymbolResolver

        return SymbolResolver().to_source(sym, self.name)

    def _td(self, payload: dict[str, Any], params: dict[str, Any]) -> Any:
        params = {**params, "apikey": self._api_key}
        data = self._json_or_raise(self._get(payload["path"], params=params), self.name)
        if isinstance(data, dict) and data.get("status") == "error":
            code = data.get("code")
            msg = data.get("message", "error")
            if code == 429:
                raise TransientError(f"twelvedata: rate limited ({msg})")
            raise DataNotFound(f"twelvedata: {msg}")
        return data

    def get_quote(self, sym: CanonicalSymbol) -> Quote:
        symbol = self._resolve(sym)
        data = self._td({"path": "/quote"}, {"symbol": symbol})
        price = to_decimal(data.get("close"))
        if price is None:
            raise DataNotFound(f"twelvedata: no quote for {symbol}")
        ts = secs_to_dt(int(data["timestamp"])) if data.get("timestamp") else now_utc()
        return Quote(
            symbol=sym.symbol,
            asset_class=sym.asset_class,
            price=price,
            currency=data.get("currency"),
            ts=ts,
            source=self.name,
            name=data.get("name"),
            prev_close=to_decimal(data.get("previous_close")),
            change=to_decimal(data.get("change")),
            change_pct=float(data["percent_change"])
            if data.get("percent_change") not in (None, "")
            else None,
            day_open=to_decimal(data.get("open")),
            day_high=to_decimal(data.get("high")),
            day_low=to_decimal(data.get("low")),
            volume=to_decimal(data.get("volume")),
        )

    def get_history(
        self,
        sym: CanonicalSymbol,
        *,
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
    ) -> list[OHLCVBar]:
        symbol = self._resolve(sym)
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": _INTERVAL.get(interval, "1day"),
            "outputsize": 5000,
            "order": "ASC",
        }
        if start:
            params["start_date"] = start
        if end:
            params["end_date"] = end
        data = self._td({"path": "/time_series"}, params)
        values = data.get("values") if isinstance(data, dict) else None
        if not values:
            raise DataNotFound(f"twelvedata: no history for {symbol}")
        return [
            OHLCVBar(
                symbol=sym.symbol,
                ts=parse_dt(v["datetime"]),
                open=to_decimal(v.get("open")),
                high=to_decimal(v.get("high")),
                low=to_decimal(v.get("low")),
                close=to_decimal(v.get("close")),
                volume=to_decimal(v.get("volume")),
                source=self.name,
            )
            for v in values
        ]

    def get_fx(self, base: str, quote: str) -> FXRate:
        data = self._td({"path": "/exchange_rate"}, {"symbol": f"{base}/{quote}"})
        rate = to_decimal(data.get("rate"))
        if rate is None:
            raise DataNotFound(f"twelvedata: no fx for {base}/{quote}")
        return FXRate(base=base, quote=quote, rate=rate, ts=today(), source=self.name)

    # Twelve Data may legitimately return a non-error dict; guard generic failures.
    @staticmethod
    def _guard(data: Any) -> Any:  # pragma: no cover - defensive
        if data is None:
            raise SourceError("twelvedata: empty response")
        return data
