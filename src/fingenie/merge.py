"""Light multi-source field merge with disagreement flagging.

Given the same logical record fetched from several sources (in priority order),
pick each field's value from the highest-priority source that has it, fill
missing fields from the next source, and flag fields where numeric sources
disagree beyond a tolerance. We never silently average — conflicts are surfaced
so they can't quietly corrupt downstream metrics.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from .models import AssetClass, FieldValue, FXRate, MergedRecord, Quote

# Fields lifted off a Quote for merging, and which of them are numeric.
_QUOTE_FIELDS = (
    "price",
    "currency",
    "name",
    "prev_close",
    "change",
    "change_pct",
    "day_open",
    "day_high",
    "day_low",
    "volume",
)
_NUMERIC = {"price", "prev_close", "change", "change_pct", "day_open", "day_high", "day_low", "volume"}

DEFAULT_TOLERANCE = 0.005  # 0.5% relative spread before we flag disagreement


def _quote_fields(q: Quote) -> dict[str, object]:
    return {f: getattr(q, f) for f in _QUOTE_FIELDS}


def merge_quotes(
    results: list[tuple[str, Quote]],
    *,
    symbol: str,
    asset_class: AssetClass,
    tolerance: float = DEFAULT_TOLERANCE,
) -> MergedRecord:
    record = MergedRecord(symbol=symbol, asset_class=asset_class)
    # collect candidate (source, value, fetched_at) per field, in priority order
    per_field: dict[str, list[tuple[str, object, object]]] = {f: [] for f in _QUOTE_FIELDS}
    for source, q in results:
        fields = _quote_fields(q)
        for f, val in fields.items():
            if val is not None:
                per_field[f].append((source, val, q.ts))

    for f, candidates in per_field.items():
        if not candidates:
            continue
        win_src, win_val, win_ts = candidates[0]
        record.fields[f] = FieldValue(value=win_val, source=win_src, fetched_at=win_ts)
        if len(candidates) > 1:
            record.alternates[f] = [
                FieldValue(value=v, source=s, fetched_at=t) for s, v, t in candidates[1:]
            ]
        if f in _NUMERIC:
            record.disagreement[f] = _disagrees(win_val, candidates[1:], tolerance)

    for f, flagged in record.disagreement.items():
        if flagged:
            spread = ", ".join(
                f"{s}={v}" for s, v, _ in [(c[0], c[1], c[2]) for c in per_field[f]]
            )
            record.warnings.append(f"sources disagree on {f}: {spread}")
    return record


def merge_fx(
    results: list[tuple[str, FXRate]],
    *,
    base: str,
    quote: str,
    tolerance: float = DEFAULT_TOLERANCE,
) -> MergedRecord:
    record = MergedRecord(symbol=f"{base}/{quote}", asset_class=AssetClass.FX)
    cands = [
        (src, fx.rate, datetime.combine(fx.ts, time())) for src, fx in results if fx.rate is not None
    ]
    if not cands:
        return record
    win_src, win_val, win_ts = cands[0]
    record.fields["rate"] = FieldValue(value=win_val, source=win_src, fetched_at=win_ts)
    if len(cands) > 1:
        record.alternates["rate"] = [
            FieldValue(value=v, source=s, fetched_at=t) for s, v, t in cands[1:]
        ]
    record.disagreement["rate"] = _disagrees(win_val, cands[1:], tolerance)
    if record.disagreement["rate"]:
        spread = ", ".join(f"{s}={v}" for s, v, _ in cands)
        record.warnings.append(f"sources disagree on rate: {spread}")
    return record


def _disagrees(winner: object, others: list[tuple[str, object, object]], tolerance: float) -> bool:
    try:
        w = Decimal(str(winner))
    except Exception:  # noqa: BLE001
        return False
    if w == 0:
        return False
    for _, val, _ in others:
        try:
            o = Decimal(str(val))
        except Exception:  # noqa: BLE001
            continue
        if abs((o - w) / w) > Decimal(str(tolerance)):
            return True
    return False
