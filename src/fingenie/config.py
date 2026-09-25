"""Configuration: API keys (from env/.env), storage paths, and the default
routing / TTL / rate-budget tables that wire the engine together.

Keys load from environment variables prefixed ``FINGENIE_`` or a local ``.env``
file. Routing priorities, cache TTLs and rate budgets are plain Python defaults
here — easy to read and tweak, no env plumbing needed for a personal tool.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import platformdirs
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import AssetClass, DataType

# --- source names (single source of truth for adapter ids) -------------------
YFINANCE = "yfinance"
COINGECKO = "coingecko"
FRANKFURTER = "frankfurter"
TIINGO = "tiingo"
FINNHUB = "finnhub"
TWELVEDATA = "twelvedata"

# Sources that require an API key, mapped to the Settings attribute holding it.
KEYED_SOURCES: dict[str, str] = {
    TIINGO: "tiingo_key",
    FINNHUB: "finnhub_key",
    TWELVEDATA: "twelvedata_key",
}


class Settings(BaseSettings):
    """User-facing settings, loaded from env / .env."""

    model_config = SettingsConfigDict(
        env_prefix="FINGENIE_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # v1 price-source keys (all free; missing key => source skipped)
    tiingo_key: SecretStr | None = None
    finnhub_key: SecretStr | None = None
    twelvedata_key: SecretStr | None = None

    # behaviour
    cache_enabled: bool = True
    user_agent: str = "fingenie/0.1 (+https://github.com/aboutali/fingenie)"

    # storage (Windows-correct via platformdirs)
    cache_dir: Path = Field(
        default_factory=lambda: Path(platformdirs.user_cache_dir("fingenie", appauthor=False))
    )

    def has_key(self, source: str) -> bool:
        attr = KEYED_SOURCES.get(source)
        if attr is None:
            return True  # no-key source is always "available"
        return getattr(self, attr) is not None

    def key(self, source: str) -> str | None:
        attr = KEYED_SOURCES.get(source)
        if attr is None:
            return None
        secret: SecretStr | None = getattr(self, attr)
        return secret.get_secret_value() if secret else None


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings()


# --- routing table: (asset_class, datatype) -> ordered list of source names ---
# The router tries these in order, skipping rate-exhausted / failing sources.
PRIORITIES: dict[tuple[AssetClass, DataType], list[str]] = {
    # equities / ETFs
    (AssetClass.EQUITY, DataType.QUOTE): [FINNHUB, YFINANCE, TWELVEDATA],
    (AssetClass.EQUITY, DataType.HISTORY): [TIINGO, YFINANCE, TWELVEDATA],
    (AssetClass.ETF, DataType.QUOTE): [FINNHUB, YFINANCE, TWELVEDATA],
    (AssetClass.ETF, DataType.HISTORY): [TIINGO, YFINANCE, TWELVEDATA],
    # crypto
    (AssetClass.CRYPTO, DataType.QUOTE): [COINGECKO, TWELVEDATA, YFINANCE],
    (AssetClass.CRYPTO, DataType.HISTORY): [COINGECKO, TWELVEDATA, YFINANCE],
    # fx
    (AssetClass.FX, DataType.FX_RATE): [FRANKFURTER, TWELVEDATA, YFINANCE],
    (AssetClass.FX, DataType.HISTORY): [FRANKFURTER, YFINANCE, TWELVEDATA],
    # commodities (best-effort)
    (AssetClass.COMMODITY, DataType.QUOTE): [YFINANCE, TWELVEDATA],
    (AssetClass.COMMODITY, DataType.HISTORY): [YFINANCE, TWELVEDATA],
    # indices
    (AssetClass.INDEX, DataType.QUOTE): [YFINANCE, TWELVEDATA],
    (AssetClass.INDEX, DataType.HISTORY): [YFINANCE, TWELVEDATA],
}


# --- per-datatype cache TTL in seconds ---------------------------------------
TTLS: dict[DataType, int] = {
    DataType.QUOTE: 15,
    DataType.FX_RATE: 60 * 30,  # daily reference rates barely move intraday
    DataType.HISTORY: 60 * 60 * 6,  # EOD bars; refresh a few times a day
}
DEFAULT_TTL = 60


# --- per-source rate budgets: name -> list of (limit, window_seconds) ---------
# Conservative so we never trip provider 429s. Persisted across restarts so
# daily caps survive (see ratelimit.RateGovernor).
RATE_BUDGETS: dict[str, list[tuple[int, int]]] = {
    FINNHUB: [(55, 60)],  # provider: 60/min
    TWELVEDATA: [(7, 60), (750, 86_400)],  # provider: 8/min, 800/day
    TIINGO: [(45, 3_600), (900, 86_400)],  # provider: 50/hour, 1000/day
    COINGECKO: [(25, 60)],  # keyless ~30/min, stay polite
    YFINANCE: [(5, 10)],  # unofficial; throttle hard + cache
    # frankfurter: no documented limit -> no budget
}
