"""Angel One SmartAPI adapter. Implements IBrokerGateway + IMarketDataFeed so
strategy/service/risk code never depends on SmartAPI directly.

Requires the `smartapi-python` package (pip install smartapi-python pyotp) at
runtime; imported lazily so the rest of the app works without it installed
(e.g. when running only with the paper broker).
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import certifi

from src.core.entities import Order, OrderStatus, OrderType, Position, TransactionType
from src.core.exceptions import (
    BrokerAuthenticationError,
    BrokerConnectionError,
    OrderRejectedError,
)
from src.core.interfaces import IBrokerGateway, IMarketDataFeed, TickCallback
from src.infra.logging import get_logger

logger = get_logger(__name__)


def configure_requests_ssl() -> str:
    """Ensure the SmartAPI SDK validates HTTPS against the certifi CA bundle."""
    ca_file = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = ca_file
    os.environ["SSL_CERT_FILE"] = ca_file
    return ca_file


def should_disable_ssl_verification() -> bool:
    value = os.getenv("ANGELONE_DISABLE_SSL_VERIFY", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


_ORDER_TYPE_MAP = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.SL: "STOPLOSS_LIMIT",
    OrderType.SL_M: "STOPLOSS_MARKET",
}
_TRANSACTION_TYPE_MAP = {
    TransactionType.BUY: "BUY",
    TransactionType.SELL: "SELL",
}


class AngelOneBrokerAdapter(IBrokerGateway):
    """Order execution & account operations via Angel One SmartAPI."""

    def __init__(self, api_key: str, client_id: str, password: str, totp_secret: str) -> None:
        self._api_key = api_key
        self._client_id = client_id
        self._password = password
        self._totp_secret = totp_secret
        self._client: Any = None

    def connect(self) -> None:
        try:
            configure_requests_ssl()
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as exc:  # pragma: no cover - depends on optional dependency
            raise BrokerConnectionError(
                "smartapi-python/pyotp not installed. Run: pip install smartapi-python pyotp"
            ) from exc

        try:
            self._client = SmartConnect(api_key=self._api_key)
            totp = pyotp.TOTP(self._totp_secret).now()
            session = self._client.generateSession(self._client_id, self._password, totp)
            if not session.get("status"):
                raise BrokerAuthenticationError(session.get("message", "Angel One login failed"))
            logger.info("angel_one_connected", client_id=self._client_id)
        except BrokerAuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001 - translate all SDK errors to our domain error
            if "CERTIFICATE_VERIFY_FAILED" in str(exc) and should_disable_ssl_verification():
                logger.warning("angel_one_ssl_verification_failed_retrying_without_verification")
                self._client = SmartConnect(api_key=self._api_key, disable_ssl=True)
                try:
                    totp = pyotp.TOTP(self._totp_secret).now()
                    session = self._client.generateSession(self._client_id, self._password, totp)
                    if not session.get("status"):
                        raise BrokerAuthenticationError(session.get("message", "Angel One login failed"))
                    logger.info("angel_one_connected", client_id=self._client_id)
                    return
                except BrokerAuthenticationError:
                    raise
                except Exception as retry_exc:  # noqa: BLE001
                    raise BrokerConnectionError(str(retry_exc)) from retry_exc
            raise BrokerConnectionError(str(exc)) from exc

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.terminateSession(self._client_id)
            self._client = None

    def place_order(self, order: Order) -> Order:
        self._require_connected()
        params = {
            "variety": "NORMAL",
            "tradingsymbol": order.instrument_id,
            "symboltoken": order.instrument_id,
            "transactiontype": _TRANSACTION_TYPE_MAP[order.transaction_type],
            "exchange": "NSE",
            "ordertype": _ORDER_TYPE_MAP[order.order_type],
            "producttype": order.product_type.value,
            "duration": "DAY",
            "quantity": order.quantity,
        }
        if order.price is not None:
            params["price"] = str(order.price)
        if order.trigger_price is not None:
            params["triggerprice"] = str(order.trigger_price)

        try:
            response = self._client.placeOrder(params)
        except Exception as exc:  # noqa: BLE001
            raise OrderRejectedError(str(exc)) from exc

        order.broker_order_id = str(response)
        order.status = OrderStatus.OPEN
        return order

    def modify_order(self, client_order_id: str, **changes: object) -> Order:
        self._require_connected()
        raise NotImplementedError("Wire up SmartConnect.modifyOrder with broker_order_id lookup")

    def cancel_order(self, client_order_id: str) -> Order:
        self._require_connected()
        raise NotImplementedError("Wire up SmartConnect.cancelOrder with broker_order_id lookup")

    def get_order_status(self, client_order_id: str) -> Order:
        self._require_connected()
        raise NotImplementedError("Wire up SmartConnect.orderBook lookup by client_order_id")

    def get_positions(self) -> list[Position]:
        self._require_connected()
        raw = self._client.position() or {}
        positions = []
        for item in raw.get("data") or []:
            positions.append(
                Position(
                    instrument_id=item["tradingsymbol"],
                    quantity=int(item["netqty"]),
                    average_price=Decimal(str(item.get("avgnetprice", "0"))),
                )
            )
        return positions

    def get_holdings(self) -> list[Position]:
        self._require_connected()
        raw = self._client.holding() or {}
        return [
            Position(
                instrument_id=item["tradingsymbol"],
                quantity=int(item["quantity"]),
                average_price=Decimal(str(item.get("averageprice", "0"))),
            )
            for item in raw.get("data") or []
        ]

    def get_margins(self) -> dict:
        self._require_connected()
        return self._client.rmsLimit() or {}

    def _require_connected(self) -> None:
        if self._client is None:
            raise BrokerConnectionError("AngelOneBrokerAdapter is not connected. Call connect() first.")


class AngelOneMarketDataFeed(IMarketDataFeed):
    """Tick streaming via Angel One SmartAPI WebSocket (SmartWebSocketV2)."""

    def __init__(self, api_key: str, client_id: str, feed_token: str) -> None:
        self._api_key = api_key
        self._client_id = client_id
        self._feed_token = feed_token
        self._ws: Any = None
        self._callbacks: list[TickCallback] = []
        self._subscribed: list[str] = []

    def connect(self) -> None:
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        except ImportError as exc:  # pragma: no cover
            raise BrokerConnectionError("smartapi-python not installed") from exc

        self._ws = SmartWebSocketV2(self._feed_token, self._api_key, self._client_id, self._feed_token)
        self._ws.on_data = self._handle_message
        self._ws.connect()

    def disconnect(self) -> None:
        if self._ws is not None:
            self._ws.close_connection()
            self._ws = None

    def subscribe(self, instrument_ids: list[str]) -> None:
        self._subscribed.extend(instrument_ids)
        if self._ws is not None:
            self._ws.subscribe("quant_trader", 1, instrument_ids)

    def unsubscribe(self, instrument_ids: list[str]) -> None:
        for instrument_id in instrument_ids:
            if instrument_id in self._subscribed:
                self._subscribed.remove(instrument_id)
        if self._ws is not None:
            self._ws.unsubscribe("quant_trader", 1, instrument_ids)

    def on_tick(self, callback: TickCallback) -> None:
        self._callbacks.append(callback)

    def _handle_message(self, wsapp: Any, message: dict) -> None:  # noqa: ANN001
        """Translate raw SmartAPI tick payload into a domain Tick and fan out to callbacks."""
        from datetime import datetime

        from src.core.entities import Tick

        tick = Tick(
            instrument_id=str(message.get("token", "")),
            ltp=Decimal(str(message.get("last_traded_price", 0))) / Decimal(100),
            volume=int(message.get("volume_trade_for_the_day", 0)),
            bid=None,
            ask=None,
            timestamp=datetime.utcnow(),
        )
        for callback in self._callbacks:
            callback(tick)
