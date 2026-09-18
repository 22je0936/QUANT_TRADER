"""Broker-agnostic domain entities. No framework or broker imports allowed here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    MCX = "MCX"


class InstrumentType(str, Enum):
    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION_CE = "OPTION_CE"
    OPTION_PE = "OPTION_PE"
    INDEX = "INDEX"


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL_M"


class ProductType(str, Enum):
    INTRADAY = "INTRADAY"
    DELIVERY = "DELIVERY"
    MARGIN = "MARGIN"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class Instrument:
    """Canonical internal instrument identity, independent of any broker's symbology."""

    instrument_id: str  # canonical internal ID, e.g. "NSE:RELIANCE"
    trading_symbol: str
    exchange: Exchange
    instrument_type: InstrumentType
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    expiry: datetime | None = None
    strike: Decimal | None = None
    broker_tokens: dict[str, str] = field(default_factory=dict)  # broker_name -> broker_token


@dataclass(frozen=True, slots=True)
class Tick:
    instrument_id: str
    ltp: Decimal
    volume: int
    bid: Decimal | None
    ask: Decimal | None
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class Candle:
    instrument_id: str
    timeframe: str  # "1m", "5m", "15m", "1d"
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timestamp: datetime


@dataclass(slots=True)
class Order:
    instrument_id: str
    transaction_type: TransactionType
    order_type: OrderType
    product_type: ProductType
    quantity: int
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    strategy_id: str | None = None
    client_order_id: str = field(default_factory=lambda: str(uuid4()))
    broker_order_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    average_price: Decimal | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Trade:
    trade_id: UUID = field(default_factory=uuid4)
    order_client_id: str = ""
    instrument_id: str = ""
    transaction_type: TransactionType = TransactionType.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    strategy_id: str | None = None
    executed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Position:
    instrument_id: str
    quantity: int  # signed: positive = long, negative = short
    average_price: Decimal
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    strategy_id: str | None = None


@dataclass(frozen=True, slots=True)
class Signal:
    instrument_id: str
    action: SignalAction
    strategy_id: str
    confidence: float = 1.0
    quantity: int | None = None
    price_hint: Decimal | None = None
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)
