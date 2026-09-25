from datetime import UTC, datetime
from decimal import Decimal

from fingenie.merge import merge_quotes
from fingenie.models import AssetClass, Quote


def _q(source, price, **kw):
    return Quote(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        price=Decimal(str(price)),
        ts=datetime(2026, 6, 10, tzinfo=UTC),
        source=source,
        **kw,
    )


def test_winner_is_highest_priority():
    merged = merge_quotes(
        [("finnhub", _q("finnhub", 231.4)), ("yfinance", _q("yfinance", 231.5))],
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
    )
    assert merged.value("price") == Decimal("231.4")
    assert merged.source_of("price") == "finnhub"


def test_fills_missing_field_from_next_source():
    a = _q("finnhub", 231.4)  # no volume
    b = _q("yfinance", 231.5, volume=Decimal("1000"))
    merged = merge_quotes(
        [("finnhub", a), ("yfinance", b)], symbol="AAPL", asset_class=AssetClass.EQUITY
    )
    assert merged.value("volume") == Decimal("1000")
    assert merged.source_of("volume") == "yfinance"


def test_disagreement_flagged_when_spread_exceeds_tolerance():
    merged = merge_quotes(
        [("finnhub", _q("finnhub", 100.0)), ("yfinance", _q("yfinance", 105.0))],
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        tolerance=0.005,
    )
    assert merged.disagreement["price"] is True
    assert merged.warnings


def test_agreement_within_tolerance():
    merged = merge_quotes(
        [("finnhub", _q("finnhub", 100.0)), ("yfinance", _q("yfinance", 100.1))],
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        tolerance=0.005,
    )
    assert merged.disagreement["price"] is False
    assert not merged.warnings
