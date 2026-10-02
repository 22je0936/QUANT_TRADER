"""Fetch Angel One historical candles into one JSON file per instrument and day.

Angel One's historical endpoint returns candles, not individual historical ticks.
Use the live WebSocket feed and ClickHouse ingestion for tick-by-tick capture.

Example:
    python data/historical/fetch_historical_data.py --date 2026-10-01 \
        --symbols RELIANCE KOTAKBANK
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter  # noqa: E402
from src.config.settings import get_settings  # noqa: E402

SCRIP_FILE = ROOT / "data" / "share_response.json"
DEFAULT_SYMBOLS = ("RELIANCE", "KOTAKBANK")
EXCHANGES = ("NSE", "BSE")
INTERVALS = (
    "ONE_MINUTE",
    "THREE_MINUTE",
    "FIVE_MINUTE",
    "TEN_MINUTE",
    "FIFTEEN_MINUTE",
    "THIRTY_MINUTE",
    "ONE_HOUR",
    "ONE_DAY",
)


def load_instruments(
    scrip_file: Path, symbols: tuple[str, ...]
) -> dict[str, dict[str, dict[str, str]]]:
    with scrip_file.open(encoding="utf-8") as source:
        rows = json.load(source)

    wanted = {symbol.upper() for symbol in symbols}
    instruments: dict[str, dict[str, dict[str, str]]] = {symbol: {} for symbol in wanted}
    for row in rows:
        symbol = str(row.get("name", "")).upper()
        exchange = row.get("exch_seg")
        if symbol in instruments and exchange in EXCHANGES and exchange not in instruments[symbol]:
            instruments[symbol][exchange] = {
                "token": str(row["token"]),
                "symbol": str(row["symbol"]),
            }

    missing = [
        f"{symbol} ({exchange})"
        for symbol, exchanges in instruments.items()
        for exchange in EXCHANGES
        if exchange not in exchanges
    ]
    if missing:
        raise ValueError(f"Scrip master is missing requested instruments: {', '.join(missing)}")
    return instruments


def normalize_candles(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Give each SmartAPI candle row named fields for easier downstream use."""
    candles = []
    for row in rows:
        if len(row) < 6:
            continue
        candles.append(
            {
                "timestamp": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
            }
        )
    return candles


def fetch_day(
    client: Any,
    instruments: dict[str, dict[str, dict[str, str]]],
    trading_date: date,
    interval: str,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    day = trading_date.isoformat()

    for index, (name, exchanges) in enumerate(instruments.items()):
        for exchange, instrument in exchanges.items():
            if index:
                time.sleep(0.5)

            response = client.getCandleData(
                {
                    "exchange": exchange,
                    "symboltoken": instrument["token"],
                    "interval": interval,
                    "fromdate": f"{day} 09:15",
                    "todate": f"{day} 15:30",
                }
            )
            if not response or not response.get("status"):
                message = (response or {}).get("message", "empty response")
                raise RuntimeError(
                    f"Angel One returned an error for {name} on {exchange}: {message}"
                )

            payload = {
                "data_type": "historical_candles",
                "interval": interval,
                "date": day,
                "name": name,
                "exchange": exchange,
                "symbol": instrument["symbol"],
                "token": instrument["token"],
                "candles": normalize_candles(response.get("data") or []),
            }
            output_file = output_dir / (
                f"equity_{name}_{day}_{exchange.lower()}.json"
            )
            output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(f"[ok] {name} {exchange}: {len(payload['candles'])} candles -> {output_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2026-10-01", help="Trading date in YYYY-MM-DD format")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--interval", choices=INTERVALS, default="ONE_MINUTE")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trading_date = date.fromisoformat(args.date)
    instruments = load_instruments(SCRIP_FILE, tuple(args.symbols))

    settings = get_settings()
    broker = AngelOneBrokerAdapter(
        settings.angel_one_api_key,
        settings.angel_one_client_id,
        settings.angel_one_password,
        settings.angel_one_totp_secret,
    )
    broker.connect()
    try:
        client = getattr(broker, "_client", None)
        if client is None:
            raise RuntimeError("Angel One broker did not initialize a client")
        fetch_day(client, instruments, trading_date, args.interval, args.output_dir)
    finally:
        broker.disconnect()


if __name__ == "__main__":
    main()