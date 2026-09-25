"""Capability router: pick the best source for a request, fall back on failure.

For a given (datatype, asset_class) it builds an ordered candidate list from the
priority table, then tries each in order — skipping sources that are
rate-exhausted or error out — and returns the first success. A ``pin_source``
argument forces a single source and disables fallback (mandatory for economic
series in a later phase; also useful to force a market source).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .config import PRIORITIES
from .errors import NoSourceAvailable, SourceError
from .models import AssetClass, Attempt, Capability, DataType, RoutedResult
from .ratelimit import RateExhausted
from .sources.base import BaseAdapter


class CapabilityRouter:
    def __init__(self, registry: dict[str, BaseAdapter]) -> None:
        self.registry = registry

    def candidates(
        self,
        datatype: DataType,
        asset_class: AssetClass,
        pin_source: str | None = None,
    ) -> list[BaseAdapter]:
        cap: Capability = (asset_class, datatype)
        if pin_source is not None:
            adapter = self.registry.get(pin_source)
            if adapter is None or cap not in adapter.capabilities():
                return []
            return [adapter]
        ordered = PRIORITIES.get(cap, [])
        out: list[BaseAdapter] = []
        # priority-listed sources first, then any other capable source as a backstop
        for name in ordered:
            adapter = self.registry.get(name)
            if adapter is not None and cap in adapter.capabilities():
                out.append(adapter)
        for name, adapter in self.registry.items():
            if name not in ordered and cap in adapter.capabilities():
                out.append(adapter)
        return out

    def route(
        self,
        datatype: DataType,
        asset_class: AssetClass,
        call: Callable[[BaseAdapter], Any],
        *,
        pin_source: str | None = None,
    ) -> RoutedResult:
        cands = self.candidates(datatype, asset_class, pin_source)
        if not cands:
            raise NoSourceAvailable(
                f"no source for ({asset_class.value}, {datatype.value})"
                + (f" pinned to {pin_source!r}" if pin_source else "")
            )
        attempts: list[Attempt] = []
        for adapter in cands:
            try:
                value = call(adapter)
            except RateExhausted as exc:
                attempts.append(Attempt(source=adapter.name, ok=False, error=str(exc)))
                continue
            except (SourceError, NotImplementedError) as exc:
                attempts.append(Attempt(source=adapter.name, ok=False, error=str(exc)))
                continue
            attempts.append(Attempt(source=adapter.name, ok=True))
            return RoutedResult(value=value, source=adapter.name, attempts=attempts)
        raise NoSourceAvailable(
            f"all sources failed for ({asset_class.value}, {datatype.value})", attempts
        )

    def route_all(
        self,
        datatype: DataType,
        asset_class: AssetClass,
        call: Callable[[BaseAdapter], Any],
    ) -> list[tuple[str, Any]]:
        """Gather results from every capable source (for multi-source merge)."""
        results: list[tuple[str, Any]] = []
        for adapter in self.candidates(datatype, asset_class):
            try:
                results.append((adapter.name, call(adapter)))
            except (SourceError, RateExhausted, NotImplementedError):
                continue
        return results
