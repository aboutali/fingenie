# FinGenie

A **lightweight engine that bundles many free financial-data sources behind one
clean, normalized interface.** Ask for a price, history, or FX rate; FinGenie
picks the best free source for that asset, falls back when one is rate-limited or
down, caches locally to stretch free tiers, and can merge fields across sources
with disagreement flagging.

No single free API covers everything, they all have brutal free-tier limits, and
they all use different schemas. FinGenie hides that behind one small API + CLI.

**Scope:** FinGenie stays a lean personal tool for prices, history and FX. It
does not aim to become a research platform.

## FinGenie and OpenBB

The [OpenBB Platform](https://github.com/OpenBB-finance/OpenBB) also puts many
data providers behind one normalized API. Use OpenBB when you need breadth:
fundamentals, macro series, SEC filings, dozens of providers.

FinGenie covers a narrower need. It focuses on staying inside free tiers:

| | FinGenie | OpenBB |
|---|---|---|
| Automatic fallback on error or rate limit | yes | not documented (static provider priority) |
| Local response cache | yes | not documented |
| Rate budgets stored across restarts | yes | not documented |
| Cross-source merge with disagreement flags | yes | not documented |
| CoinGecko, Finnhub, Twelve Data | yes | no |
| FRED, SEC EDGAR, many more providers | no | yes |
| License | MIT | AGPL-3.0 |
| Install size | 10 dependencies | ~30 packages in the base install |

OpenBB comparison checked against OpenBB v4.7.2 (September 2026).

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

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Configure (optional)

Copy `.env.example` to `.env` and add any free keys you have (Tiingo, Finnhub,
Twelve Data — email signup, no credit card). Without them, FinGenie still runs on
the no-key sources.

## Use

CLI:

```bash
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

- OpenFIGI symbol mapping, to resolve tickers across sources.
- More free price sources only when a real gap appears.

Macro data and fundamentals stay out of scope. Use OpenBB for those.

## Develop

```bash
pytest          # fully offline (respx-mocked adapters) — no API quota used
ruff check .
```
