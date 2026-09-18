"""SQLAlchemy-backed implementation of IOrderRepository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.entities import (
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
)
from src.core.interfaces import IOrderRepository
from src.repositories.postgres.models import OrderModel


def _to_entity(model: OrderModel) -> Order:
    return Order(
        instrument_id=model.instrument_id,
        transaction_type=TransactionType(model.transaction_type),
        order_type=OrderType(model.order_type),
        product_type=ProductType(model.product_type),
        quantity=model.quantity,
        price=model.price,
        trigger_price=model.trigger_price,
        strategy_id=model.strategy_id,
        client_order_id=model.client_order_id,
        broker_order_id=model.broker_order_id,
        status=OrderStatus(model.status),
        filled_quantity=model.filled_quantity,
        average_price=model.average_price,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class PostgresOrderRepository(IOrderRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, order: Order) -> None:
        model = self._session.get(OrderModel, order.client_order_id)
        if model is None:
            model = OrderModel(client_order_id=order.client_order_id)
            self._session.add(model)

        model.broker_order_id = order.broker_order_id
        model.instrument_id = order.instrument_id
        model.transaction_type = order.transaction_type.value
        model.order_type = order.order_type.value
        model.product_type = order.product_type.value
        model.quantity = order.quantity
        model.price = order.price
        model.trigger_price = order.trigger_price
        model.status = order.status.value
        model.filled_quantity = order.filled_quantity
        model.average_price = order.average_price
        model.strategy_id = order.strategy_id
        model.updated_at = order.updated_at

    def get_by_client_order_id(self, client_order_id: str) -> Order | None:
        model = self._session.get(OrderModel, client_order_id)
        return _to_entity(model) if model else None

    def list_by_strategy(self, strategy_id: str) -> list[Order]:
        stmt = select(OrderModel).where(OrderModel.strategy_id == strategy_id)
        return [_to_entity(m) for m in self._session.scalars(stmt)]
