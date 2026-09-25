"""CoinGecko (keyless public API) — the crypto backbone (prices + OHLC history)."""

from __future__ import annotations

from ..errors import DataNotFound
from ..models import AssetClass, CanonicalSymbol, Capability, DataType, OHLCVBar, Quote
from ..utils import ms_to_dt, now_utc, parse_date, secs_to_dt, to_decimal, today
from .base import BaseHTTPAdapter

# CoinGecko's /coins/{id}/ohlc only accepts these day windows on the free tier.
_OHLC_DAYS = [1, 7, 14, 30, 90, 180, 365]


class CoinGeckoAdapter(BaseHTTPAdapter):
    name = "coingecko"
    needs_key = False
    base_url = "https://api.coingecko.com/api/v3"

    def capabilities(self) -> set[Capability]:
        return {(AssetClass.CRYPTO, DataType.QUOTE), (AssetClass.CRYPTO, DataType.HISTORY)}

    def get_quote(self, sym: CanonicalSymbol) -> Quote:
        from ..symbols import CRYPTO_IDS

        coin_id = CRYPTO_IDS.get(sym.base or "", (sym.base or "").lower())
        vs = (sym.quote or "USD").lower()
        data = self._json_or_raise(
            self._get(
                "/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": vs,
                    "include_24hr_change": "true",
                    "include_last_updated_at": "true",
                },
            ),
            self.name,
        )
        row = data.get(coin_id)
        if not row or vs not in row:
            raise DataNotFound(f"coingecko: no price for {coin_id}/{vs}")
        ts = secs_to_dt(row["last_updated_at"]) if row.get("last_updated_at") else now_utc()
        return Quote(
            symbol=sym.symbol,
            asset_class=sym.asset_class,
            price=to_decimal(row[vs]),
            currency=(sym.quote or "USD").upper(),
            ts=ts,
            source=self.name,
            change_pct=row.get(f"{vs}_24h_change"),
        )

    def get_history(
        self,
        sym: CanonicalSymbol,
        *,
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
    ) -> list[OHLCVBar]:
        from ..symbols import CRYPTO_IDS

        coin_id = CRYPTO_IDS.get(sym.base or "", (sym.base or "").lower())
        vs = (sym.quote or "USD").lower()
        days = self._days(start)
        data = self._json_or_raise(
            self._get(f"/coins/{coin_id}/ohlc", params={"vs_currency": vs, "days": days}),
            self.name,
        )
        if not isinstance(data, list) or not data:
            raise DataNotFound(f"coingecko: no history for {coin_id}/{vs}")
        bars = [
            OHLCVBar(
                symbol=sym.symbol,
                ts=ms_to_dt(row[0]),
                open=to_decimal(row[1]),
                high=to_decimal(row[2]),
                low=to_decimal(row[3]),
                close=to_decimal(row[4]),
                source=self.name,
            )
            for row in data
        ]
        return bars

    @staticmethod
    def _days(start: str | None) -> int | str:
        if not start:
            return 365
        wanted = (today() - parse_date(start)).days
        for d in _OHLC_DAYS:
            if d >= wanted:
                return d
        return 365  # free tier caps history at ~1 year
