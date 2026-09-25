"""yfinance (Yahoo Finance) — broadest multi-asset coverage, lowest reliability.

This adapter does NOT use the shared httpx client (yfinance speaks to Yahoo via
its own library). It still flows through the rate governor and converts library
errors into the engine's transient/not-found errors so the router can fall back.
A curl_cffi browser-impersonation session reduces (does not eliminate) Yahoo 429s.
"""

from __future__ import annotations

from ..errors import DataNotFound, SourceError, TransientError
from ..models import AssetClass, CanonicalSymbol, Capability, DataType, FXRate, OHLCVBar, Quote
from ..ratelimit import RateGovernor
from ..utils import iso, now_utc, range_to_start, to_decimal, today
from .base import BaseAdapter

_ALL_ASSETS = [
    AssetClass.EQUITY,
    AssetClass.ETF,
    AssetClass.CRYPTO,
    AssetClass.FX,
    AssetClass.COMMODITY,
    AssetClass.INDEX,
]

_INTERVAL = {"1d": "1d", "1wk": "1wk", "1mo": "1mo", "1h": "1h", "1m": "1m"}


class YFinanceAdapter(BaseAdapter):
    name = "yfinance"
    needs_key = False

    def __init__(self, governor: RateGovernor) -> None:
        self._governor = governor
        self._session = None
        self._yf = None

    def capabilities(self) -> set[Capability]:
        caps: set[Capability] = set()
        for ac in _ALL_ASSETS:
            caps.add((ac, DataType.QUOTE))
            caps.add((ac, DataType.HISTORY))
        caps.add((AssetClass.FX, DataType.FX_RATE))
        return caps

    # -- lazy library/session setup -------------------------------------------
    def _yfin(self):
        if self._yf is None:
            import yfinance as yf

            self._yf = yf
            try:
                from curl_cffi import requests as cffi

                self._session = cffi.Session(impersonate="chrome")
            except Exception:  # noqa: BLE001 - session is best-effort
                self._session = None
        return self._yf

    def _ticker(self, tk: str):
        yf = self._yfin()
        try:
            return yf.Ticker(tk, session=self._session) if self._session else yf.Ticker(tk)
        except TypeError:
            return yf.Ticker(tk)  # older/newer yfinance without session kwarg

    def _resolve(self, sym: CanonicalSymbol) -> str:
        from ..symbols import SymbolResolver

        return SymbolResolver().to_source(sym, self.name)

    # -- capabilities ----------------------------------------------------------
    def get_quote(self, sym: CanonicalSymbol) -> Quote:
        tk = self._resolve(sym)
        self._governor.acquire(self.name)
        info = self._fast_info(tk)
        price = to_decimal(info.get("last_price"))
        if price is None:
            raise DataNotFound(f"yfinance: no quote for {tk}")
        prev = to_decimal(info.get("previous_close"))
        change_pct = None
        if price is not None and prev not in (None, 0):
            change_pct = float((price - prev) / prev * 100)
        return Quote(
            symbol=sym.symbol,
            asset_class=sym.asset_class,
            price=price,
            currency=info.get("currency"),
            ts=now_utc(),
            source=self.name,
            prev_close=prev,
            change=(price - prev) if (price is not None and prev is not None) else None,
            change_pct=change_pct,
            day_open=to_decimal(info.get("open")),
            day_high=to_decimal(info.get("day_high")),
            day_low=to_decimal(info.get("day_low")),
            volume=to_decimal(info.get("last_volume")),
        )

    def get_history(
        self,
        sym: CanonicalSymbol,
        *,
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
    ) -> list[OHLCVBar]:
        tk = self._resolve(sym)
        self._governor.acquire(self.name)
        yf_interval = _INTERVAL.get(interval, "1d")
        start = start or iso(range_to_start("1y"))
        end = end or iso(today())
        ticker = self._ticker(tk)
        try:
            df = ticker.history(start=start, end=end, interval=yf_interval, auto_adjust=False)
        except Exception as exc:  # noqa: BLE001
            raise self._classify(exc) from exc
        if df is None or df.empty:
            raise DataNotFound(f"yfinance: no history for {tk}")
        bars: list[OHLCVBar] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                from datetime import UTC

                ts = ts.replace(tzinfo=UTC)
            bars.append(
                OHLCVBar(
                    symbol=sym.symbol,
                    ts=ts,
                    open=to_decimal(row.get("Open")),
                    high=to_decimal(row.get("High")),
                    low=to_decimal(row.get("Low")),
                    close=to_decimal(row.get("Close")),
                    volume=to_decimal(row.get("Volume")),
                    source=self.name,
                )
            )
        return bars

    def get_fx(self, base: str, quote: str) -> FXRate:
        self._governor.acquire(self.name)
        info = self._fast_info(f"{base}{quote}=X")
        rate = to_decimal(info.get("last_price"))
        if rate is None:
            raise DataNotFound(f"yfinance: no fx for {base}/{quote}")
        return FXRate(base=base, quote=quote, rate=rate, ts=today(), source=self.name)

    # -- helpers ---------------------------------------------------------------
    def _fast_info(self, tk: str) -> dict:
        ticker = self._ticker(tk)
        try:
            fi = ticker.fast_info
            keys = (
                "last_price",
                "previous_close",
                "open",
                "day_high",
                "day_low",
                "last_volume",
                "currency",
            )
            return {k: getattr(fi, k, None) for k in keys}
        except Exception as exc:  # noqa: BLE001
            raise self._classify(exc) from exc

    @staticmethod
    def _classify(exc: Exception) -> SourceError:
        msg = str(exc).lower()
        if "rate" in msg or "too many" in msg or "429" in msg:
            return TransientError(f"yfinance: rate limited ({exc})")
        return SourceError(f"yfinance: {exc}")
