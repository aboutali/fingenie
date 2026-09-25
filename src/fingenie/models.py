"""Canonical, source-agnostic data models that the whole engine speaks.

Every source adapter normalizes its raw payload into these types, so callers
never see provider-specific quirks. Keep these flat and small — they are the
contract between adapters, the router, the cache and the public facade.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssetClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    FX = "fx"
    COMMODITY = "commodity"
    INDEX = "index"
    ECONOMIC = "economic"  # series-keyed macro data (later phase)
    UNKNOWN = "unknown"


class DataType(StrEnum):
    QUOTE = "quote"
    HISTORY = "history"
    FX_RATE = "fx_rate"
    # Reserved for later phases (append-only — do not reorder, cache keys depend on names):
    ECON_SERIES = "econ_series"
    ECON_OBSERVATION = "econ_observation"
    ECON_SEARCH = "econ_search"
    SYMBOL_MAP = "symbol_map"


# A capability is the pair an adapter advertises it can serve.
Capability = tuple[AssetClass, DataType]


class CanonicalSymbol(BaseModel):
    """A user symbol normalized to a canonical form plus a detected asset class.

    ``symbol`` is the engine's canonical string (e.g. ``AAPL``, ``BTC-USD``,
    ``EUR/USD``). For FX, ``base``/``quote`` carry the currency pair.
    """

    model_config = ConfigDict(frozen=True)

    raw: str
    symbol: str
    asset_class: AssetClass
    base: str | None = None  # FX base currency
    quote: str | None = None  # FX quote currency

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.symbol} [{self.asset_class.value}]"


class Quote(BaseModel):
    """A latest price snapshot for any asset class."""

    symbol: str
    asset_class: AssetClass
    price: Decimal
    currency: str | None = None
    ts: datetime
    source: str
    name: str | None = None
    prev_close: Decimal | None = None
    change: Decimal | None = None
    change_pct: float | None = None
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    volume: Decimal | None = None


class OHLCVBar(BaseModel):
    """A single historical bar. ``open/high/low`` are optional because some
    sources (e.g. daily FX reference rates) only publish a close value."""

    symbol: str
    ts: datetime
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal
    volume: Decimal | None = None
    source: str


class FXRate(BaseModel):
    """A single foreign-exchange rate: 1 unit of ``base`` = ``rate`` units of ``quote``."""

    base: str
    quote: str
    rate: Decimal
    ts: date
    source: str


class FieldValue(BaseModel):
    """One field's value tagged with where it came from and when — the unit of
    provenance used by the multi-source merge layer."""

    value: Any
    source: str
    fetched_at: datetime


class MergedRecord(BaseModel):
    """The result of merging the same logical record across multiple sources.

    ``fields`` holds the winning value per field; ``alternates`` keeps the
    losers; ``disagreement`` flags fields where numeric sources differed beyond
    tolerance. The engine never silently averages — conflicts are surfaced.
    """

    symbol: str
    asset_class: AssetClass
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    alternates: dict[str, list[FieldValue]] = Field(default_factory=dict)
    disagreement: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def value(self, name: str) -> Any:
        fv = self.fields.get(name)
        return fv.value if fv else None

    def values(self) -> dict[str, Any]:
        return {k: v.value for k, v in self.fields.items()}

    def source_of(self, name: str) -> str | None:
        fv = self.fields.get(name)
        return fv.source if fv else None


class Attempt(BaseModel):
    source: str
    ok: bool
    error: str | None = None


class RoutedResult(BaseModel):
    """Internal carrier: the value plus which source won and what was tried."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    value: Any
    source: str | None
    from_cache: bool = False
    attempts: list[Attempt] = Field(default_factory=list)


class SourceStatus(BaseModel):
    """Introspection record for `fingenie sources`."""

    name: str
    available: bool
    needs_key: bool
    capabilities: list[str] = Field(default_factory=list)
    remaining: dict[str, int] = Field(default_factory=dict)
    note: str | None = None
