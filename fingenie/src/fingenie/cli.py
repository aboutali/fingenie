"""FinGenie command-line interface (Typer + rich).

A thin wrapper over the Genie facade: pretty tables, source/cache management, and
the cache/merge flags. No business logic lives here.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .errors import FinGenieError
from .genie import Genie
from .models import AssetClass, FXRate, MergedRecord, Quote

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Bundle many free financial-data sources behind one clean interface.",
)
console = Console()
err = Console(stderr=True)


def _asset(value: str | None) -> AssetClass | None:
    if not value:
        return None
    try:
        return AssetClass(value.lower())
    except ValueError:
        raise typer.BadParameter(f"unknown asset class: {value}") from None


def _fail(exc: Exception) -> None:
    err.print(f"[bold red]error:[/] {exc}")
    raise typer.Exit(code=1)


@app.command()
def quote(
    symbol: str = typer.Argument(..., help="Ticker / pair, e.g. AAPL, BTC-USD, EUR/USD"),
    asset: str | None = typer.Option(None, help="Force asset class (equity/crypto/fx/...)"),
    merge: bool = typer.Option(False, "--merge", help="Combine all sources, flag disagreement"),
    refresh: bool = typer.Option(False, "--refresh", help="Bypass cache, then repopulate"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Don't read or write the cache"),
) -> None:
    """Latest price for a symbol."""
    g = Genie()
    try:
        result = g.quote(symbol, asset=_asset(asset), merge=merge, refresh=refresh, no_cache=no_cache)
    except FinGenieError as exc:
        _fail(exc)
    finally:
        g.close()
    if isinstance(result, MergedRecord):
        _print_merged(result)
    else:
        _print_quote(result)


@app.command()
def history(
    symbol: str = typer.Argument(..., help="Ticker / pair"),
    asset: str | None = typer.Option(None, help="Force asset class"),
    interval: str = typer.Option("1d", help="1d, 1wk, 1mo, 1h"),
    range_: str = typer.Option("1mo", "--range", help="1mo, 6mo, 1y, ytd, max ..."),
    start: str | None = typer.Option(None, help="YYYY-MM-DD (overrides --range)"),
    end: str | None = typer.Option(None, help="YYYY-MM-DD"),
    rows: int = typer.Option(12, help="Number of most-recent bars to show"),
    refresh: bool = typer.Option(False, "--refresh"),
    no_cache: bool = typer.Option(False, "--no-cache"),
) -> None:
    """Historical OHLCV bars."""
    g = Genie()
    try:
        bars = g.history(
            symbol, asset=_asset(asset), interval=interval, start=start, end=end,
            range=range_, refresh=refresh, no_cache=no_cache,
        )
    except FinGenieError as exc:
        _fail(exc)
    finally:
        g.close()
    _print_history(symbol, bars[-rows:])


@app.command()
def fx(
    pair: str = typer.Argument(..., help="EUR/USD or EUR (quote defaults to USD)"),
    quote_ccy: str | None = typer.Argument(None, help="Optional quote currency"),
    merge: bool = typer.Option(False, "--merge"),
    refresh: bool = typer.Option(False, "--refresh"),
    no_cache: bool = typer.Option(False, "--no-cache"),
) -> None:
    """Latest FX rate."""
    g = Genie()
    try:
        result = g.fx(pair, quote_ccy, merge=merge, refresh=refresh, no_cache=no_cache)
    except FinGenieError as exc:
        _fail(exc)
    finally:
        g.close()
    if isinstance(result, MergedRecord):
        _print_merged(result)
    else:
        _print_fx(result)


@app.command()
def sources() -> None:
    """Show configured sources, capabilities and remaining rate budget."""
    g = Genie()
    try:
        statuses = g.sources()
    finally:
        g.close()
    table = Table(title="FinGenie sources")
    table.add_column("source")
    table.add_column("status")
    table.add_column("key")
    table.add_column("remaining")
    table.add_column("capabilities", overflow="fold")
    for s in sorted(statuses, key=lambda x: (not x.available, x.name)):
        status = "[green]on[/]" if s.available else "[dim]off[/]"
        rem = " ".join(f"{k}:{v}" for k, v in s.remaining.items()) or "-"
        note = f" [dim]({s.note})[/]" if s.note else ""
        table.add_row(
            s.name, status + note, "yes" if s.needs_key else "no", rem,
            ", ".join(s.capabilities) or "-",
        )
    console.print(table)


@app.command()
def cache(
    action: str = typer.Argument("stats", help="stats | clear"),
) -> None:
    """Inspect or clear the local cache."""
    g = Genie()
    try:
        if action == "clear":
            n = g.cache.clear()
            console.print(f"[green]cleared[/] {n} cache entries")
        else:
            st = g.cache.stats()
            console.print(
                f"cache: [cyan]{st['count']}[/] entries, "
                f"{st['size_bytes'] / 1024:.0f} KiB at {st['directory']}"
            )
    finally:
        g.close()


@app.command()
def version() -> None:
    """Print the FinGenie version."""
    console.print(f"fingenie {__version__}")


# -- rendering helpers --------------------------------------------------------
def _print_quote(q: Quote) -> None:
    table = Table(title=f"{q.symbol}  ({q.asset_class.value})")
    table.add_column("field")
    table.add_column("value", justify="right")
    table.add_row("price", f"{q.price} {q.currency or ''}".strip())
    if q.change is not None:
        chg = f"{q.change}" + (f" ({q.change_pct:+.2f}%)" if q.change_pct is not None else "")
        table.add_row("change", chg)
    if q.prev_close is not None:
        table.add_row("prev close", str(q.prev_close))
    if q.day_high is not None or q.day_low is not None:
        table.add_row("day range", f"{q.day_low} - {q.day_high}")
    if q.volume is not None:
        table.add_row("volume", str(q.volume))
    table.add_row("as of", q.ts.isoformat())
    table.add_row("source", q.source)
    console.print(table)


def _print_fx(r: FXRate) -> None:
    table = Table(title=f"{r.base}/{r.quote}")
    table.add_column("field")
    table.add_column("value", justify="right")
    table.add_row("rate", str(r.rate))
    table.add_row("date", r.ts.isoformat())
    table.add_row("source", r.source)
    console.print(table)


def _print_history(symbol: str, bars) -> None:
    if not bars:
        console.print("[yellow]no data[/]")
        return
    table = Table(title=f"{symbol}  -  {len(bars)} bars ({bars[0].source})")
    for col in ("date", "open", "high", "low", "close", "volume"):
        table.add_column(col, justify="right" if col != "date" else "left")
    for b in bars:
        table.add_row(
            b.ts.date().isoformat(),
            _fmt(b.open), _fmt(b.high), _fmt(b.low), _fmt(b.close), _fmt(b.volume),
        )
    console.print(table)


def _print_merged(r: MergedRecord) -> None:
    table = Table(title=f"{r.symbol}  ({r.asset_class.value})  -  merged")
    table.add_column("field")
    table.add_column("value", justify="right")
    table.add_column("source")
    table.add_column("agree")
    for name, fv in r.fields.items():
        flagged = r.disagreement.get(name, False)
        table.add_row(
            name, str(fv.value), fv.source,
            "[red]DIFF[/]" if flagged else "[green]ok[/]",
        )
    console.print(table)
    for w in r.warnings:
        err.print(f"[yellow]warning:[/] {w}")


def _fmt(v) -> str:
    return "" if v is None else str(v)


if __name__ == "__main__":  # pragma: no cover
    app()
