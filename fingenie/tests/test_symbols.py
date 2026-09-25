from fingenie.config import COINGECKO, FRANKFURTER, TIINGO, TWELVEDATA, YFINANCE
from fingenie.models import AssetClass
from fingenie.symbols import SymbolResolver

r = SymbolResolver()


def test_detect_equity():
    assert r.detect_asset_class("AAPL") == AssetClass.EQUITY
    assert r.detect_asset_class("BRK.B") == AssetClass.EQUITY


def test_detect_crypto():
    assert r.detect_asset_class("BTC-USD") == AssetClass.CRYPTO
    assert r.detect_asset_class("ETH/USDT") == AssetClass.CRYPTO
    assert r.detect_asset_class("BTCUSD") == AssetClass.CRYPTO
    assert r.detect_asset_class("SOL") == AssetClass.CRYPTO


def test_detect_fx():
    assert r.detect_asset_class("EUR/USD") == AssetClass.FX
    assert r.detect_asset_class("EURUSD") == AssetClass.FX
    assert r.detect_asset_class("GBP-JPY") == AssetClass.FX


def test_detect_commodity_index():
    assert r.detect_asset_class("GC=F") == AssetClass.COMMODITY
    assert r.detect_asset_class("^GSPC") == AssetClass.INDEX


def test_resolve_crypto_pair():
    sym = r.resolve("btc-usd")
    assert sym.asset_class == AssetClass.CRYPTO
    assert sym.base == "BTC" and sym.quote == "USD"
    assert sym.symbol == "BTC-USD"


def test_resolve_fx_defaults_quote_usd():
    sym = r.resolve("EUR", hint=AssetClass.FX)
    assert sym.base == "EUR" and sym.quote == "USD"
    assert sym.symbol == "EUR/USD"


def test_to_source_yfinance():
    assert r.to_source(r.resolve("BRK.B"), YFINANCE) == "BRK-B"
    assert r.to_source(r.resolve("BTC-USD"), YFINANCE) == "BTC-USD"
    assert r.to_source(r.resolve("EUR/USD"), YFINANCE) == "EURUSD=X"


def test_to_source_coingecko_id():
    assert r.to_source(r.resolve("BTC-USD"), COINGECKO) == "bitcoin"
    assert r.to_source(r.resolve("ETH-USD"), COINGECKO) == "ethereum"


def test_to_source_twelvedata_and_tiingo():
    assert r.to_source(r.resolve("BTC-USD"), TWELVEDATA) == "BTC/USD"
    assert r.to_source(r.resolve("EUR/USD"), TWELVEDATA) == "EUR/USD"
    assert r.to_source(r.resolve("BRK.B"), TIINGO) == "brk-b"


def test_to_source_frankfurter_base():
    assert r.to_source(r.resolve("EUR/USD"), FRANKFURTER) == "EUR"
