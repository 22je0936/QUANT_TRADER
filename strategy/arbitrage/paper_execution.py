"""Paper-only paired execution with same-exchange fallback close handling."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping
from uuid import uuid4

from .config import ArbitrageConfig
from .costs import CostCalculator
from .models import (
    ArbitrageOpportunity,
    ExchangeName,
    MarketQuote,
    PaperExecution,
)


class PaperExecutor:
    """Simulate fills only; this component has no broker/order API dependency."""

    def __init__(self, config: ArbitrageConfig, costs: CostCalculator) -> None:
        self.config = config
        self.costs = costs

    def execute(
        self,
        opportunity: ArbitrageOpportunity,
        quotes: Mapping[ExchangeName, MarketQuote],
        now: datetime | None = None,
    ) -> PaperExecution:
        current_time = now or datetime.now(timezone.utc)
        primary_quote = quotes.get(opportunity.sell_exchange)
        if (
            self._can_fill(primary_quote, opportunity.quantity, current_time)
            and self._within_loss_cap(
                opportunity,
                primary_quote.bid,
                opportunity.quantity,
                opportunity.sell_exchange,
            )
        ):
            return self._complete(
                opportunity,
                opportunity.sell_exchange,
                primary_quote.bid,
                False,
                current_time,
            )

        fallback_quote = quotes.get(opportunity.buy_exchange)
        if (
            self._can_fill(fallback_quote, opportunity.quantity, current_time)
            and self._within_loss_cap(
                opportunity,
                fallback_quote.bid,
                opportunity.quantity,
                opportunity.buy_exchange,
            )
        ):
            return self._complete(
                opportunity,
                opportunity.buy_exchange,
                fallback_quote.bid,
                True,
                current_time,
            )

        filled_quantity = 0
        actual_sell_exchange: ExchangeName | None = None
        sell_price: Decimal | None = None
        open_quantity = opportunity.quantity
        fallback_used = fallback_quote is not None
        if fallback_quote and self._is_fresh(fallback_quote, current_time):
            filled_quantity = min(opportunity.quantity, fallback_quote.bid_quantity)
            if filled_quantity > 0 and fallback_quote.bid > 0:
                if self._within_loss_cap(
                    opportunity,
                    fallback_quote.bid,
                    filled_quantity,
                    opportunity.buy_exchange,
                ):
                    actual_sell_exchange = opportunity.buy_exchange
                    sell_price = fallback_quote.bid
                    open_quantity -= filled_quantity
                else:
                    filled_quantity = 0

        costs = Decimal("0")
        gross = Decimal("0")
        net = Decimal("0")
        if filled_quantity:
            gross = (sell_price - opportunity.buy_price) * filled_quantity
            costs = self.costs.calculate(
                opportunity.buy_price,
                sell_price,
                filled_quantity,
                opportunity.buy_exchange,
                actual_sell_exchange,
            ).total
            net = gross - costs

        return PaperExecution(
            execution_id=str(uuid4()),
            opportunity_id=opportunity.opportunity_id,
            symbol=opportunity.symbol,
            status="UNHEDGED" if open_quantity else "FALLBACK_CLOSED",
            quantity=opportunity.quantity,
            filled_quantity=filled_quantity,
            open_quantity=open_quantity,
            buy_exchange=opportunity.buy_exchange,
            intended_sell_exchange=opportunity.sell_exchange,
            actual_sell_exchange=actual_sell_exchange,
            buy_price=opportunity.buy_price,
            sell_price=sell_price,
            gross_profit=gross,
            costs=costs,
            net_profit=net,
            fallback_used=fallback_used,
            executed_at=current_time,
        )

    def _complete(
        self,
        opportunity: ArbitrageOpportunity,
        sell_exchange: ExchangeName,
        sell_price: Decimal,
        fallback_used: bool,
        executed_at: datetime,
    ) -> PaperExecution:
        gross = (sell_price - opportunity.buy_price) * opportunity.quantity
        costs = self.costs.calculate(
            opportunity.buy_price,
            sell_price,
            opportunity.quantity,
            opportunity.buy_exchange,
            sell_exchange,
        ).total
        return PaperExecution(
            execution_id=str(uuid4()),
            opportunity_id=opportunity.opportunity_id,
            symbol=opportunity.symbol,
            status="FALLBACK_CLOSED" if fallback_used else "PAPER_FILLED",
            quantity=opportunity.quantity,
            filled_quantity=opportunity.quantity,
            open_quantity=0,
            buy_exchange=opportunity.buy_exchange,
            intended_sell_exchange=opportunity.sell_exchange,
            actual_sell_exchange=sell_exchange,
            buy_price=opportunity.buy_price,
            sell_price=sell_price,
            gross_profit=gross,
            costs=costs,
            net_profit=gross - costs,
            fallback_used=fallback_used,
            executed_at=executed_at,
        )

    def _can_fill(
        self, quote: MarketQuote | None, quantity: int, now: datetime
    ) -> bool:
        return bool(
            quote
            and self._is_fresh(quote, now)
            and quote.bid > 0
            and quote.bid_quantity >= quantity
        )

    def _is_fresh(self, quote: MarketQuote, now: datetime) -> bool:
        age = (now - quote.timestamp).total_seconds()
        return 0 <= age <= self.config.max_quote_age_seconds

    def _within_loss_cap(
        self,
        opportunity: ArbitrageOpportunity,
        sell_price: Decimal,
        quantity: int,
        sell_exchange: ExchangeName,
    ) -> bool:
        gross_profit = (sell_price - opportunity.buy_price) * quantity
        costs = self.costs.calculate(
            opportunity.buy_price,
            sell_price,
            quantity,
            opportunity.buy_exchange,
            sell_exchange,
        ).total
        return gross_profit - costs >= -self.config.max_fallback_loss