"""Ports (interfaces). Core/service/strategy code depends only on these — never on
concrete broker SDKs or database drivers. Every adapter/repository implements one
of these ABCs. Angel One is the live broker; backtesting uses a separate local fill model.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Protocol

from src.core.entities import (
    Instrument,
    Order,
    Position,
    Signal,
    Tick,
    Trade,
)

TickCallback = Callable[[Tick], None]


class IBrokerGateway(ABC):
    """Order execution & account operations. One implementation per broker."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Submit an order to the broker and return it updated with broker_order_id/status."""

    @abstractmethod
    def modify_order(self, client_order_id: str, **changes: object) -> Order: ...

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> Order: ...

    @abstractmethod
    def get_order_status(self, client_order_id: str) -> Order: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_holdings(self) -> list[Position]: ...

    @abstractmethod
    def get_margins(self) -> dict: ...


class IMarketDataFeed(ABC):
    """Real-time tick streaming. One implementation per broker."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def subscribe(self, instrument_ids: list[str]) -> None: ...

    @abstractmethod
    def unsubscribe(self, instrument_ids: list[str]) -> None: ...

    @abstractmethod
    def on_tick(self, callback: TickCallback) -> None:
        """Register a callback invoked for every incoming tick."""


class IOrderRepository(ABC):
    @abstractmethod
    def save(self, order: Order) -> None: ...

    @abstractmethod
    def get_by_client_order_id(self, client_order_id: str) -> Order | None: ...

    @abstractmethod
    def list_by_strategy(self, strategy_id: str) -> list[Order]: ...


class ITradeRepository(ABC):
    @abstractmethod
    def save(self, trade: Trade) -> None: ...

    @abstractmethod
    def list_by_strategy(self, strategy_id: str) -> list[Trade]: ...


class IInstrumentRepository(ABC):
    @abstractmethod
    def get_by_instrument_id(self, instrument_id: str) -> Instrument | None: ...

    @abstractmethod
    def get_by_broker_token(self, broker_name: str, token: str) -> Instrument | None: ...

    @abstractmethod
    def upsert(self, instrument: Instrument) -> None: ...


class ISignalGenerator(Protocol):
    """Strategies implement this. MUST NOT import anything from src.brokers."""

    strategy_id: str

    def generate(self, instrument_id: str) -> Signal | None: ...


class IRiskChecker(Protocol):
    def validate_order(self, order: Order) -> None:
        """Raise RiskLimitBreachedError if the order violates a risk rule."""
