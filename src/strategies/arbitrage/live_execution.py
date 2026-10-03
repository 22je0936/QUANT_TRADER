"""Risk-gated, exchange-aware two-leg live execution for explicit opt-in use."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from decimal import Decimal

from src.core.entities import (
    Exchange,
    MarketQuote,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    TransactionType,
)
from src.core.exceptions import RiskLimitBreachedError
from src.core.interfaces import IBrokerGateway
from src.infra.logging import get_logger
from src.risk.risk_manager import RiskManager

from .config import ArbitrageConfig
from .costs import CostCalculator
from .instruments import Instrument
from .models import (
    ArbitrageOpportunity,
    ExchangeName,
    LiveExecutionReport,
    LiveOrderEvent,
)
from .storage import CsvJournal

logger = get_logger(__name__)

_TERMINAL_STATUSES = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}


class LiveOrderReconciliationError(RuntimeError):
    """Raised when broker state is unknown and exposure needs manual reconciliation."""

    def __init__(self, message: str, possible_open_quantity: int) -> None:
        super().__init__(message)
        self.possible_open_quantity = possible_open_quantity


class LiveArbitrageExecutor:
    """Submit paired LIMIT orders, reconcile fills, and cap the fallback loss."""

    def __init__(
        self,
        broker: IBrokerGateway,
        risk_manager: RiskManager,
        config: ArbitrageConfig,
        costs: CostCalculator,
        journal: CsvJournal,
        latest_quotes: Callable[[str], Mapping[ExchangeName, MarketQuote]],
    ) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._config = config
        self._costs = costs
        self._journal = journal
        self._latest_quotes = latest_quotes





    def execute(
        self,
        opportunity: ArbitrageOpportunity,
        buy_instrument: Instrument,
        sell_instrument: Instrument,
    ) -> LiveExecutionReport:
        started_at = datetime.now(timezone.utc)
        bought_quantity = 0
        sold_quantity = 0
        buy_average: Decimal | None = None
        exit_fills: list[tuple[int, Decimal, ExchangeName]] = []
        open_quantity = 0
        active_order_quantity = 0
        order_submission_started = False

        try:
            buy_order = self._make_order(
                opportunity,
                buy_instrument,
                TransactionType.BUY,
                opportunity.quantity,
                opportunity.buy_price,
            )
            active_order_quantity = buy_order.quantity
            buy_result = self._submit_and_reconcile(
                opportunity, "ENTRY_BUY", buy_order, possible_open_quantity=buy_order.quantity
            )
            order_submission_started = True
            bought_quantity = buy_result.filled_quantity
            if bought_quantity == 0:
                return self._finish(
                    opportunity,
                    "NO_BUY_FILL",
                    bought_quantity,
                    sold_quantity,
                    0,
                    buy_instrument,
                    sell_instrument,
                    None,
                    None,
                    exit_fills,
                    started_at,
                    "Entry order was cancelled/rejected without a fill.",
                )

            buy_average = buy_result.average_price or buy_order.price
            if buy_average is None:
                raise LiveOrderReconciliationError(
                    "Buy fill has no average price; reconcile broker trade book manually.",
                    bought_quantity,
                )
            open_quantity = bought_quantity
            self._set_position(buy_order.instrument_id, open_quantity, buy_average)

            primary_order = self._make_order(
                opportunity,
                sell_instrument,
                TransactionType.SELL,
                bought_quantity,
                opportunity.sell_price,
            )
            active_order_quantity = primary_order.quantity
            primary_result = self._submit_and_reconcile(
                opportunity,
                "CROSS_EXCHANGE_SELL",
                primary_order,
                possible_open_quantity=open_quantity,
            )
            order_submission_started = True
            primary_filled = min(primary_result.filled_quantity, open_quantity)
            sold_quantity += primary_filled
            if primary_filled:
                primary_price = primary_result.average_price or primary_order.price
                if primary_price is None:
                    raise LiveOrderReconciliationError(
                        "Sell fill has no average price; reconcile broker trade book manually.",
                        open_quantity,
                    )
                exit_fills.append((primary_filled, primary_price, sell_instrument.exchange))
                open_quantity -= primary_filled
                self._set_position(buy_order.instrument_id, open_quantity, buy_average)

            fallback_exchange: ExchangeName | None = None
            if open_quantity:
                fallback_exchange = self._try_fallback(
                    opportunity,
                    buy_instrument,
                    buy_average,
                    open_quantity,
                    exit_fills,
                )
                if fallback_exchange is not None:
                    fallback_quote = self._latest_quotes(opportunity.symbol)[
                        buy_instrument.exchange
                    ]
                    fallback_order = self._make_order(
                        opportunity,
                        buy_instrument,
                        TransactionType.SELL,
                        min(open_quantity, fallback_quote.bid_quantity),
                        fallback_quote.bid,
                    )
                    active_order_quantity = fallback_order.quantity
                    fallback_result = self._submit_and_reconcile(
                        opportunity,
                        "SAME_EXCHANGE_FALLBACK_SELL",
                        fallback_order,
                        possible_open_quantity=open_quantity,
                    )
                    order_submission_started = True
                    fallback_filled = min(fallback_result.filled_quantity, open_quantity)
                    if fallback_filled:
                        fallback_price = fallback_result.average_price or fallback_order.price
                        if fallback_price is None:
                            raise LiveOrderReconciliationError(
                                "Fallback fill has no average price; reconcile broker trade book manually.",
                                open_quantity,
                            )
                        exit_fills.append((fallback_filled, fallback_price, buy_instrument.exchange))
                        sold_quantity += fallback_filled
                        open_quantity -= fallback_filled
                        self._set_position(buy_order.instrument_id, open_quantity, buy_average)

            estimated_costs, estimated_net_pnl = self._estimate_pnl(
                buy_average, exit_fills, buy_instrument.exchange
            )
            status = "CLOSED" if open_quantity == 0 else "UNHEDGED"
            report = self._finish(
                opportunity,
                status,
                bought_quantity,
                sold_quantity,
                open_quantity,
                buy_instrument,
                sell_instrument,
                fallback_exchange,
                buy_average,
                self._weighted_sell_price(exit_fills),
                exit_fills,
                started_at,
                "" if open_quantity == 0 else "Fallback could not close all filled quantity.",
                estimated_costs,
                estimated_net_pnl,
            )
            self._risk.record_fill_pnl(estimated_net_pnl)
            if open_quantity:
                self._risk.engage_kill_switch("Live fallback left an open position")
                logger.error(
                    "live_arbitrage_position_unhedged",
                    opportunity_id=opportunity.opportunity_id,
                    open_quantity=open_quantity,
                )
            return report
        except LiveOrderReconciliationError as exc:
            self._risk.engage_kill_switch(str(exc))
            conservative_open_quantity = max(open_quantity, exc.possible_open_quantity)
            report = self._finish(
                opportunity,
                "MANUAL_RECONCILIATION",
                bought_quantity,
                sold_quantity,
                conservative_open_quantity,
                buy_instrument,
                sell_instrument,
                None,
                buy_average,
                self._weighted_sell_price(exit_fills),
                exit_fills,
                started_at,
                str(exc),
            )
            logger.exception(
                "live_arbitrage_reconciliation_required",
                opportunity_id=opportunity.opportunity_id,
                order_quantity=active_order_quantity,
                order_submitted=order_submission_started,
            )
            return report
        except Exception as exc:
            self._risk.engage_kill_switch(f"Live execution failed: {exc}")
            conservative_open_quantity = max(
                open_quantity,
                active_order_quantity if order_submission_started else 0,
            )
            self._finish(
                opportunity,
                "MANUAL_RECONCILIATION" if conservative_open_quantity else "ABORTED",
                bought_quantity,
                sold_quantity,
                conservative_open_quantity,
                buy_instrument,
                sell_instrument,
                None,
                buy_average,
                self._weighted_sell_price(exit_fills),
                exit_fills,
                started_at,
                str(exc),
            )
            logger.exception(
                "live_arbitrage_execution_failed",
                opportunity_id=opportunity.opportunity_id,
                order_submitted=order_submission_started,
            )
            raise

    def _make_order(
        self,
        opportunity: ArbitrageOpportunity,
        instrument: Instrument,
        side: TransactionType,
        quantity: int,
        price: Decimal,
    ) -> Order:
        return Order(
            instrument_id=f"{instrument.exchange}:{instrument.token}",
            transaction_type=side,
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
            quantity=quantity,
            price=price,
            exchange=Exchange(instrument.exchange),
            trading_symbol=instrument.symbol,
            symbol_token=instrument.token,
            strategy_id=f"arbitrage:{opportunity.opportunity_id}",
        )

    def _submit_and_reconcile(
        self,
        opportunity: ArbitrageOpportunity,
        leg: str,
        order: Order,
        possible_open_quantity: int,
    ) -> Order:
        try:
            self._risk.validate_order(order)
        except RiskLimitBreachedError:
            logger.exception("live_order_blocked_by_risk", leg=leg)
            raise

        self._record_order_event(opportunity, leg, order, "SUBMISSION_INTENT")
        try:
            self._broker.place_order(order)
            self._record_order_event(opportunity, leg, order, "SUBMITTED")
        except LiveOrderReconciliationError:
            raise
        except Exception as exc:
            raise LiveOrderReconciliationError(
                f"Submission or journaling result for {leg} is ambiguous; "
                f"check broker order book manually: {exc}",
                possible_open_quantity,
            ) from exc

        try:
            return self._wait_for_terminal(opportunity, leg, order)
        except Exception as exc:
            raise LiveOrderReconciliationError(
                f"Could not reconcile {leg} order {order.broker_order_id}: {exc}",
                possible_open_quantity,
            ) from exc

    def _wait_for_terminal(
        self, opportunity: ArbitrageOpportunity, leg: str, order: Order
    ) -> Order:
        deadline = time.monotonic() + self._config.live_order_timeout_seconds
        cancellation_requested = False
        while True:
            status = self._broker.get_order_status(order.client_order_id)
            self._record_order_event(opportunity, leg, status, "STATUS")
            if status.status in _TERMINAL_STATUSES or status.filled_quantity >= status.quantity:
                return status
            if time.monotonic() >= deadline:
                if cancellation_requested:
                    raise TimeoutError("Order did not reach a terminal state after cancellation")
                cancellation_requested = True
                self._record_order_event(opportunity, leg, status, "CANCEL_INTENT")
                status = self._broker.cancel_order(order.client_order_id)
                self._record_order_event(opportunity, leg, status, "CANCEL_RESPONSE")
                deadline = time.monotonic() + self._config.live_order_timeout_seconds
            else:
                time.sleep(self._config.live_order_poll_seconds)

    def _try_fallback(
        self,
        opportunity: ArbitrageOpportunity,
        buy_instrument: Instrument,
        buy_average: Decimal,
        open_quantity: int,
        exits: list[tuple[int, Decimal, ExchangeName]],
    ) -> ExchangeName | None:
        quote = self._latest_quotes(opportunity.symbol).get(buy_instrument.exchange)
        if quote is None:
            logger.error("live_fallback_quote_missing", symbol=opportunity.symbol)
            return None
        quote_age = (datetime.now(timezone.utc) - quote.timestamp).total_seconds()
        if quote_age < 0 or quote_age > self._config.max_quote_age_seconds:
            logger.error("live_fallback_quote_stale", symbol=opportunity.symbol, age=quote_age)
            return None
        fallback_quantity = min(open_quantity, quote.bid_quantity)
        if fallback_quantity <= 0:
            logger.error("live_fallback_bid_size_unavailable", symbol=opportunity.symbol)
            return None
        costs, net = self._estimate_pnl(
            buy_average,
            exits,
            buy_instrument.exchange,
            fallback_candidate=(fallback_quantity, quote.bid, buy_instrument.exchange),
        )
        if net < -self._config.max_fallback_loss:
            logger.error(
                "live_fallback_loss_cap_would_be_exceeded",
                symbol=opportunity.symbol,
                estimated_net_pnl=str(net),
                max_loss=str(self._config.max_fallback_loss),
                estimated_costs=str(costs),
            )
            return None
        return buy_instrument.exchange

    def _estimate_pnl(
        self,
        buy_average: Decimal,
        exits: list[tuple[int, Decimal, ExchangeName]],
        buy_exchange: ExchangeName,
        fallback_candidate: tuple[int, Decimal, ExchangeName] | None = None,
    ) -> tuple[Decimal, Decimal]:
        total_costs = Decimal("0")
        gross_profit = Decimal("0")
        all_exits = [item for item in exits if item[0] > 0]
        if fallback_candidate is not None:
            all_exits.append(fallback_candidate)
        for quantity, sell_price, sell_exchange in all_exits:
            gross_profit += (sell_price - buy_average) * quantity
            total_costs += self._costs.calculate(
                buy_average,
                sell_price,
                quantity,
                buy_exchange,
                sell_exchange,
            ).total
        return total_costs, gross_profit - total_costs

    @staticmethod
    def _weighted_sell_price(exits: list[tuple[int, Decimal, ExchangeName]]) -> Decimal | None:
        total_quantity = sum(quantity for quantity, _, _ in exits)
        if total_quantity == 0:
            return None
        total_value = sum((price * quantity for quantity, price, _ in exits), Decimal("0"))
        return total_value / total_quantity

    def _set_position(self, instrument_id: str, quantity: int, average_price: Decimal) -> None:
        if quantity == 0:
            self._risk.state.positions.pop(instrument_id, None)
        else:
            self._risk.state.positions[instrument_id] = Position(
                instrument_id=instrument_id,
                quantity=quantity,
                average_price=average_price,
            )

    def _record_order_event(
        self,
        opportunity: ArbitrageOpportunity,
        leg: str,
        order: Order,
        detail: str,
    ) -> None:
        if order.exchange is None:
            raise ValueError("Live order has no exchange")
        self._journal.record_live_order_event(
            LiveOrderEvent(
                opportunity_id=opportunity.opportunity_id,
                leg=leg,
                client_order_id=order.client_order_id,
                broker_order_id=order.broker_order_id,
                exchange=order.exchange.value,  # type: ignore[arg-type]
                side=order.transaction_type.value,
                status=order.status.value,
                quantity=order.quantity,
                filled_quantity=order.filled_quantity,
                average_price=order.average_price,
                event_at=datetime.now(timezone.utc),
                detail=detail,
            )
        )

    def _finish(
        self,
        opportunity: ArbitrageOpportunity,
        status: str,
        bought_quantity: int,
        sold_quantity: int,
        open_quantity: int,
        buy_instrument: Instrument,
        sell_instrument: Instrument,
        fallback_exchange: ExchangeName | None,
        buy_average: Decimal | None,
        sell_average: Decimal | None,
        exit_fills: list[tuple[int, Decimal, ExchangeName]],
        started_at: datetime,
        detail: str,
        estimated_costs: Decimal | None = None,
        estimated_net_pnl: Decimal | None = None,
    ) -> LiveExecutionReport:
        costs, net_pnl = (Decimal("0"), Decimal("0"))
        if buy_average is not None and exit_fills:
            costs, net_pnl = self._estimate_pnl(
                buy_average, exit_fills, buy_instrument.exchange
            )
        report = LiveExecutionReport(
            opportunity_id=opportunity.opportunity_id,
            symbol=opportunity.symbol,
            status=status,
            requested_quantity=opportunity.quantity,
            bought_quantity=bought_quantity,
            sold_quantity=sold_quantity,
            open_quantity=open_quantity,
            buy_exchange=buy_instrument.exchange,  # type: ignore[arg-type]
            intended_sell_exchange=sell_instrument.exchange,  # type: ignore[arg-type]
            fallback_exchange=fallback_exchange,
            average_buy_price=buy_average,
            average_sell_price=sell_average,
            estimated_costs=estimated_costs if estimated_costs is not None else costs,
            estimated_net_pnl=estimated_net_pnl if estimated_net_pnl is not None else net_pnl,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            detail=detail,
        )
        self._journal.record_live_execution(report)
        return report
