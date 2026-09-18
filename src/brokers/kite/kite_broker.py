"""Zerodha Kite Connect adapter — implements the same IBrokerGateway /
IMarketDataFeed interfaces as Angel One. Must pass tests/contract/ unmodified
before BROKER_PROVIDER=kite is enabled in any environment.

Requires `kiteconnect` (pip install kiteconnect) at runtime; imported lazily.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.core.entities import Order, OrderStatus, OrderType, Position, TransactionType
from src.core.exceptions import BrokerConnectionError, OrderRejectedError
from src.core.interfaces import IBrokerGateway, IMarketDataFeed, TickCallback
from src.infra.logging import get_logger

logger = get_logger(__name__)

_ORDER_TYPE_MAP = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.SL: "SL",
    OrderType.SL_M: "SL-M",
}
_TRANSACTION_TYPE_MAP = {
    TransactionType.BUY: "BUY",
    TransactionType.SELL: "SELL",
}


class KiteBrokerAdapter(IBrokerGateway):
    def __init__(self, api_key: str, api_secret: str, access_token: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._access_token = access_token
        self._client: Any = None

    def connect(self) -> None:
        try:
            from kiteconnect import KiteConnect
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise BrokerConnectionError("kiteconnect not installed. Run: pip install kiteconnect") from exc

        self._client = KiteConnect(api_key=self._api_key)
        self._client.set_access_token(self._access_token)
        logger.info("kite_connected")

    def disconnect(self) -> None:
        self._client = None

    def place_order(self, order: Order) -> Order:
        self._require_connected()
        try:
            broker_order_id = self._client.place_order(
                variety="regular",
                exchange="NSE",
                tradingsymbol=order.instrument_id,
                transaction_type=_TRANSACTION_TYPE_MAP[order.transaction_type],
                quantity=order.quantity,
                order_type=_ORDER_TYPE_MAP[order.order_type],
                product=order.product_type.value,
                price=float(order.price) if order.price is not None else None,
                trigger_price=float(order.trigger_price) if order.trigger_price is not None else None,
                tag=order.client_order_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise OrderRejectedError(str(exc)) from exc

        order.broker_order_id = str(broker_order_id)
        order.status = OrderStatus.OPEN
        return order

    def modify_order(self, client_order_id: str, **changes: object) -> Order:
        self._require_connected()
        raise NotImplementedError("Wire up KiteConnect.modify_order with broker_order_id lookup")

    def cancel_order(self, client_order_id: str) -> Order:
        self._require_connected()
        raise NotImplementedError("Wire up KiteConnect.cancel_order with broker_order_id lookup")

    def get_order_status(self, client_order_id: str) -> Order:
        self._require_connected()
        raise NotImplementedError("Wire up KiteConnect.order_history lookup by tag")

    def get_positions(self) -> list[Position]:
        self._require_connected()
        raw = self._client.positions() or {}
        return [
            Position(
                instrument_id=item["tradingsymbol"],
                quantity=int(item["quantity"]),
                average_price=Decimal(str(item.get("average_price", "0"))),
            )
            for item in raw.get("net", [])
        ]

    def get_holdings(self) -> list[Position]:
        self._require_connected()
        raw = self._client.holdings() or []
        return [
            Position(
                instrument_id=item["tradingsymbol"],
                quantity=int(item["quantity"]),
                average_price=Decimal(str(item.get("average_price", "0"))),
            )
            for item in raw
        ]

    def get_margins(self) -> dict:
        self._require_connected()
        return self._client.margins() or {}

    def _require_connected(self) -> None:
        if self._client is None:
            raise BrokerConnectionError("KiteBrokerAdapter is not connected. Call connect() first.")


class KiteMarketDataFeed(IMarketDataFeed):
    """Tick streaming via Kite Connect WebSocket ticker (KiteTicker)."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self._api_key = api_key
        self._access_token = access_token
        self._ticker: Any = None
        self._callbacks: list[TickCallback] = []

    def connect(self) -> None:
        try:
            from kiteconnect import KiteTicker
        except ImportError as exc:  # pragma: no cover
            raise BrokerConnectionError("kiteconnect not installed") from exc

        self._ticker = KiteTicker(self._api_key, self._access_token)
        self._ticker.on_ticks = self._handle_ticks
        self._ticker.connect(threaded=True)

    def disconnect(self) -> None:
        if self._ticker is not None:
            self._ticker.close()
            self._ticker = None

    def subscribe(self, instrument_ids: list[str]) -> None:
        if self._ticker is not None:
            self._ticker.subscribe([int(i) for i in instrument_ids])

    def unsubscribe(self, instrument_ids: list[str]) -> None:
        if self._ticker is not None:
            self._ticker.unsubscribe([int(i) for i in instrument_ids])

    def on_tick(self, callback: TickCallback) -> None:
        self._callbacks.append(callback)

    def _handle_ticks(self, ws: Any, ticks: list[dict]) -> None:  # noqa: ANN001
        from datetime import datetime

        from src.core.entities import Tick

        for raw in ticks:
            tick = Tick(
                instrument_id=str(raw["instrument_token"]),
                ltp=Decimal(str(raw.get("last_price", 0))),
                volume=int(raw.get("volume_traded", 0)),
                bid=None,
                ask=None,
                timestamp=raw.get("exchange_timestamp") or datetime.utcnow(),
            )
            for callback in self._callbacks:
                callback(tick)
