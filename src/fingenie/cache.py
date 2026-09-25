"""Local, persistent, cache-aside layer with per-datatype TTL.

Backed by diskcache (SQLite) so it survives across runs — a cache hit costs
zero rate budget, which is the single biggest lever against free-tier limits.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import diskcache

from .models import AssetClass, DataType


def params_hash(params: dict[str, Any] | None) -> str:
    """Stable short hash of request params for cache-key disambiguation."""
    if not params:
        return "_"
    blob = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def make_key(
    datatype: DataType,
    symbol: str,
    asset_class: AssetClass,
    params: dict[str, Any] | None = None,
    source: str | None = None,
) -> str:
    return "|".join(
        [
            datatype.value,
            asset_class.value,
            symbol.upper(),
            params_hash(params),
            source or "_merged_",
        ]
    )


class TTLCache:
    """Thin wrapper over diskcache with explicit per-call TTL and a kill switch."""

    def __init__(self, directory: str | Path, enabled: bool = True) -> None:
        Path(directory).mkdir(parents=True, exist_ok=True)
        self._cache = diskcache.Cache(str(directory))
        self.enabled = enabled

    def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        return self._cache.get(key, default=None)

    def set(self, key: str, value: Any, ttl: int) -> None:
        if not self.enabled:
            return
        self._cache.set(key, value, expire=ttl)

    def clear(self) -> int:
        return self._cache.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "directory": self._cache.directory,
            "count": len(self._cache),
            "size_bytes": self._cache.volume(),
        }

    def close(self) -> None:
        self._cache.close()
