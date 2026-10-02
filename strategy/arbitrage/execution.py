"""Angel One authentication and order execution for the watcher."""

from __future__ import annotations

from typing import Any

from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter
from src.core.arbitrage_config import Config

from .instruments import Instrument


class AngelOneOrderExecutor:
    """Isolate SmartAPI session handling and exchange-specific order payloads."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._broker: AngelOneBrokerAdapter | None = None
        self._client: Any = None

    def connect(self, settings: Any) -> tuple[str, str]:
        self._broker = AngelOneBrokerAdapter(
            settings.angel_one_api_key,
            settings.angel_one_client_id,
            settings.angel_one_password,
            settings.angel_one_totp_secret,
        )
        self._broker.connect()
        self._client = getattr(self._broker, "_client", None)
        if self._client is None:
            raise RuntimeError("Angel One broker did not initialize a client")

        auth_token = str(getattr(self._client, "access_token", "") or "")
        auth_token = auth_token.removeprefix("Bearer ").strip()
        feed_token = self._client.getfeedToken()
        if not auth_token or not feed_token:
            raise RuntimeError("Missing auth/feed token after login")
        return auth_token, feed_token

    def place_order(
        self, instrument: Instrument, side: str, price: float, quantity: int
    ) -> None:
        if self._client is None:
            raise RuntimeError("Not logged in. Call connect() first.")

        params = {
            "variety": "NORMAL",
            "tradingsymbol": instrument.symbol,
            "symboltoken": instrument.token,
            "transactiontype": side,
            "exchange": instrument.exchange,
            "ordertype": "LIMIT",
            "producttype": self._config.product_type,
            "duration": "DAY",
            "price": f"{price:.2f}",
            "quantity": str(quantity),
        }
        try:
            response = self._client.placeOrderFullResponse(params)
            print(
                f"   order {side} {instrument.name} {instrument.exchange} "
                f"@ {price:.2f}: {response}"
            )
        except Exception as exc:  # pragma: no cover - network / broker call
            print(f"   order FAILED {side} {instrument.name} {instrument.exchange}: {exc}")

    def disconnect(self) -> None:
        if self._broker is not None:
            self._broker.disconnect()
            self._broker = None
            self._client = None