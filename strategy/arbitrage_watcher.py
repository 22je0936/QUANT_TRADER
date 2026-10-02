"""
NSE <-> BSE arbitrage watcher using Angel One SmartWebSocketV2.

Watches the same stocks on NSE and BSE at once. When the best BID on one
exchange is higher than the best ASK on the other (by more than your cost
threshold), it prints a BUY / SELL signal. Orders are only placed if
PLACE_ORDERS = True.

Save as: strategy/arbitrage_watcher.py
Needs: data/share_response.json and Angel One credentials in your settings.
"""


from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# project root = parent of the "strategy" folder
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from SmartApi.smartWebSocketV2 import SmartWebSocketV2  # noqa: E402

from src.brokers.angel_one.angel_one_broker import AngelOneBrokerAdapter  # noqa: E402
from src.config.settings import get_settings  # noqa: E402

# ---------------- CONFIG ----------------
WATCHLIST = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "SBIN", "ITC", "LT", "AXISBANK", "KOTAKBANK",
]
SCRIP_FILE = ROOT / "data" / "share_response.json"

MIN_SPREAD_PCT = 0.20   # must exceed your total costs (brokerage, STT, charges)
MIN_QTY = 1             # min quantity at best bid/ask (only checked if the Tick has quantities)
MAX_QUOTE_AGE = 2.0     # seconds; ignore if the two exchange quotes are further apart
COOLDOWN_SEC = 5        # per stock, to avoid repeated signals

PLACE_ORDERS = False    # keep False until you've paper-tested
ORDER_QTY = 1
PRODUCT_TYPE = "INTRADAY"

# ---------------- STATE ----------------
EXCH_TYPE = {"NSE": 1, "BSE": 3}

instruments: dict[str, dict[str, dict[str, Any]]] = {}   # name -> {"NSE": row, "BSE": row}
token_map: dict[tuple[int, str], tuple[str, str]] = {}   # (exchange_type, token) -> (name, exch)
quotes: dict[str, dict[str, dict[str, Any]]] = {}        # name -> {"NSE": {...}, "BSE": {...}}
last_signal: dict[str, float] = {}
broker: AngelOneBrokerAdapter | None = None
client: Any = None                                       # SmartConnect inside the adapter


def build_instruments() -> None:
    """Map each watchlist stock to its NSE and BSE rows from the scrip master."""
    if not SCRIP_FILE.exists():
        raise FileNotFoundError(f"Missing scrip master file: {SCRIP_FILE}")

    instruments.clear()
    quotes.clear()
    token_map.clear()

    with open(SCRIP_FILE, encoding="utf-8") as f:
        rows = json.load(f)

    by_exch: dict[str, dict[str, dict[str, Any]]] = {"NSE": {}, "BSE": {}}
    for row in rows:
        exchange = row.get("exch_seg")
        if exchange in by_exch:
            by_exch[exchange].setdefault(str(row.get("name", "")).upper(), row)

    for name in WATCHLIST:
        nse_row, bse_row = by_exch["NSE"].get(name), by_exch["BSE"].get(name)
        if not nse_row or not bse_row:
            print(f"[skip] {name}: NSE={bool(nse_row)} BSE={bool(bse_row)}")
            continue

        instruments[name] = {"NSE": nse_row, "BSE": bse_row}
        quotes[name] = {}
        for exch, row in (("NSE", nse_row), ("BSE", bse_row)):
            token_map[(EXCH_TYPE[exch], str(row["token"]))] = (name, exch)

        print(f"[ok] {name}: NSE {nse_row['symbol']}/{nse_row['token']}  "
              f"BSE {bse_row['symbol']}/{bse_row['token']}")


def login() -> tuple[str, str]:
    """Log in via the broker adapter; return (auth_token, feed_token) for the websocket."""
    global broker, client

    s = get_settings()
    broker = AngelOneBrokerAdapter(
        s.angel_one_api_key,
        s.angel_one_client_id,
        s.angel_one_password,
        s.angel_one_totp_secret,
    )
    broker.connect()

    client = getattr(broker, "_client", None)
    if client is None:
        raise RuntimeError("Angel One broker did not initialize a client")

    # SmartConnect stores the jwt as access_token after generateSession()
    auth_token = str(getattr(client, "access_token", "") or "").removeprefix("Bearer ").strip()
    feed_token = client.getfeedToken()
    if not auth_token or not feed_token:
        raise RuntimeError("Missing auth/feed token after login")
    return auth_token, feed_token


def place_order(name: str, exch: str, side: str, price: float, qty: int) -> None:
    """Place one LIMIT order through the SmartConnect client."""
    if client is None:
        raise RuntimeError("Not logged in. Call login() first.")

    row = instruments[name][exch]
    params = {
        "variety": "NORMAL",
        "tradingsymbol": row["symbol"],
        "symboltoken": row["token"],
        "transactiontype": side,
        "exchange": exch,
        "ordertype": "LIMIT",
        "producttype": PRODUCT_TYPE,
        "duration": "DAY",
        "price": f"{price:.2f}",
        "quantity": str(qty),
    }
    try:
        resp = client.placeOrderFullResponse(params)
        print(f"   order {side} {name} {exch} @ {price:.2f}: {resp}")
    except Exception as exc:  # pragma: no cover - network / broker call
        print(f"   order FAILED {side} {name} {exch}: {exc}")


def check_arbitrage(name: str) -> None:
    """Signal when best bid on one exchange beats best ask on the other."""
    q = quotes.get(name)
    if not q or "NSE" not in q or "BSE" not in q:
        return
    if abs(q["NSE"]["ts"] - q["BSE"]["ts"]) > MAX_QUOTE_AGE:
        return
    if time.time() - last_signal.get(name, 0) < COOLDOWN_SEC:
        return

    for buy_ex, sell_ex in (("NSE", "BSE"), ("BSE", "NSE")):
        buy_price = q[buy_ex]["ask"]
        sell_price = q[sell_ex]["bid"]
        if buy_price <= 0 or sell_price <= 0:
            continue

        ask_qty, bid_qty = q[buy_ex].get("ask_qty"), q[sell_ex].get("bid_qty")
        qty = min(ask_qty, bid_qty) if ask_qty is not None and bid_qty is not None else None

        pct = (sell_price - buy_price) / buy_price * 100
        if pct >= MIN_SPREAD_PCT and (qty is None or qty >= MIN_QTY):
            last_signal[name] = time.time()
            print(
                f"\n*** ARBITRAGE {name} ***\n"
                f"   BUY  on {buy_ex} @ {buy_price:.2f}\n"
                f"   SELL on {sell_ex} @ {sell_price:.2f}\n"
                f"   spread {sell_price - buy_price:.2f} ({pct:.3f}%)  "
                f"available qty {qty if qty is not None else 'n/a'}"
            )
            if PLACE_ORDERS:
                n = ORDER_QTY if qty is None else min(ORDER_QTY, qty)
                place_order(name, buy_ex, "BUY", buy_price, n)
                place_order(name, sell_ex, "SELL", sell_price, n)
            return


def on_data(wsapp: Any, msg: dict[str, Any]) -> None:
    """Handle the raw SmartAPI websocket payload."""
    token = str(msg.get("token", "")).strip('"')
    print(msg)
    exchange_type = msg.get("exchange_type")
    if exchange_type is None:
        return

    key = token_map.get((int(exchange_type), token))
    if not key:
        return

    name, exch = key
    bid = msg.get("best_5_buy_data") or []
    ask = msg.get("best_5_sell_data") or []

    best_bid = max(bid, key=lambda level: int(level.get("price", 0)), default=None)
    best_ask = min(ask, key=lambda level: int(level.get("price", 0)), default=None)
    if best_bid is None or best_ask is None:
        return

    quotes.setdefault(name, {})[exch] = {
        "bid": float(best_bid["price"]) / 100.0,
        "bid_qty": int(best_bid.get("quantity", 0)),
        "ask": float(best_ask["price"]) / 100.0,
        "ask_qty": int(best_ask.get("quantity", 0)),
        "ts": time.time(),
    }

    print(name)
    check_arbitrage(name)



def main() -> None:
    build_instruments()
    if not instruments:
        raise SystemExit("No stocks found on both NSE and BSE.")

    auth_token, feed_token = login()

    s = get_settings()
    sws = SmartWebSocketV2(
        auth_token,
        s.angel_one_api_key,
        s.angel_one_client_id,
        feed_token,
        max_retry_attempt=5,
    )

    token_list = [
        {"exchangeType": EXCH_TYPE[ex], "tokens": [str(v[ex]["token"]) for v in instruments.values()]}
        for ex in ("NSE", "BSE")
    ]

    def on_open(wsapp: Any) -> None:
        print("WebSocket connected. Subscribing...")
        sws.subscribe("arb_watch", 3, token_list)

    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = lambda ws, err: print("WS error:", err)
    sws.on_close = lambda ws: print("WS closed")

    print(f"Watching {len(instruments)} stocks on NSE + BSE. Ctrl+C to stop.")
    try:
        sws.connect()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if broker is not None:
            broker.disconnect()


if __name__ == "__main__":
    main()