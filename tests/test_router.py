from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fingenie.errors import NoSourceAvailable, SourceError
from fingenie.models import AssetClass, CanonicalSymbol, Capability, DataType, Quote
from fingenie.ratelimit import RateExhausted
from fingenie.router import CapabilityRouter
from fingenie.sources.base import BaseAdapter

SYM = CanonicalSymbol(raw="AAPL", symbol="AAPL", asset_class=AssetClass.EQUITY)


class FakeAdapter(BaseAdapter):
    def __init__(self, name, behaviour="ok", price=100):
        self.name = name
        self.needs_key = False
        self._behaviour = behaviour
        self._price = price

    def capabilities(self) -> set[Capability]:
        return {(AssetClass.EQUITY, DataType.QUOTE)}

    def get_quote(self, sym):
        if self._behaviour == "error":
            raise SourceError(f"{self.name} boom")
        if self._behaviour == "exhausted":
            raise RateExhausted(self.name, 1, 60)
        return Quote(
            symbol=sym.symbol,
            asset_class=sym.asset_class,
            price=Decimal(str(self._price)),
            ts=datetime(2026, 6, 10, tzinfo=UTC),
            source=self.name,
        )


def test_returns_first_success():
    router = CapabilityRouter({"a": FakeAdapter("a", price=1), "b": FakeAdapter("b", price=2)})
    res = router.route(DataType.QUOTE, AssetClass.EQUITY, lambda ad: ad.get_quote(SYM))
    assert res.source == "a"
    assert res.value.price == Decimal("1")


def test_falls_back_on_error():
    router = CapabilityRouter(
        {"a": FakeAdapter("a", behaviour="error"), "b": FakeAdapter("b", price=2)}
    )
    res = router.route(DataType.QUOTE, AssetClass.EQUITY, lambda ad: ad.get_quote(SYM))
    assert res.source == "b"
    assert any(not at.ok for at in res.attempts)


def test_falls_back_on_rate_exhausted():
    router = CapabilityRouter(
        {"a": FakeAdapter("a", behaviour="exhausted"), "b": FakeAdapter("b", price=5)}
    )
    res = router.route(DataType.QUOTE, AssetClass.EQUITY, lambda ad: ad.get_quote(SYM))
    assert res.source == "b"


def test_all_fail_raises():
    router = CapabilityRouter(
        {"a": FakeAdapter("a", behaviour="error"), "b": FakeAdapter("b", behaviour="error")}
    )
    with pytest.raises(NoSourceAvailable):
        router.route(DataType.QUOTE, AssetClass.EQUITY, lambda ad: ad.get_quote(SYM))


def test_pin_source_disables_fallback():
    router = CapabilityRouter(
        {"a": FakeAdapter("a", behaviour="error"), "b": FakeAdapter("b", price=2)}
    )
    with pytest.raises(NoSourceAvailable):
        router.route(
            DataType.QUOTE, AssetClass.EQUITY, lambda ad: ad.get_quote(SYM), pin_source="a"
        )


def test_pin_source_unknown_capability_raises():
    router = CapabilityRouter({"a": FakeAdapter("a")})
    with pytest.raises(NoSourceAvailable):
        router.route(
            DataType.FX_RATE, AssetClass.FX, lambda ad: ad.get_quote(SYM), pin_source="a"
        )


def test_route_all_gathers_successes_only():
    router = CapabilityRouter(
        {"a": FakeAdapter("a", price=1), "b": FakeAdapter("b", behaviour="error"),
         "c": FakeAdapter("c", price=3)}
    )
    got = router.route_all(DataType.QUOTE, AssetClass.EQUITY, lambda ad: ad.get_quote(SYM))
    assert [name for name, _ in got] == ["a", "c"]
