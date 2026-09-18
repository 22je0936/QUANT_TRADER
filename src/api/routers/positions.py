"""Read-only positions endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_broker_gateway
from src.api.schemas import PositionResponse
from src.core.interfaces import IBrokerGateway

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionResponse])
def list_positions(broker: IBrokerGateway = Depends(get_broker_gateway)) -> list[PositionResponse]:
    return [
        PositionResponse(
            instrument_id=p.instrument_id,
            quantity=p.quantity,
            average_price=p.average_price,
            realized_pnl=p.realized_pnl,
            unrealized_pnl=p.unrealized_pnl,
        )
        for p in broker.get_positions()
    ]
