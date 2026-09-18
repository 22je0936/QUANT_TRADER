"""SQLAlchemy-backed implementation of ITradeRepository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.entities import Trade, TransactionType
from src.core.interfaces import ITradeRepository
from src.repositories.postgres.models import TradeModel


def _to_entity(model: TradeModel) -> Trade:
    return Trade(
        trade_id=model.trade_id,
        order_client_id=model.order_client_id,
        instrument_id=model.instrument_id,
        transaction_type=TransactionType(model.transaction_type),
        quantity=model.quantity,
        price=model.price,
        strategy_id=model.strategy_id,
        executed_at=model.executed_at,
    )


class PostgresTradeRepository(ITradeRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, trade: Trade) -> None:
        model = TradeModel(
            trade_id=trade.trade_id,
            order_client_id=trade.order_client_id,
            instrument_id=trade.instrument_id,
            transaction_type=trade.transaction_type.value,
            quantity=trade.quantity,
            price=trade.price,
            strategy_id=trade.strategy_id,
            executed_at=trade.executed_at,
        )
        self._session.add(model)

    def list_by_strategy(self, strategy_id: str) -> list[Trade]:
        stmt = select(TradeModel).where(TradeModel.strategy_id == strategy_id)
        return [_to_entity(m) for m in self._session.scalars(stmt)]
