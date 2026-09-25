# FinGenie

A **lightweight engine that bundles many free financial-data sources behind one
clean, normalized interface.** Ask for a price, history, or FX rate; FinGenie
picks the best free source for that asset, falls back when one is rate-limited or
down, caches locally to stretch free tiers, and can merge fields across sources
with disagreement flagging.

No single free API covers everything, they all have brutal free-tier limits, and
they all use different schemas. FinGenie hides that behind one small API + CLI.

## What's in v1 (prices-first)

`quote` · `history` · `fx` across equities/ETFs, crypto, FX and (best-effort)
commodities, over six free sources:

| Source | Key? | Role |
|---|---|---|
| yfinance | none | broad quotes/history (lowest-priority fallback — flaky) |
| CoinGecko | none | crypto |
| Frankfurter (ECB) | none | daily FX reference rates |
| Tiingo | free key | clean reliable EOD history |
| Finnhub | free key | real-time US quotes |
| Twelve Data | free key | unified intraday multi-asset |

Sources whose key is missing are skipped automatically — **the no-key sources
work with zero configuration.**

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Configure (optional)

Copy `.env.example` to `.env` and add any free keys you have (Tiingo, Finnhub,
Twelve Data — email signup, no credit card). Without them, FinGenie still runs on
the no-key sources.

## Use

CLI:

```powershell
fingenie quote AAPL
fingenie quote BTC-USD --merge          # combine sources, flag disagreement
fingenie history BTC-USD --range 1y
fingenie fx EUR USD
fingenie sources                        # configured sources + remaining budgets
fingenie cache stats
```

Library:

```python
from fingenie import Genie

with Genie() as g:
    q = g.quote("AAPL")                 # -> Quote (auto-routed + cached)
    bars = g.history("BTC-USD", range="6mo")
    rate = g.fx("EUR", "USD")
    merged = g.quote("ETH-USD", merge=True)   # -> MergedRecord with provenance
```

## How it works

```
symbol -> SymbolResolver -> cache lookup -> CapabilityRouter (priority + fallback)
       -> source adapter (rate-governed httpx) -> canonical model -> (optional) merge
```

- **Canonical models** (`Quote`, `OHLCVBar`, `FXRate`) — one schema all sources normalize to.
- **CapabilityRouter** — tries sources in priority order for `(asset_class, datatype)`,
  skipping rate-exhausted/failing ones.
- **TTL cache** (diskcache/SQLite) — cache hits cost zero rate budget.
- **Rate governor** — per-source budgets persisted in SQLite, so daily caps survive restarts.
- **Light merge** — fill missing fields from the next source; flag (never hide) numeric disagreement.

## Roadmap

Beyond v1: OpenFIGI symbol/ID mapping → FRED macro (series-keyed, pinned-source)
→ SEC EDGAR fundamentals + `report` + metrics. See the plan for the full,
researched source catalog (DBnomics, news/sentiment, DeFi, etc.).

## Develop

```powershell
pytest          # fully offline (respx-mocked adapters) — no API quota used
ruff check .
```
