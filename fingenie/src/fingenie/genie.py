"""The Genie facade — the single clean public API over the whole engine.

Orchestrates: resolve symbol -> check cache -> route (governor-guarded adapters)
-> normalize -> (optionally) merge across sources. Returns canonical models.
"""

from __future__ import annotations

from .cache import TTLCache, make_key
from .config import (
    DEFAULT_TTL,
    RATE_BUDGETS,
    TTLS,
    Settings,
    load_settings,
)
from .errors import NoSourceAvailable
from .merge import merge_fx, merge_quotes
from .models import (
    AssetClass,
    DataType,
    FXRate,
    MergedRecord,
    OHLCVBar,
    Quote,
    SourceStatus,
)
from .ratelimit import RateGovernor
from .router import CapabilityRouter
from .sources import build_registry
from .symbols import SymbolResolver
from .utils import iso, range_to_start


class Genie:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = TTLCache(self.settings.cache_dir / "cache", enabled=self.settings.cache_enabled)
        self.governor = RateGovernor(self.settings.cache_dir / "ratelimit.db", RATE_BUDGETS)
        self.registry = build_registry(self.settings, self.governor)
        self.router = CapabilityRouter(self.registry)
        self.resolver = SymbolResolver()

    # -- quotes ----------------------------------------------------------------
    def quote(
        self,
        symbol: str,
        *,
        asset: AssetClass | None = None,
        merge: bool = False,
        refresh: bool = False,
        no_cache: bool = False,
    ) -> Quote | MergedRecord:
        sym = self.resolver.resolve(symbol, hint=asset)
        if sym.asset_class == AssetClass.FX:
            return self.fx(
                sym.base, sym.quote, merge=merge, refresh=refresh, no_cache=no_cache
            )
        dt = DataType.QUOTE
        if merge:
            results = self.router.route_all(dt, sym.asset_class, lambda a: a.get_quote(sym))
            if not results:
                raise NoSourceAvailable(f"no quote source for {sym}")
            return merge_quotes(results, symbol=sym.symbol, asset_class=sym.asset_class)
        return self._routed(
            dt, sym.asset_class, sym.symbol, lambda a: a.get_quote(sym),
            refresh=refresh, no_cache=no_cache,
        )

    # -- history ---------------------------------------------------------------
    def history(
        self,
        symbol: str,
        *,
        asset: AssetClass | None = None,
        interval: str = "1d",
        start: str | None = None,
        end: str | None = None,
        range: str | None = None,
        refresh: bool = False,
        no_cache: bool = False,
    ) -> list[OHLCVBar]:
        sym = self.resolver.resolve(symbol, hint=asset)
        if range and not start:
            start = iso(range_to_start(range))
        dt = DataType.HISTORY
        params = {"interval": interval, "start": start, "end": end}
        return self._routed(
            dt,
            sym.asset_class,
            sym.symbol,
            lambda a: a.get_history(sym, interval=interval, start=start, end=end),
            params=params,
            refresh=refresh,
            no_cache=no_cache,
        )

    # -- fx --------------------------------------------------------------------
    def fx(
        self,
        base: str,
        quote: str | None = None,
        *,
        merge: bool = False,
        refresh: bool = False,
        no_cache: bool = False,
    ) -> FXRate | MergedRecord:
        if quote is None:
            sym = self.resolver.resolve(base, hint=AssetClass.FX)
            b, q = sym.base, sym.quote
        else:
            b, q = base.upper(), quote.upper()
        dt = DataType.FX_RATE
        symbol = f"{b}/{q}"
        if merge:
            results = self.router.route_all(dt, AssetClass.FX, lambda a: a.get_fx(b, q))
            if not results:
                raise NoSourceAvailable(f"no fx source for {symbol}")
            return merge_fx(results, base=b, quote=q)
        return self._routed(
            dt, AssetClass.FX, symbol, lambda a: a.get_fx(b, q),
            refresh=refresh, no_cache=no_cache,
        )

    # -- introspection ---------------------------------------------------------
    def sources(self) -> list[SourceStatus]:
        out: list[SourceStatus] = []
        for name, adapter in self.registry.items():
            caps = sorted(f"{ac.value}:{dt.value}" for ac, dt in adapter.capabilities())
            out.append(
                SourceStatus(
                    name=name,
                    available=True,
                    needs_key=adapter.needs_key,
                    capabilities=caps,
                    remaining=self.governor.remaining(name),
                )
            )
        # surface keyed sources that are disabled because their key is missing
        from .config import KEYED_SOURCES

        for name in KEYED_SOURCES:
            if name not in self.registry:
                out.append(
                    SourceStatus(
                        name=name,
                        available=False,
                        needs_key=True,
                        note="disabled: API key not set",
                    )
                )
        return out

    # -- internals -------------------------------------------------------------
    def _routed(
        self,
        datatype: DataType,
        asset_class: AssetClass,
        symbol: str,
        call,
        *,
        params: dict | None = None,
        pin_source: str | None = None,
        refresh: bool = False,
        no_cache: bool = False,
    ):
        key = make_key(datatype, symbol, asset_class, params=params, source=pin_source)
        if not refresh and not no_cache:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        result = self.router.route(datatype, asset_class, call, pin_source=pin_source)
        if not no_cache:
            self.cache.set(key, result.value, ttl=TTLS.get(datatype, DEFAULT_TTL))
        return result.value

    def close(self) -> None:
        self.cache.close()
        self.governor.close()
        for adapter in self.registry.values():
            close = getattr(adapter, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> Genie:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
