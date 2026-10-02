"""Broker-independent, timestamp-aware NSE/BSE arbitrage detection."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping
from uuid import uuid4

from .config import ArbitrageConfig
from .costs import CostCalculator
from .models import ArbitrageOpportunity, ExchangeName, MarketQuote


class ArbitrageEngine:
    """Evaluate synchronized bid/ask quotes after estimated transaction costs."""

    def __init__(self, config: ArbitrageConfig, costs: CostCalculator) -> None:
        self.config = config
        self.costs = costs
        self._quotes: dict[str, dict[ExchangeName, MarketQuote]] = {}
        self._last_opportunity: dict[str, datetime] = {}

    @property
    def latest_quotes(self) -> Mapping[str, Mapping[ExchangeName, MarketQuote]]:
        return self._quotes

    def update_quote(
        self, quote: MarketQuote, now: datetime | None = None
    ) -> ArbitrageOpportunity | None:
        self._quotes.setdefault(quote.symbol, {})[quote.exchange] = quote
        return self.evaluate(quote.symbol, now)

    def evaluate(
        self, symbol: str, now: datetime | None = None
    ) -> ArbitrageOpportunity | None:
        quotes = self._quotes.get(symbol, {})
        if "NSE" not in quotes or "BSE" not in quotes:
            return None

        current_time = now or datetime.now(timezone.utc)
        nse_quote, bse_quote = quotes["NSE"], quotes["BSE"]
        if not self._quotes_are_fresh(nse_quote, bse_quote, current_time):
            return None
        last_opportunity = self._last_opportunity.get(symbol)
        if (
            last_opportunity
            and (current_time - last_opportunity).total_seconds() < self.config.cooldown_seconds
        ):
            return None

        candidates: list[ArbitrageOpportunity] = []
        for buy_quote, sell_quote in ((nse_quote, bse_quote), (bse_quote, nse_quote)):
            quantity = min(
                self.config.paper_quantity,
                buy_quote.ask_quantity,
                sell_quote.bid_quantity,
            )
            if quantity < self.config.min_quantity or buy_quote.ask <= 0 or sell_quote.bid <= 0:
                continue

            gross_profit = (sell_quote.bid - buy_quote.ask) * quantity
            if gross_profit <= 0:
                continue
            charges = self.costs.calculate(
                buy_quote.ask,
                sell_quote.bid,
                quantity,
                buy_quote.exchange,
                sell_quote.exchange,
            )
            net_profit = gross_profit - charges.total
            if net_profit <= self.config.min_net_profit:
                continue
            candidates.append(
                ArbitrageOpportunity(
                    opportunity_id=str(uuid4()),
                    symbol=symbol,
                    detected_at=current_time,
                    buy_exchange=buy_quote.exchange,
                    sell_exchange=sell_quote.exchange,
                    buy_price=buy_quote.ask,
                    sell_price=sell_quote.bid,
                    quantity=quantity,
                    gross_profit=gross_profit,
                    costs=charges,
                    estimated_net_profit=net_profit,
                    buy_quote_timestamp=buy_quote.timestamp,
                    sell_quote_timestamp=sell_quote.timestamp,
                )
            )

        if not candidates:
            return None
        opportunity = max(candidates, key=lambda item: item.estimated_net_profit)
        self._last_opportunity[symbol] = current_time
        return opportunity

    def _quotes_are_fresh(
        self, nse: MarketQuote, bse: MarketQuote, now: datetime
    ) -> bool:
        allowed_age = self.config.max_quote_age_seconds
        if abs((nse.timestamp - bse.timestamp).total_seconds()) > allowed_age:
            return False
        return all(
            0 <= (now - quote.timestamp).total_seconds() <= allowed_age
            for quote in (nse, bse)
        )