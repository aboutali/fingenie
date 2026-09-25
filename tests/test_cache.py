import time

from fingenie.cache import TTLCache, make_key, params_hash
from fingenie.models import AssetClass, DataType


def test_set_get_roundtrip(tmp_path):
    c = TTLCache(tmp_path / "cache")
    c.set("k", {"a": 1}, ttl=60)
    assert c.get("k") == {"a": 1}


def test_ttl_expiry(tmp_path):
    c = TTLCache(tmp_path / "cache")
    c.set("k", 1, ttl=1)
    assert c.get("k") == 1
    time.sleep(1.2)
    assert c.get("k") is None


def test_disabled_cache_is_noop(tmp_path):
    c = TTLCache(tmp_path / "cache", enabled=False)
    c.set("k", 1, ttl=60)
    assert c.get("k") is None


def test_make_key_is_stable_and_distinct():
    k1 = make_key(DataType.QUOTE, "aapl", AssetClass.EQUITY)
    k2 = make_key(DataType.QUOTE, "AAPL", AssetClass.EQUITY)
    assert k1 == k2  # case-insensitive symbol
    k3 = make_key(DataType.HISTORY, "AAPL", AssetClass.EQUITY, params={"interval": "1d"})
    assert k3 != k1
    assert params_hash(None) == "_"
