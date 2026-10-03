"""Structured values shared by broker-neutral arbitrage components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from src.core.entities import ExchangeName, MarketQuote


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    brokerage: Decimal
    transaction_charges: Decimal
    stt: Decimal
    stamp_duty: Decimal
    sebi_charges: Decimal
    gst: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.brokerage
            + self.transaction_charges
            + self.stt
            + self.stamp_duty
            + self.sebi_charges
            + self.gst
        )


@dataclass(frozen=True, slots=True)
class ArbitrageOpportunity:
    opportunity_id: str
    symbol: str
    detected_at: datetime
    buy_exchange: ExchangeName
    sell_exchange: ExchangeName
    buy_price: Decimal
    sell_price: Decimal
    quantity: int
    gross_profit: Decimal
    costs: CostBreakdown
    estimated_net_profit: Decimal
    buy_quote_timestamp: datetime
    sell_quote_timestamp: datetime

    @classmethod
    def create(cls, **values: object) -> ArbitrageOpportunity:
        return cls(opportunity_id=str(uuid4()), **values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class LiveOrderEvent:
    opportunity_id: str
    leg: str
    client_order_id: str
    broker_order_id: str | None
    exchange: ExchangeName
    side: str
    status: str
    quantity: int
    filled_quantity: int
    average_price: Decimal | None
    event_at: datetime
    detail: str = ""


@dataclass(frozen=True, slots=True)
class LiveExecutionReport:
    opportunity_id: str
    symbol: str
    status: str
    requested_quantity: int
    bought_quantity: int
    sold_quantity: int
    open_quantity: int
    buy_exchange: ExchangeName
    intended_sell_exchange: ExchangeName
    fallback_exchange: ExchangeName | None
    average_buy_price: Decimal | None
    average_sell_price: Decimal | None
    estimated_costs: Decimal
    estimated_net_pnl: Decimal
    started_at: datetime
    completed_at: datetime
    detail: str = ""