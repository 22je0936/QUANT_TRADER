"""Order placement and lookup endpoints. All orders pass through RiskManager
before reaching the broker — no bypass path.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_broker_gateway, get_risk_manager
from src.api.schemas import OrderResponse, PlaceOrderRequest
from src.core.entities import Order
from src.core.exceptions import OrderRejectedError, RiskLimitBreachedError
from src.core.interfaces import IBrokerGateway
from src.risk.risk_manager import RiskManager

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=201)
def place_order(
    request: PlaceOrderRequest,
    broker: IBrokerGateway = Depends(get_broker_gateway),
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> OrderResponse:
    order = Order(
        instrument_id=request.instrument_id,
        transaction_type=request.transaction_type,
        order_type=request.order_type,
        product_type=request.product_type,
        quantity=request.quantity,
        price=request.price,
        trigger_price=request.trigger_price,
        strategy_id=request.strategy_id,
    )

    try:
        risk_manager.validate_order(order)
    except RiskLimitBreachedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        filled_order = broker.place_order(order)
    except OrderRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return OrderResponse(
        client_order_id=filled_order.client_order_id,
        broker_order_id=filled_order.broker_order_id,
        instrument_id=filled_order.instrument_id,
        status=filled_order.status,
        filled_quantity=filled_order.filled_quantity,
        average_price=filled_order.average_price,
    )


@router.get("/{client_order_id}", response_model=OrderResponse)
def get_order(
    client_order_id: str, broker: IBrokerGateway = Depends(get_broker_gateway)
) -> OrderResponse:
    order = broker.get_order_status(client_order_id)
    return OrderResponse(
        client_order_id=order.client_order_id,
        broker_order_id=order.broker_order_id,
        instrument_id=order.instrument_id,
        status=order.status,
        filled_quantity=order.filled_quantity,
        average_price=order.average_price,
    )
