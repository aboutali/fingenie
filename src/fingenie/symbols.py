"""Symbol resolution: normalize user input to a CanonicalSymbol (with a detected
asset class) and translate that canonical symbol to each source's convention.

This is the main integration cost of a multi-source engine — Yahoo, Tiingo,
CoinGecko (coin-ids), Frankfurter (currency pairs) and Twelve Data all spell the
same instrument differently. Detection is heuristic but predictable for the
common cases, and every facade method accepts an explicit ``asset`` hint to
override it.
"""

from __future__ import annotations

import re

from .config import COINGECKO, FINNHUB, FRANKFURTER, TIINGO, TWELVEDATA, YFINANCE
from .models import AssetClass, CanonicalSymbol

# Common ISO-4217 fiat currencies (enough to recognise FX pairs).
FIAT = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "CNY", "HKD",
    "SGD", "SEK", "NOK", "DKK", "MXN", "ZAR", "INR", "BRL", "RUB", "KRW",
    "TRY", "PLN", "THB", "IDR", "HUF", "CZK", "ILS", "CLP", "PHP", "AED",
}

# Common crypto tickers -> CoinGecko coin id. Majors only; unknown bases fall
# back to a lowercased ticker (often wrong for long-tail coins — documented).
CRYPTO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "USDT": "tether", "BNB": "binancecoin",
    "SOL": "solana", "XRP": "ripple", "USDC": "usd-coin", "ADA": "cardano",
    "DOGE": "dogecoin", "TRX": "tron", "TON": "the-open-network", "DOT": "polkadot",
    "MATIC": "matic-network", "LTC": "litecoin", "SHIB": "shiba-inu",
    "AVAX": "avalanche-2", "LINK": "chainlink", "BCH": "bitcoin-cash",
    "XLM": "stellar", "UNI": "uniswap", "ATOM": "cosmos", "ETC": "ethereum-classic",
    "XMR": "monero", "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
    "NEAR": "near", "FIL": "filecoin", "ICP": "internet-computer", "HBAR": "hedera",
}
CRYPTO = set(CRYPTO_IDS)
CRYPTO_QUOTES = {"USD", "USDT", "USDC", "EUR", "BTC", "ETH", "GBP"}

_SEP = re.compile(r"[-/_:]")


class SymbolResolver:
    def detect_asset_class(self, raw: str) -> AssetClass:
        s = raw.strip().upper()
        if "=F" in s:
            return AssetClass.COMMODITY
        if s.startswith("^"):
            return AssetClass.INDEX
        base, quote = self._split_pair(s)
        if base in FIAT and quote in FIAT:
            return AssetClass.FX
        if base in CRYPTO:
            return AssetClass.CRYPTO
        return AssetClass.EQUITY

    def resolve(self, raw: str, hint: AssetClass | None = None) -> CanonicalSymbol:
        s = raw.strip()
        ac = hint or self.detect_asset_class(s)
        up = s.upper()

        if ac == AssetClass.FX:
            base, quote = self._split_pair(up)
            quote = quote or "USD"
            return CanonicalSymbol(
                raw=raw, symbol=f"{base}/{quote}", asset_class=ac, base=base, quote=quote
            )
        if ac == AssetClass.CRYPTO:
            base, quote = self._split_pair(up)
            quote = quote or "USD"
            return CanonicalSymbol(
                raw=raw, symbol=f"{base}-{quote}", asset_class=ac, base=base, quote=quote
            )
        # equity / etf / commodity / index / unknown -> keep upper symbol as-is
        return CanonicalSymbol(raw=raw, symbol=up, asset_class=ac)

    # -- per-source translation ------------------------------------------------
    def to_source(self, sym: CanonicalSymbol, source: str) -> str:
        ac = sym.asset_class
        if source == YFINANCE:
            if ac == AssetClass.CRYPTO:
                return f"{sym.base}-{sym.quote}"
            if ac == AssetClass.FX:
                return f"{sym.base}{sym.quote}=X"
            return sym.symbol.replace(".", "-")  # BRK.B -> BRK-B
        if source == TIINGO:
            if ac == AssetClass.CRYPTO:
                return f"{sym.base}{sym.quote}".lower()
            if ac == AssetClass.FX:
                return f"{sym.base}{sym.quote}".lower()
            return sym.symbol.replace(".", "-").lower()
        if source == COINGECKO:
            # returns the coin id; the adapter pairs it with sym.quote as vs_currency
            return CRYPTO_IDS.get(sym.base or "", (sym.base or "").lower())
        if source == TWELVEDATA:
            if ac == AssetClass.CRYPTO:
                return f"{sym.base}/{sym.quote}"
            if ac == AssetClass.FX:
                return f"{sym.base}/{sym.quote}"
            return sym.symbol
        if source == FINNHUB:
            return sym.symbol.replace(".", "-")  # used for equities/ETFs only
        if source == FRANKFURTER:
            return sym.base or sym.symbol
        return sym.symbol

    # -- helpers ---------------------------------------------------------------
    def _split_pair(self, up: str) -> tuple[str, str]:
        """Return (base, quote) for a pair-like string, or (token, "")."""
        if _SEP.search(up):
            parts = _SEP.split(up)
            if len(parts) >= 2:
                return parts[0], parts[1]
            return parts[0], ""
        # contiguous 6-char pair e.g. EURUSD / BTCUSD
        if len(up) == 6:
            base, quote = up[:3], up[3:]
            if (base in FIAT and quote in FIAT) or (base in CRYPTO and quote in CRYPTO_QUOTES):
                return base, quote
        # crypto base with attached quote e.g. BTCUSDT
        for q in sorted(CRYPTO_QUOTES, key=len, reverse=True):
            if up.endswith(q) and up[: -len(q)] in CRYPTO:
                return up[: -len(q)], q
        return up, ""
