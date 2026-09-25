from decimal import Decimal

import httpx
import pytest
import respx

from fingenie.errors import TransientError
from fingenie.ratelimit import RateGovernor
from fingenie.sources.coingecko import CoinGeckoAdapter
from fingenie.sources.finnhub_src import FinnhubAdapter
from fingenie.sources.frankfurter import FrankfurterAdapter
from fingenie.sources.tiingo import TiingoAdapter
from fingenie.sources.twelvedata import TwelveDataAdapter
from fingenie.symbols import SymbolResolver

R = SymbolResolver()


@pytest.fixture
def gov(tmp_path):
    return RateGovernor(tmp_path / "rl.db", budgets={})


@respx.mock
def test_frankfurter_fx(gov):
    respx.get("https://api.frankfurter.dev/v1/latest").mock(
        return_value=httpx.Response(
            200, json={"amount": 1.0, "base": "USD", "date": "2026-06-10", "rates": {"EUR": 0.864}}
        )
    )
    fx = FrankfurterAdapter(governor=gov).get_fx("USD", "EUR")
    assert fx.rate == Decimal("0.864")
    assert fx.base == "USD" and fx.quote == "EUR"
    assert fx.ts.isoformat() == "2026-06-10"
    assert fx.source == "frankfurter"


@respx.mock
def test_coingecko_quote(gov):
    respx.get("https://api.coingecko.com/api/v3/simple/price").mock(
        return_value=httpx.Response(
            200,
            json={"bitcoin": {"usd": 65000.0, "usd_24h_change": 1.5, "last_updated_at": 1700000000}},
        )
    )
    q = CoinGeckoAdapter(governor=gov).get_quote(R.resolve("BTC-USD"))
    assert q.price == Decimal("65000.0")
    assert q.currency == "USD"
    assert q.source == "coingecko"


@respx.mock
def test_coingecko_history(gov):
    respx.get("https://api.coingecko.com/api/v3/coins/bitcoin/ohlc").mock(
        return_value=httpx.Response(
            200, json=[[1700000000000, 64000, 65500, 63500, 65000]]
        )
    )
    bars = CoinGeckoAdapter(governor=gov).get_history(R.resolve("BTC-USD"))
    assert len(bars) == 1
    assert bars[0].close == Decimal("65000")
    assert bars[0].high == Decimal("65500")


@respx.mock
def test_finnhub_quote(gov):
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(
            200,
            json={"c": 231.4, "d": 1.2, "dp": 0.52, "h": 232, "l": 230, "o": 231,
                  "pc": 230.2, "t": 1700000000},
        )
    )
    q = FinnhubAdapter(api_key="x", governor=gov).get_quote(R.resolve("AAPL"))
    assert q.price == Decimal("231.4")
    assert q.prev_close == Decimal("230.2")
    assert q.source == "finnhub"


@respx.mock
def test_finnhub_unknown_symbol_raises(gov):
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 0, "d": None, "dp": None, "pc": 0})
    )
    from fingenie.errors import DataNotFound

    with pytest.raises(DataNotFound):
        FinnhubAdapter(api_key="x", governor=gov).get_quote(R.resolve("NOPE"))


@respx.mock
def test_twelvedata_quote(gov):
    respx.get("https://api.twelvedata.com/quote").mock(
        return_value=httpx.Response(
            200,
            json={"symbol": "AAPL", "name": "Apple", "close": "231.40",
                  "previous_close": "230.00", "change": "1.40", "percent_change": "0.61",
                  "open": "231.00", "high": "232.00", "low": "230.00", "volume": "1000",
                  "timestamp": 1700000000, "currency": "USD"},
        )
    )
    q = TwelveDataAdapter(api_key="x", governor=gov).get_quote(R.resolve("AAPL"))
    assert q.price == Decimal("231.40")
    assert q.name == "Apple"
    assert q.change_pct == pytest.approx(0.61)


@respx.mock
def test_twelvedata_rate_limit_is_transient(gov):
    respx.get("https://api.twelvedata.com/quote").mock(
        return_value=httpx.Response(
            200, json={"status": "error", "code": 429, "message": "out of credits"}
        )
    )
    with pytest.raises(TransientError):
        TwelveDataAdapter(api_key="x", governor=gov).get_quote(R.resolve("AAPL"))


@respx.mock
def test_tiingo_history(gov):
    respx.get("https://api.tiingo.com/tiingo/daily/aapl/prices").mock(
        return_value=httpx.Response(
            200,
            json=[{"date": "2026-06-09T00:00:00.000Z", "open": 231, "high": 232,
                   "low": 230, "close": 231.5, "volume": 1000}],
        )
    )
    bars = TiingoAdapter(api_key="x", governor=gov).get_history(R.resolve("AAPL"))
    assert len(bars) == 1
    assert bars[0].close == Decimal("231.5")
    assert bars[0].source == "tiingo"
