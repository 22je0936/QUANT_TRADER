"""Orchestrates: signal generation -> risk validation -> order execution.
Every dependency is injected via the constructor (no hidden globals), so the
exact same code runs in backtest, paper, and live modes — only the injected
IBrokerGateway implementation changes.
"""
from __future__ import annotations

from decimal import Decimal

from src.core.entities import Order, OrderType, ProductType, SignalAction, TransactionType
from src.core.exceptions import OrderRejectedError, RiskLimitBreachedError
from src.core.interfaces import IBrokerGateway, ISignalGenerator
from src.infra.logging import get_logger
from src.risk.risk_manager import RiskManager

logger = get_logger(__name__)

_ACTION_TO_TRANSACTION = {
    SignalAction.BUY: TransactionType.BUY,
    SignalAction.SELL: TransactionType.SELL,
}


class StrategyRunner:
    def __init__(
        self,
        strategy: ISignalGenerator,
        broker: IBrokerGateway,
        risk_manager: RiskManager,
        default_quantity: int = 1,
    ) -> None:
        self._strategy = strategy
        self._broker = broker
        self._risk_manager = risk_manager
        self._default_quantity = default_quantity

    def run_once(self, instrument_id: str) -> Order | None:
        signal = self._strategy.generate(instrument_id)
        if signal is None or signal.action not in _ACTION_TO_TRANSACTION:
            return None

        order = Order(
            instrument_id=signal.instrument_id,
            transaction_type=_ACTION_TO_TRANSACTION[signal.action],
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            quantity=signal.quantity or self._default_quantity,
            strategy_id=signal.strategy_id,
        )

        try:
            self._risk_manager.validate_order(order)
        except RiskLimitBreachedError:
            logger.warning("order_blocked_by_risk", instrument_id=instrument_id, strategy_id=signal.strategy_id)
            raise

        try:
            filled_order = self._broker.place_order(order)
        except OrderRejectedError:
            logger.error("order_rejected_by_broker", instrument_id=instrument_id)
            raise

        logger.info(
            "order_placed",
            client_order_id=filled_order.client_order_id,
            instrument_id=instrument_id,
            status=filled_order.status,
        )
        return filled_order
