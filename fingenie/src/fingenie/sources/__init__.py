"""Adapter registry assembly.

``build_registry`` instantiates every adapter whose credentials are present.
No-key sources are always included; keyed sources are skipped when their key is
missing, so the engine degrades gracefully and runs with zero configuration.
"""

from __future__ import annotations

from ..config import (
    COINGECKO,
    FINNHUB,
    FRANKFURTER,
    TIINGO,
    TWELVEDATA,
    YFINANCE,
    Settings,
)
from ..ratelimit import RateGovernor
from .base import BaseAdapter
from .coingecko import CoinGeckoAdapter
from .finnhub_src import FinnhubAdapter
from .frankfurter import FrankfurterAdapter
from .tiingo import TiingoAdapter
from .twelvedata import TwelveDataAdapter
from .yfinance_src import YFinanceAdapter


def build_registry(settings: Settings, governor: RateGovernor) -> dict[str, BaseAdapter]:
    ua = settings.user_agent
    registry: dict[str, BaseAdapter] = {
        FRANKFURTER: FrankfurterAdapter(governor=governor, user_agent=ua),
        COINGECKO: CoinGeckoAdapter(governor=governor, user_agent=ua),
        YFINANCE: YFinanceAdapter(governor),
    }
    if settings.has_key(TIINGO):
        registry[TIINGO] = TiingoAdapter(
            api_key=settings.key(TIINGO), governor=governor, user_agent=ua
        )
    if settings.has_key(FINNHUB):
        registry[FINNHUB] = FinnhubAdapter(
            api_key=settings.key(FINNHUB), governor=governor, user_agent=ua
        )
    if settings.has_key(TWELVEDATA):
        registry[TWELVEDATA] = TwelveDataAdapter(
            api_key=settings.key(TWELVEDATA), governor=governor, user_agent=ua
        )
    return registry


__all__ = ["build_registry", "BaseAdapter"]
