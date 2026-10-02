"""
Place a 1-quantity MARKET order for IDEA (Vodafone Idea) on NSE.

Usage (from the project root):
    python strategy/place_order.py                 # BUY 1 IDEA, INTRADAY, asks for confirmation
    python strategy/place_order.py --side SELL
    python strategy/place_order.py --product DELIVERY
    python strategy/place_order.py --yes           # skip the confirmation prompt

The order id is saved to data/last_order.json so cancel_order.py can use it.
THIS PLACES A REAL ORDER WITH REAL MONEY.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pyotp
from SmartApi import SmartConnect

# project root = first parent folder that contains "src"
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src").exists())
sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings  # noqa: E402

SCRIP_FILE = ROOT / "data" / "share_response.json"
LAST_ORDER_FILE = ROOT / "data" / "last_order.json"

SYMBOL = "IDEA-EQ"   # NSE equity symbol for Vodafone Idea
EXCHANGE = "NSE"
QUANTITY = 1


def find_instrument() -> dict:
    """Look up IDEA-EQ on NSE in the scrip master (so the token is never hard-coded)."""
    with open(SCRIP_FILE, encoding="utf-8") as f:
        rows = json.load(f)
    for row in rows:
        if row.get("exch_seg") == EXCHANGE and row.get("symbol", "").upper() == SYMBOL:
            return row
    raise SystemExit(f"{SYMBOL} not found on {EXCHANGE} in {SCRIP_FILE}")


def login() -> tuple[SmartConnect, str]:
    s = get_settings()
    client = SmartConnect(api_key=s.angel_one_api_key)
    session = client.generateSession(
        s.angel_one_client_id,
        s.angel_one_password,
        pyotp.TOTP(s.angel_one_totp_secret).now(),
    )
    if not session.get("status"):
        raise SystemExit(f"Login failed: {session}")
    return client, s.angel_one_client_id


def order_status(client: SmartConnect, order_id: str) -> dict | None:
    book = client.orderBook() or {}
    for order in book.get("data") or []:
        if str(order.get("orderid")) == str(order_id):
            return order
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Place a 1-qty MARKET order for IDEA on NSE")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--product", choices=["INTRADAY", "DELIVERY"], default="INTRADAY")
    parser.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    args = parser.parse_args()

    row = find_instrument()
    print(f"About to place: {args.side} {QUANTITY} x {row['symbol']} "
          f"(token {row['token']}) on {EXCHANGE}, MARKET, {args.product}")
    if not args.yes and input("Type YES to confirm: ").strip() != "YES":
        raise SystemExit("Cancelled, no order placed.")

    client, client_id = login()
    try:
        params = {
            "variety": "NORMAL",
            "tradingsymbol": row["symbol"],
            "symboltoken": row["token"],
            "transactiontype": args.side,
            "exchange": EXCHANGE,
            "ordertype": "MARKET",
            "producttype": args.product,
            "duration": "DAY",
            "price": "0",          # price is 0 for MARKET orders
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(QUANTITY),
        }
        resp = client.placeOrderFullResponse(params)
        print("Response:", resp)

        if not resp or not resp.get("status"):
            raise SystemExit("Order was not accepted.")

        order_id = resp["data"]["orderid"]
        LAST_ORDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_ORDER_FILE.write_text(
            json.dumps({"orderid": order_id, "variety": "NORMAL",
                        "symbol": row["symbol"], "side": args.side}, indent=2),
            encoding="utf-8",
        )
        print(f"Order id: {order_id} (saved to {LAST_ORDER_FILE})")

        time.sleep(1)  # give the exchange a moment before reading the status
        status = order_status(client, order_id)
        if status:
            print(f"Status: {status.get('orderstatus')}  "
                  f"filled {status.get('filledshares')}/{status.get('quantity')}  "
                  f"avg price {status.get('averageprice')}  "
                  f"{status.get('text') or ''}")
        else:
            print("Order not visible in the order book yet; check your Angel One app.")
    finally:
        client.terminateSession(client_id)


if __name__ == "__main__":
    main()