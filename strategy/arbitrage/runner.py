"""WebSocket lifecycle and wiring for the arbitrage watcher."""

from __future__ import annotations

import time
from typing import Any

from src.config.settings import get_settings
from src.core.arbitrage_config import EXCHANGES, EXCH_TYPE, Config

from .execution import AngelOneOrderExecutor
from .instruments import InstrumentCatalog, load_instruments
from .signals import ArbitrageSignal, ArbitrageSignalEngine, parse_quote


class ArbitrageWatcher:
    """Connect market data to the signal engine and optional order executor."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.catalog: InstrumentCatalog | None = None
        self.signal_engine = ArbitrageSignalEngine(self.config)
        self.order_executor = AngelOneOrderExecutor(self.config)
        self.websocket: Any = None

    def on_data(self, _websocket: Any, message: dict[str, Any]) -> None:
        if self.catalog is None:
            return

        token = str(message.get("token", "")).strip('"')
        exchange_type = message.get("exchange_type")
        if exchange_type is None:
            return
        instrument_key = self.catalog.by_token.get((int(exchange_type), token))
        if instrument_key is None:
            return

        name, exchange = instrument_key
        quote = parse_quote(message)
        if quote is None:
            return
        signal = self.signal_engine.update_quote(name, exchange, quote)
        if signal is not None:
            self._handle_signal(signal)

    def _handle_signal(self, signal: ArbitrageSignal) -> None:
        print(
            f"\n*** ARBITRAGE {signal.name} ***\n"
            f"   BUY  on {signal.buy_exchange} @ {signal.buy_price:.2f}\n"
            f"   SELL on {signal.sell_exchange} @ {signal.sell_price:.2f}\n"
            f"   spread {signal.spread:.2f} ({signal.spread_pct:.3f}%)  "
            f"available qty {signal.quantity if signal.quantity is not None else 'n/a'}"
        )
        if not self.config.place_orders:
            return

        quantity = self.config.order_qty
        if signal.quantity is not None:
            quantity = min(quantity, signal.quantity)
        instruments = self.catalog.by_name[signal.name]
        self.order_executor.place_order(
            instruments[signal.buy_exchange], "BUY", signal.buy_price, quantity
        )
        self.order_executor.place_order(
            instruments[signal.sell_exchange], "SELL", signal.sell_price, quantity
        )

    def run(self) -> None:
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        self.catalog = load_instruments(self.config.scrip_file, self.config.watchlist)
        for name in self.catalog.missing_names:
            print(f"[skip] {name}: missing NSE or BSE scrip")
        for name, instruments in self.catalog.by_name.items():
            nse, bse = instruments["NSE"], instruments["BSE"]
            print(f"[ok] {name}: NSE {nse.symbol}/{nse.token}  BSE {bse.symbol}/{bse.token}")
        if not self.catalog.by_name:
            raise SystemExit("No stocks found on both NSE and BSE.")

        settings = get_settings()
        auth_token, feed_token = self.order_executor.connect(settings)
        self.websocket = SmartWebSocketV2(
            auth_token,
            settings.angel_one_api_key,
            settings.angel_one_client_id,
            feed_token,
            max_retry_attempt=5,
        )
        token_list = [
            {
                "exchangeType": EXCH_TYPE[exchange],
                "tokens": [
                    instruments[exchange].token for instruments in self.catalog.by_name.values()
                ],
            }
            for exchange in EXCHANGES
        ]

        def on_open(_websocket: Any) -> None:
            print("WebSocket connected. Subscribing...")
            self.websocket.subscribe("arb_watch", 3, token_list)

        self.websocket.on_open = on_open
        self.websocket.on_data = self.on_data
        self.websocket.on_error = lambda _ws, error: print("WS error:", error)
        self.websocket.on_close = lambda _ws: print("WS closed")

        print(f"Watching {len(self.catalog.by_name)} stocks on NSE + BSE. Ctrl+C to stop.")
        try:
            self.websocket.connect()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            self.order_executor.disconnect()


def main() -> None:
    ArbitrageWatcher().run()