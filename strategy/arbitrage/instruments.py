"""Scrip-master lookup for the instruments monitored by the watcher."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.core.arbitrage_config import EXCHANGES, EXCH_TYPE


@dataclass(frozen=True)
class Instrument:
    name: str
    exchange: str
    symbol: str
    token: str


@dataclass(frozen=True)
class InstrumentCatalog:
    by_name: dict[str, dict[str, Instrument]]
    by_token: dict[tuple[int, str], tuple[str, str]]
    missing_names: tuple[str, ...]


def load_instruments(scrip_file: Path, watchlist: tuple[str, ...]) -> InstrumentCatalog:
    """Load watchlist instruments that have entries on every configured exchange."""
    if not scrip_file.exists():
        raise FileNotFoundError(f"Missing scrip master file: {scrip_file}")

    with scrip_file.open(encoding="utf-8") as source:
        rows = json.load(source)

    by_exchange: dict[str, dict[str, dict[str, object]]] = {
        exchange: {} for exchange in EXCHANGES
    }
    for row in rows:
        exchange = row.get("exch_seg")
        if exchange in by_exchange:
            by_exchange[exchange].setdefault(str(row.get("name", "")).upper(), row)

    by_name: dict[str, dict[str, Instrument]] = {}
    by_token: dict[tuple[int, str], tuple[str, str]] = {}
    missing_names: list[str] = []

    for name in watchlist:
        exchange_rows = {
            exchange: by_exchange[exchange].get(name.upper()) for exchange in EXCHANGES
        }
        if any(row is None for row in exchange_rows.values()):
            missing_names.append(name)
            continue

        instruments = {
            exchange: Instrument(
                name=name,
                exchange=exchange,
                symbol=str(row["symbol"]),
                token=str(row["token"]),
            )
            for exchange, row in exchange_rows.items()
            if row is not None
        }
        by_name[name] = instruments
        for exchange, instrument in instruments.items():
            by_token[(EXCH_TYPE[exchange], instrument.token)] = (name, exchange)

    return InstrumentCatalog(by_name, by_token, tuple(missing_names))