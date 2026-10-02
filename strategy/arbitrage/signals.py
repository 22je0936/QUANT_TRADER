"""Quote parsing and arbitrage signal evaluation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from src.core.arbitrage_config import Config


@dataclass(frozen=True)
class Quote:
    bid: float
    bid_qty: int | None
    ask: float
    ask_qty: int | None
    timestamp: float


@dataclass(frozen=True)
class ArbitrageSignal:
    name: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread: float
    spread_pct: float
    quantity: int | None


def parse_quote(message: dict[str, Any], timestamp: float | None = None) -> Quote | None:
    """Convert a SmartAPI market-depth payload into a normalized quote."""
    bids = message.get("best_5_buy_data") or []
    asks = message.get("best_5_sell_data") or []
    best_bid = max(bids, key=lambda level: int(level.get("price", 0)), default=None)
    best_ask = min(asks, key=lambda level: int(level.get("price", 0)), default=None)
    if best_bid is None or best_ask is None:
        return None

    def quantity(level: dict[str, Any]) -> int | None:
        value = level.get("quantity")
        return int(value) if value is not None else None

    return Quote(
        bid=float(best_bid["price"]) / 100.0,
        bid_qty=quantity(best_bid),
        ask=float(best_ask["price"]) / 100.0,
        ask_qty=quantity(best_ask),
        timestamp=time.time() if timestamp is None else timestamp,
    )


class ArbitrageSignalEngine:
    """Maintain recent quotes and apply spread, freshness, and cooldown rules."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._quotes: dict[str, dict[str, Quote]] = {}
        self._last_signal: dict[str, float] = {}

    def update_quote(
        self, name: str, exchange: str, quote: Quote, now: float | None = None
    ) -> ArbitrageSignal | None:
        self._quotes.setdefault(name, {})[exchange] = quote
        return self.evaluate(name, now)

    def evaluate(self, name: str, now: float | None = None) -> ArbitrageSignal | None:
        exchange_quotes = self._quotes.get(name, {})
        if "NSE" not in exchange_quotes or "BSE" not in exchange_quotes:
            return None

        current_time = time.time() if now is None else now
        nse_quote, bse_quote = exchange_quotes["NSE"], exchange_quotes["BSE"]
        if abs(nse_quote.timestamp - bse_quote.timestamp) > self._config.max_quote_age:
            return None
        if current_time - self._last_signal.get(name, 0) < self._config.cooldown_sec:
            return None

        for buy_exchange, sell_exchange in (("NSE", "BSE"), ("BSE", "NSE")):
            buy_quote = exchange_quotes[buy_exchange]
            sell_quote = exchange_quotes[sell_exchange]
            buy_price, sell_price = buy_quote.ask, sell_quote.bid
            if buy_price <= 0 or sell_price <= 0:
                continue

            available_qty = None
            if buy_quote.ask_qty is not None and sell_quote.bid_qty is not None:
                available_qty = min(buy_quote.ask_qty, sell_quote.bid_qty)

            spread_pct = (sell_price - buy_price) / buy_price * 100
            if spread_pct < self._config.min_spread_pct:
                continue
            if available_qty is not None and available_qty < self._config.min_qty:
                continue

            self._last_signal[name] = current_time
            return ArbitrageSignal(
                name=name,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                buy_price=buy_price,
                sell_price=sell_price,
                spread=sell_price - buy_price,
                spread_pct=spread_pct,
                quantity=available_qty,
            )

        return None