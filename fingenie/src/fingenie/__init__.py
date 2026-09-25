"""FinGenie — a lightweight engine that bundles many free financial-data sources
behind one clean, normalized interface."""

from __future__ import annotations

from .genie import Genie
from .models import (
    AssetClass,
    DataType,
    FXRate,
    MergedRecord,
    OHLCVBar,
    Quote,
)

__version__ = "0.1.0"

__all__ = [
    "Genie",
    "AssetClass",
    "DataType",
    "Quote",
    "OHLCVBar",
    "FXRate",
    "MergedRecord",
    "__version__",
]
