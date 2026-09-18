"""Pydantic request/response schemas for the API layer."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from src.core.entities import OrderStatus, OrderType, ProductType, TransactionType


class PlaceOrderRequest(BaseModel):
    instrument_id: str
    transaction_type: TransactionType
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    quantity: int = Field(gt=0)
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    strategy_id: str | None = None


class OrderResponse(BaseModel):
    client_order_id: str
    broker_order_id: str | None
    instrument_id: str
    status: OrderStatus
    filled_quantity: int
    average_price: Decimal | None


class PositionResponse(BaseModel):
    instrument_id: str
    quantity: int
    average_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


class HealthResponse(BaseModel):
    status: str
    broker_provider: str
