"""All tunable settings in one place. Change values here, nothing else."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# project root = parent of the "strategy" folder (this file: strategy/arbitrage/config.py)
ROOT = Path(__file__).resolve().parents[2]

# Angel One websocket exchange codes
EXCH_TYPE = {"NSE": 1, "BSE": 3}
EXCHANGES = tuple(EXCH_TYPE)  # ("NSE", "BSE")


@dataclass(frozen=True)
class Config:
    watchlist: tuple[str, ...] = (
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "ITC", "LT", "AXISBANK", "KOTAKBANK",
    )
    scrip_file: Path = ROOT / "data" / "share_response.json"

    min_spread_pct: float = 0.20   # must exceed total costs (brokerage, STT, charges)
    min_qty: int = 1               # min quantity at best bid/ask
    max_quote_age: float = 2.0     # seconds; ignore if NSE/BSE quotes are further apart
    cooldown_sec: float = 5.0      # per stock, avoids repeated signals

    place_orders: bool = False     # keep False until you've paper-tested
    order_qty: int = 1
    product_type: str = "INTRADAY"