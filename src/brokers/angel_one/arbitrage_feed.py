"""Angel One WebSocket adapter for normalized arbitrage market quotes."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter
from src.core.entities import ExchangeName, MarketQuote
from src.infra.logging import get_logger

logger = get_logger(__name__)

_EXCHANGE_TYPE = {"NSE": 1, "BSE": 3}
_EXCHANGE_NAME = {value: key for key, value in _EXCHANGE_TYPE.items()}


class AngelOneArbitrageFeed:
    """Own Angel One login/WebSocket details; emits only validated domain quotes."""

    def __init__(
        self,
        api_key: str,
        client_id: str,
        password: str,
        totp_secret: str,
        token_map: Mapping[tuple[str, str], tuple[str, str]],
        on_quote: Callable[[MarketQuote], None],
        on_failure: Callable[[Exception], None],
        reconnect_initial_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
        broker_factory: Callable[..., Any] | None = None,
        websocket_factory: Callable[..., Any] | None = None,
        broker: AngelOneBrokerAdapter | None = None,
    ) -> None:
        self._credentials = (api_key, client_id, password, totp_secret)
        self._token_map = token_map
        self._on_quote = on_quote
        self._on_failure = on_failure
        self._initial_delay = reconnect_initial_delay
        self._max_delay = reconnect_max_delay
        self._broker_factory = broker_factory or AngelOneBrokerAdapter
        self._websocket_factory = websocket_factory
        self._provided_broker = broker
        self._owns_broker = broker is None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_websocket: Any = None
        self._broker: AngelOneBrokerAdapter | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Angel One quote feed is already running")
        self._thread = threading.Thread(
            target=self._run,
            name="angel-one-arbitrage-feed",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        websocket = self._active_websocket
        if websocket is not None:
            try:
                websocket.close_connection()
            except Exception:
                logger.exception("angel_one_websocket_close_failed")
        if self._thread is not None:
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                raise RuntimeError("Angel One quote feed did not stop within 10 seconds")

    def _run(self) -> None:
        try:
            if self._provided_broker is None:
                self._broker = self._broker_factory(*self._credentials)
                self._broker.connect()
            else:
                self._broker = self._provided_broker
            client = getattr(self._broker, "_client", None)
            if client is None:
                raise RuntimeError("Angel One broker did not initialize a client")

            auth_token = str(getattr(client, "access_token", "") or "")
            auth_token = auth_token.removeprefix("Bearer ").strip()
            feed_token = client.getfeedToken()
            if not auth_token or not feed_token:
                raise RuntimeError("Angel One login did not return auth and feed tokens")
        except Exception as exc:
            logger.exception("angel_one_feed_login_failed")
            self._on_failure(exc)
            if self._broker is not None and self._owns_broker:
                try:
                    self._broker.disconnect()
                except Exception as disconnect_error:
                    logger.exception("angel_one_broker_disconnect_failed")
                    self._on_failure(disconnect_error)
                self._broker = None
            return

        attempt = 0
        try:
            while not self._stop_event.is_set():
                try:
                    self._connect_websocket(auth_token, feed_token)
                    if not self._stop_event.is_set():
                        logger.warning("angel_one_websocket_disconnected")
                except Exception:
                    logger.exception("angel_one_websocket_session_failed")
                if self._stop_event.is_set():
                    break
                delay = min(self._initial_delay * (2**attempt), self._max_delay)
                attempt += 1
                logger.warning("angel_one_websocket_reconnecting", delay_seconds=delay)
                self._stop_event.wait(delay)
        finally:
            if self._broker is not None and self._owns_broker:
                try:
                    self._broker.disconnect()
                except Exception as exc:
                    logger.exception("angel_one_broker_disconnect_failed")
                    self._on_failure(exc)
                self._broker = None

    def _connect_websocket(self, auth_token: str, feed_token: str) -> None:
        websocket_factory = self._websocket_factory
        if websocket_factory is None:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2

            websocket_factory = SmartWebSocketV2

        api_key, client_id, _, _ = self._credentials
        websocket = websocket_factory(
            auth_token,
            api_key,
            client_id,
            feed_token,
            max_retry_attempt=3,
            retry_strategy=1,
            retry_delay=2,
            retry_multiplier=2,
        )
        self._active_websocket = websocket

        def on_open(_websocket: Any) -> None:
            tokens = [
                {
                    "exchangeType": exchange_type,
                    "tokens": [
                        token
                        for exchange, token in self._token_map
                        if exchange == _EXCHANGE_NAME[exchange_type]
                    ],
                }
                for exchange_type in _EXCHANGE_NAME
            ]
            logger.info("angel_one_websocket_subscribing", instruments=len(self._token_map))
            websocket.subscribe("arb_watch", 3, tokens)

        websocket.on_open = on_open
        websocket.on_data = self._handle_message
        websocket.on_error = lambda _ws, error: logger.warning(
            "angel_one_websocket_error", error=str(error)
        )

        def on_close(_websocket: Any) -> None:
            if self._stop_event.is_set():
                logger.info("angel_one_websocket_closed")
            else:
                logger.warning("angel_one_websocket_closed")

        websocket.on_close = on_close
        websocket.connect()

    def _handle_message(self, _websocket: Any, message: dict[str, Any]) -> None:
        try:
            exchange = _EXCHANGE_NAME.get(int(message["exchange_type"]))
            token = str(message["token"]).strip('"')
            if exchange is None or (exchange, token) not in self._token_map:
                logger.warning(
                    "angel_one_quote_unknown_instrument",
                    exchange_type=message.get("exchange_type"),
                    token=token,
                )
                return

            symbol, mapped_exchange = self._token_map[(exchange, token)]
            bids = message.get("best_5_buy_data") or []
            asks = message.get("best_5_sell_data") or []
            best_bid = max(bids, key=lambda level: int(level["price"]), default=None)
            best_ask = min(asks, key=lambda level: int(level["price"]), default=None)
            if best_bid is None or best_ask is None:
                logger.warning(
                    "angel_one_quote_missing_book_side", symbol=symbol, exchange=exchange
                )
                return

            timestamp_ms = int(message.get("exchange_timestamp", 0))
            timestamp = (
                datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                if timestamp_ms > 0
                else datetime.now(timezone.utc)
            )
            quote = MarketQuote(
                symbol=symbol,
                exchange=mapped_exchange,  # type: ignore[arg-type]
                bid=Decimal(str(best_bid["price"])) / Decimal(100),
                bid_quantity=int(best_bid.get("quantity", 0)),
                ask=Decimal(str(best_ask["price"])) / Decimal(100),
                ask_quantity=int(best_ask.get("quantity", 0)),
                timestamp=timestamp,
                raw_payload=dict(message),
            )
            if (
                quote.bid <= 0
                or quote.ask <= 0
                or quote.bid_quantity < 0
                or quote.ask_quantity < 0
            ):
                logger.warning(
                    "angel_one_quote_failed_validation", symbol=symbol, exchange=exchange
                )
                return
        except (KeyError, TypeError, ValueError, ArithmeticError):
            logger.exception("angel_one_quote_parse_failed", message=message)
            return

        try:
            self._on_quote(quote)
        except Exception as exc:
            logger.exception("arbitrage_quote_publish_failed", symbol=quote.symbol)
            self._on_failure(exc)